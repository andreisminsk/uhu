"""Sleep tool — wait for a specified number of seconds.

Two modes:

- Plain mode (no watchers): sleep N seconds — unchanged v1 behavior.
- Watch mode: optional ``job_id`` / ``process_id`` params. The tool exits on
  the earliest event: timeout, the watched job reaching a terminal state, or
  the watched PID no longer being alive.

Watch mode enables the recommended job pattern (saves a full feedback round
versus sleep-then-job_list):

    job_submit → sleep({"seconds": est, "job_id": X}) → job_result

Auto-approved (no side effects). Prints a countdown so the user can see the
agent is waiting, not frozen. Design doc: dev-docs/SLEEP-WATCH-DESIGN.md
"""

import os
import sys
import time

MAX_SLEEP_SECONDS = 600


def _pid_alive(pid):
    """True if ``pid`` is a live process. Tiered implementation:

    1. psutil if installed (best semantics; can detect zombies),
    2. POSIX ``os.kill(pid, 0)``,
    3. shell fallback (tasklist on Windows).

    Conservative: unknown state → assume alive (the timeout still bounds waits).
    """
    if pid <= 0:
        return False
    try:
        import psutil
    except ImportError:
        psutil = None
    if psutil is not None:
        try:
            proc = psutil.Process(pid)
            return proc.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False
        except psutil.AccessDenied:
            return True
        except Exception:
            pass  # fall through to the next tier
    if hasattr(os, "kill"):
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # exists, owned by another user
        except OSError:
            return False
    try:
        import subprocess
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True, timeout=5,
        )
        return str(pid) in out.stdout.decode("utf-8", errors="replace")
    except Exception:
        return True


def _running_jobs_count(mgr):
    """Number of currently running jobs, or None if unavailable."""
    if mgr is None:
        return None
    try:
        return len(mgr.list_jobs("running"))
    except Exception:
        return None  # display-only — must never break the wait


def _progress_line(remaining, mgr, job_id, job_obj, pid):
    parts = [f"[Waiting... {remaining}s remaining"]
    count = _running_jobs_count(mgr)
    if count:
        parts.append(f" | running jobs: {count}")
    if job_id:
        status = job_obj.status if job_obj is not None else "?"
        parts.append(f" | job {job_id}: {status}")
    if pid is not None:
        parts.append(f" | pid {pid}: alive")
    return "".join(parts) + "]"


def _print_progress(remaining, mgr, job_id, job_obj, pid, pad=0):
    """Overwrite the countdown line. ``pad`` is the length of the longest line
    printed so far — shorter lines are space-padded so they fully erase the
    previous longer one (no garbled residue on terminals without ANSI EL)."""
    line = _progress_line(remaining, mgr, job_id, job_obj, pid)
    if len(line) < pad:
        line = line.ljust(pad)
    sys.stdout.write("\r" + line)
    sys.stdout.flush()
    return max(pad, len(line))


def _clear_line(exit_msg, pad=0):
    msg = f"[{exit_msg}]"
    if len(msg) < pad:
        msg = msg.ljust(pad)
    sys.stdout.write("\r" + msg + "\n")
    sys.stdout.flush()


def _jobs_hint(mgr):
    """Nudge the model when it sleeps plain while background jobs are running,
    but did not pass a job_id — wake-up-on-completion is what sleep is for."""
    count = _running_jobs_count(mgr)
    if not count:
        return ""
    plural = "s" if count > 1 else ""
    return (" (note: {} job{} running — re-run sleep with its job_id to wake "
            "as soon as a job finishes)".format(count, plural))


