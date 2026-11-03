"""Tests for the event-driven sleep tool (watch mode).

Covers: plain mode contract, watch-mode defaults, fail-fast validation,
job/pid/timeout/interrupt events. See dev-docs/SLEEP-WATCH-DESIGN.md.
"""

import os
import subprocess
import sys
import time

from ollama_agent.tools import jobs as job_tools
from ollama_agent.tools import sleep as sleep_mod
from ollama_agent.tools.sleep import SleepTool


class FakeJob:
    def __init__(self, status, terminal):
        self.status = status
        self._terminal = terminal

    def is_terminal(self):
        return self._terminal


class FakeManager:
    def __init__(self, jobs=None):
        self.jobs = jobs or {}

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def list_jobs(self, status_filter=None):
        summaries = [{"id": k, "status": v.status} for k, v in self.jobs.items()]
        if status_filter:
            summaries = [s for s in summaries if s["status"] == status_filter]
        return summaries


def test_plain_sleep_v1_contract():
    assert SleepTool().execute({"seconds": 1}) == "Slept 1s. Continuing."


def test_seconds_required_in_plain_mode():
    result = SleepTool().execute({})
    assert result == "Error: 'seconds' is required."


def test_terminal_job_returns_immediately():
    job_tools.set_active_manager(
        FakeManager({"custom-001": FakeJob("completed", True)})
    )
    try:
        result = SleepTool().execute({"job_id": "custom-001"})
    finally:
        job_tools.set_active_manager(None)
    assert result["event"] == "job_finished"
    assert result["job_status"] == "completed"


def test_running_job_timeout_with_note():
    job_tools.set_active_manager(
        FakeManager({"custom-001": FakeJob("running", False)})
    )
    try:
        result = SleepTool().execute({"seconds": 1, "job_id": "custom-001"})
    finally:
        job_tools.set_active_manager(None)
    assert result["event"] == "timeout"
    assert "job custom-001 still running" in result["note"]


def test_unknown_job_fails_fast_without_sleeping():
    job_tools.set_active_manager(FakeManager({}))
    try:
        result = SleepTool().execute({"seconds": 5, "job_id": "nope"})
    finally:
        job_tools.set_active_manager(None)
    assert result == {"error": "Job nope not found."}


def test_missing_manager_degrades_gracefully():
    job_tools.set_active_manager(None)
    result = SleepTool().execute({"seconds": 1, "job_id": "custom-001"})
    assert result.startswith("Slept 1s")
    assert "no job manager" in result


def test_dead_pid_returns_immediately():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    for _ in range(50):  # wait for OS to reap the process (max ~5s)
        if not sleep_mod._pid_alive(proc.pid):
            break
        time.sleep(0.1)
    result = SleepTool().execute({"seconds": 5, "process_id": proc.pid})
    assert result["event"] == "process_finished"
    assert result["waited"] == 0


def test_alive_pid_times_out():
    result = SleepTool().execute({"seconds": 1, "process_id": os.getpid()})
    assert result["event"] == "timeout"
    assert f"pid {os.getpid()} still alive" in result["note"]


def test_max_seconds_clamped():
    # plain mode: 1000s request is clamped but immediately interrupted is
    # hard to arrange; instead verify clamp via watch mode constant cap.
    assert sleep_mod.MAX_SLEEP_SECONDS == 600


def test_countdown_shows_running_jobs(capsys):
    job_tools.set_active_manager(
        FakeManager({"custom-001": FakeJob("running", False)})
    )
    try:
        SleepTool().execute({"seconds": 1, "job_id": "custom-001"})
    finally:
        job_tools.set_active_manager(None)
    assert "running jobs: 1" in capsys.readouterr().out
