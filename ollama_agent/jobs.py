"""Core job system: Job, JobStore, JobManager.

Thread-based background workers with a notification queue.
Phase 1 of the job system (see JOB-SYSTEM-CODER.md).
"""

import json
import logging
import os
import queue
import threading
import time
from datetime import datetime
from typing import Any, Callable, Optional

from .constants import MAX_CONCURRENT_JOBS, MAX_JOB_LOG_LINES

logger = logging.getLogger(__name__)

# Status constants
_PENDING = "pending"
_RUNNING = "running"
_COMPLETED = "completed"
_FAILED = "failed"
_CANCELLED = "cancelled"
_INTERRUPTED = "interrupted"

_TERMINAL_STATUSES = {_COMPLETED, _FAILED, _CANCELLED, _INTERRUPTED}


class Job:
    """A single background job executed in a worker thread.

    The worker_fn is called as ``worker_fn(job)`` and may inspect
    ``job.cancel_event`` for cooperative cancellation.
    """

    def __init__(
        self,
        job_id: str,
        name: str,
        job_type: str,
        params: dict,
        worker_fn: Callable[["Job"], Any],
        timeout: Optional[float] = None,
    ):
        self.id = job_id
        self.name = name
        self.type = job_type
        self.status = _PENDING
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None
        self.progress = 0.0
        self.params = params
        self.result: Any = None
        self.error: Optional[str] = None
        self.log: list[str] = []
        self.cancel_event = threading.Event()
        self.timeout = timeout
        self._worker_fn = worker_fn
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        # Back-reference set by JobManager so the worker can emit notifications.
        self._manager: Optional["JobManager"] = None

    # ── lifecycle ──────────────────────────────────────────────────────

    def start(self):
        """Spawn the worker thread and transition to running."""
        with self._lock:
            if self.status not in (_PENDING, _INTERRUPTED):
                return
            self.started_at = datetime.now()
            self.status = _RUNNING
        self._thread = threading.Thread(target=self._run_worker, daemon=True)
        self._thread.start()
        logger.info("Job %s started (%s)", self.id, self.name)

    def cancel(self):
        """Cooperatively request cancellation."""
        self.cancel_event.set()
        with self._lock:
            if self.status in (_PENDING, _RUNNING):
                self.status = _CANCELLED
                self.finished_at = datetime.now()
        logger.info("Job %s cancelled", self.id)

    # ── worker ─────────────────────────────────────────────────────────

    def _run_worker(self):
        """Worker thread body — catches exceptions, emits notifications."""
        event_type = _COMPLETED
        message = "completed"
        try:
            with self._lock:
                self.status = _RUNNING
            self.result = self._worker_fn(self)
            with self._lock:
                if self.cancel_event.is_set():
                    self.status = _CANCELLED
                    event_type = _CANCELLED
                    message = "cancelled"
                else:
                    self.status = _COMPLETED
                    self.finished_at = datetime.now()
                    event_type = _COMPLETED
                    message = "completed"
        except Exception as e:
            with self._lock:
                self.status = _FAILED
                self.error = str(e)
                self.finished_at = datetime.now()
            self.append_log(f"[ERROR] {e}")
            event_type = _FAILED
            message = str(e)
            logger.error("Job %s failed: %s", self.id, e)
        finally:
            if self._manager is not None:
                self._manager._notify(self.id, event_type, message)
                self._manager._try_start_pending()

    # ── progress / log ─────────────────────────────────────────────────

    def update_progress(self, pct: float):
        """Update progress fraction (0.0–1.0)."""
        with self._lock:
            self.progress = max(0.0, min(1.0, float(pct)))

    def append_log(self, line: str):
        """Thread-safe append, capped at MAX_JOB_LOG_LINES."""
        with self._lock:
            self.log.append(str(line))
            if len(self.log) > MAX_JOB_LOG_LINES:
                # Drop oldest lines to stay within cap.
                del self.log[: len(self.log) - MAX_JOB_LOG_LINES]

    # ── serialization ──────────────────────────────────────────────────

    def _elapsed(self) -> str:
        """Human-readable elapsed time string."""
        end = self.finished_at or datetime.now()
        start = self.started_at or self.created_at
        secs = (end - start).total_seconds()
        if secs < 60:
            return f"{secs:.1f}s"
        mins, rem = divmod(int(secs), 60)
        return f"{mins}m{rem}s"

    def to_summary(self) -> dict:
        """Compact summary for list views."""
        with self._lock:
            return {
                "id": self.id,
                "name": self.name,
                "type": self.type,
                "status": self.status,
                "progress": self.progress,
                "elapsed": self._elapsed(),
            }

    def to_dict(self) -> dict:
        """Full state for persistence (no thread/fn references)."""
        with self._lock:
            return {
                "id": self.id,
                "name": self.name,
                "type": self.type,
                "status": self.status,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "finished_at": self.finished_at.isoformat() if self.finished_at else None,
                "progress": self.progress,
                "params": self.params,
                "result": self.result,
                "error": self.error,
                "log": list(self.log),
                "timeout": self.timeout,
            }

    def is_terminal(self) -> bool:
        """True if the job has reached a final state."""
        with self._lock:
            return self.status in _TERMINAL_STATUSES