class SleepTool:
    name = "sleep"
    description = (
        "Wait for a specified number of seconds; with optional job_id/process_id "
        "watchers, exits on the earliest event (timeout, job finished, process gone)"
    )
    system_prompt = """## sleep

Wait for a specified number of seconds. Use this when you need to wait for a
background job to finish, a server to start, or a rate limit to clear.
Max 600 seconds (10 minutes). Auto-approved — no confirmation needed.

Event-driven watch mode — pass optional watchers and the tool exits on the
EARLIEST event (timeout, watched job finishes, watched process exits):

- job_id (string, optional): exit as soon as this job reaches a terminal
  state (completed/failed/cancelled/interrupted)
- process_id (integer, optional): exit as soon as this OS process is gone

RECOMMENDED job pattern (replaces sleep-then-job_list, saves a round):
1. job_submit → returns job_id immediately
2. sleep {"seconds": <estimate>, "job_id": "<id>"} →
   {"event": "job_finished", "job_status": ...} when done, or
   {"event": "timeout", ...} if the estimate was too short
3. job_result {"job_id": ...} → fetch the job output

Plain mode (no watchers) requires seconds and behaves as before.
In watch mode seconds is a timeout cap (default 600).

Parameters (JSON object):
- seconds (integer, optional in watch mode, default 600): Max seconds to wait (max 600)
- job_id (string, optional): Watched job — exit when it reaches a terminal state
- process_id (integer, optional): Watched PID — exit when the process is gone

Examples:
- {"seconds": 30}
- {"seconds": 120, "job_id": "custom-001"}
- {"job_id": "custom-001"}
- {"process_id": 1234, "seconds": 60}"""
    parameters = {
        "seconds": {
            "type": "integer",
            "required": False,
            "description": "Max seconds to wait; required in plain mode, optional timeout cap in watch mode (max 600, default 600)",
        },
        "job_id": {
            "type": "string",
            "required": False,
            "description": "Exit early when this job reaches a terminal state",
        },
        "process_id": {
            "type": "integer",
            "required": False,
            "description": "Exit early when this PID is no longer alive",
        },
    }
    do_not_truncate_observations = True

    def execute(self, params, workdir=None):
        raw_seconds = params.get("seconds")
        raw_job = params.get("job_id")
        raw_pid = params.get("process_id")

        # ── parse job_id ──
        if raw_job is None or (isinstance(raw_job, str) and not raw_job.strip()):
            job_id = None
        elif isinstance(raw_job, str):
            job_id = raw_job.strip()
        else:
            return "Error: 'job_id' must be a string."

        # ── parse process_id ──
        pid = None
        if raw_pid is not None and raw_pid != "":
            if isinstance(raw_pid, bool):
                return "Error: 'process_id' must be a positive integer."
            try:
                pid = int(raw_pid)
            except (TypeError, ValueError):
                return "Error: 'process_id' must be a positive integer."
            if pid <= 0:
                return "Error: 'process_id' must be a positive integer."

        # ── resolve watchers: fail fast where possible, degrade gracefully ──
        from .jobs import get_active_manager  # lazy — avoids circular import
        mgr = get_active_manager()
        degrade_note = ""
        if job_id and mgr is None:
            degrade_note = f" (note: job_id '{job_id}' ignored — no job manager available)"
            job_id = None

        job_obj = None
        if job_id:
            job_obj = mgr.get_job(job_id)
            if job_obj is None:
                return {"error": f"Job {job_id} not found."}

        if pid is not None and not _pid_alive(pid):
            return {"event": "process_finished", "process_id": pid, "waited": 0}

        # ── seconds ──
        watch_mode = job_id is not None or pid is not None
        if raw_seconds is None or raw_seconds == "":
            if watch_mode:
                seconds = MAX_SLEEP_SECONDS
            else:
                return "Error: 'seconds' is required."
        else:
            try:
                seconds = int(raw_seconds)
            except (TypeError, ValueError):
                return "Error: 'seconds' must be an integer."
            if seconds <= 0:
                return "Error: 'seconds' must be positive."
        seconds = min(seconds, MAX_SLEEP_SECONDS)

        # ── wait loop: exit on earliest event ──
        start = time.monotonic()
        pad = 0  # longest countdown line printed this wait — erases residue
        try:
            while True:
                elapsed = time.monotonic() - start
                if elapsed >= seconds:  # ① timeout
                    if watch_mode:
                        _clear_line(f"Wait ended: timeout after {seconds}s", pad)
                        return _timeout_result(seconds, job_id, job_obj, pid)
                    _clear_line(f"Slept {seconds}s", pad)
                    return f"Slept {seconds}s. Continuing.{_jobs_hint(mgr)}{degrade_note}"
                if job_obj is not None and job_obj.is_terminal():  # ② job done
                    _clear_line(f"Wait ended: job {job_id} {job_obj.status}", pad)
                    return {
                        "event": "job_finished",
                        "job_id": job_id,
                        "job_status": job_obj.status,
                        "waited": round(elapsed, 1),
                    }
                if pid is not None and not _pid_alive(pid):  # ③ process gone
                    _clear_line(f"Wait ended: pid {pid} is gone", pad)
                    return {
                        "event": "process_finished",
                        "process_id": pid,
                        "waited": round(elapsed, 1),
                    }
                remaining = seconds - int(elapsed)
                if int(elapsed) % 15 == 0 or remaining <= 5:
                    pad = _print_progress(remaining, mgr, job_id, job_obj, pid, pad)
                time.sleep(max(0.05, min(1.0, seconds - (time.monotonic() - start))))
        except KeyboardInterrupt:
            elapsed = time.monotonic() - start
            _clear_line(f"Interrupted after {int(elapsed)}s", pad)
            if watch_mode:
                return {"event": "interrupted", "waited": round(elapsed, 1)}
            return f"Interrupted after {int(elapsed)}s."


def _timeout_result(seconds, job_id, job_obj, pid):
    """Build the timeout observation: which watchers did NOT fire."""
    result = {"event": "timeout", "waited": seconds}
    notes = []
    if job_obj is not None:
        notes.append(f"job {job_id} still {job_obj.status} — check job_list")
    if pid is not None:
        notes.append(f"pid {pid} still alive")
    if notes:
        result["note"] = "; ".join(notes)
    return result