class JobStore:
    """Thread-safe in-memory store of jobs keyed by id."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def add(self, job: Job):
        with self._lock:
            self._jobs[job.id] = job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status == _RUNNING)

    def to_persistable(self) -> list[dict]:
        """Return dicts for terminal jobs only."""
        with self._lock:
            return [j.to_dict() for j in self._jobs.values() if j.is_terminal()]

    def load_from(self, data: list[dict]):
        """Load jobs from persisted dicts. Running jobs become 'interrupted'."""
        with self._lock:
            for d in data:
                job = Job(
                    job_id=d["id"],
                    name=d.get("name", ""),
                    job_type=d.get("type", "custom"),
                    params=d.get("params", {}),
                    worker_fn=lambda j: None,  # no worker for restored jobs
                    timeout=d.get("timeout"),
                )
                job.status = d.get("status", _INTERRUPTED)
                if job.status == _RUNNING:
                    job.status = _INTERRUPTED
                job.progress = d.get("progress", 0.0)
                job.result = d.get("result")
                job.error = d.get("error")
                job.log = list(d.get("log", []))
                if d.get("created_at"):
                    job.created_at = datetime.fromisoformat(d["created_at"])
                if d.get("started_at"):
                    job.started_at = datetime.fromisoformat(d["started_at"])
                if d.get("finished_at"):
                    job.finished_at = datetime.fromisoformat(d["finished_at"])
                self._jobs[job.id] = job


class JobManager:
    """Manages job submission, concurrency limits, notifications, watchdog."""

    MAX_CONCURRENT = MAX_CONCURRENT_JOBS
    MAX_JOB_LOG_LINES = MAX_JOB_LOG_LINES

    def __init__(self, workdir: str):
        self._store = JobStore()
        self._notifications: queue.Queue = queue.Queue()
        self._seq = 0
        self._lock = threading.Lock()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._workdir = workdir
        self._shutdown = False
        self._start_watchdog()

    # ── submission ─────────────────────────────────────────────────────

    def submit(
        self,
        name: str,
        job_type: str,
        params: dict,
        worker_fn: Callable[[Job], Any],
        timeout: Optional[float] = None,
    ) -> str:
        """Create a job, add to store, start if a slot is free.

        If ``running_count >= MAX_CONCURRENT`` the job stays ``pending``
        and the watchdog starts it when a slot frees up.
        Returns the job id.
        """
        with self._lock:
            self._seq += 1
            seq = self._seq
        job_id = f"{job_type}-{seq:03d}"
        job = Job(job_id, name, job_type, params, worker_fn, timeout=timeout)
        job._manager = self
        self._store.add(job)
        logger.info("Job %s submitted (%s)", job_id, name)

        if self._store.running_count() < self.MAX_CONCURRENT:
            job.start()
        # else: watchdog will start it when a slot frees.
        return job_id

    # ── control ────────────────────────────────────────────────────────

    def cancel(self, job_id: str) -> bool:
        """Cancel a job by id. Returns True if the job existed."""
        job = self._store.get(job_id)
        if job is None:
            return False
        job.cancel()
        return True

    def list_jobs(self, status_filter: Optional[str] = None) -> list[dict]:
        """Return summaries for all jobs, optionally filtered by status."""
        jobs = self._store.all()
        if status_filter:
            jobs = [j for j in jobs if j.status == status_filter]
        return [j.to_summary() for j in jobs]

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._store.get(job_id)

    def get_result(self, job_id: str) -> tuple[str, Any]:
        """Return (status, result) for completed jobs, (status, error) for failed."""
        job = self._store.get(job_id)
        if job is None:
            return ("not_found", None)
        with job._lock:
            if job.status == _FAILED:
                return (_FAILED, job.error)
            return (job.status, job.result)

    def get_log(self, job_id: str, last_n: int = 50) -> list[str]:
        job = self._store.get(job_id)
        if job is None:
            return []
        with job._lock:
            return list(job.log[-last_n:])

    # ── notifications ──────────────────────────────────────────────────

    def _notify(self, job_id: str, event_type: str, message: str):
        """Push a job event onto the notification queue."""
        self._notifications.put(
            {
                "job_id": job_id,
                "event_type": event_type,
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def drain_notifications(self) -> list[dict]:
        """Pop all pending notifications (non-blocking)."""
        notifs = []
        while True:
            try:
                notifs.append(self._notifications.get_nowait())
            except queue.Empty:
                break
        return notifs

    # ── watchdog ───────────────────────────────────────────────────────

    def _try_start_pending(self):
        """Start pending jobs if concurrency slots are available.

        Called immediately when a job finishes, so pending jobs don't
        have to wait for the next 5s watchdog cycle.
        """
        for job in self._store.all():
            if self._store.running_count() >= self.MAX_CONCURRENT:
                break
            if job.status == _PENDING:
                job.start()

    def _start_watchdog(self):
        """Background thread: reap dead workers, enforce timeouts, start pending."""

        def _watch():
            while not self._shutdown:
                try:
                    for job in self._store.all():
                        # Reap dead threads
                        if (
                            job.status == _RUNNING
                            and job._thread is not None
                            and not job._thread.is_alive()
                            and not job.is_terminal()
                        ):
                            with job._lock:
                                job.status = _FAILED
                                job.error = "worker thread died unexpectedly"
                                job.finished_at = datetime.now()
                            self._notify(job.id, _FAILED, job.error)
                            logger.warning("Job %s thread died", job.id)

                        # Check timeouts
                        if (
                            job.status == _RUNNING
                            and job.timeout
                            and job.started_at
                        ):
                            elapsed = (datetime.now() - job.started_at).total_seconds()
                            if elapsed > job.timeout:
                                job.cancel()
                                self._notify(
                                    job.id, _FAILED, f"timed out after {job.timeout}s"
                                )
                                logger.warning("Job %s timed out", job.id)

                        # Start pending jobs if slots available
                        if (
                            job.status == _PENDING
                            and self._store.running_count() < self.MAX_CONCURRENT
                        ):
                            job.start()
                except Exception:
                    logger.exception("Watchdog error")

                time.sleep(5)

        self._watchdog_thread = threading.Thread(target=_watch, daemon=True)
        self._watchdog_thread.start()

    # ── shutdown ───────────────────────────────────────────────────────

    def shutdown(self):
        """Cancel all active jobs, wait up to 5s for threads, stop watchdog."""
        self._shutdown = True
        for job in self._store.all():
            if job.status in (_PENDING, _RUNNING):
                job.cancel()
        # Wait for running threads to finish (cooperative).
        deadline = time.time() + 5
        for job in self._store.all():
            if job._thread and job._thread.is_alive():
                remaining = max(0.1, deadline - time.time())
                job._thread.join(timeout=remaining)
        logger.info("JobManager shut down")

    # ── persistence ─────────────────────────────────────────────────────

    JOB_STATE_FILE = ".uhu/jobs.json"

    def save_state(self):
        """Persist terminal jobs to .uhu/jobs.json."""
        path = os.path.join(self._workdir, self.JOB_STATE_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = self._store.to_persistable()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_state(self):
        """Load persisted jobs from .uhu/jobs.json."""
        path = os.path.join(self._workdir, self.JOB_STATE_FILE)
        if not os.path.isfile(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._store.load_from(data)
        logger.info("Loaded %d persisted jobs", len(data))
