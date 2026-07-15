"""Job tools — submit, list, result, cancel, log.

Phase 2 of the job system (see JOB-SYSTEM-CODER.md).
"""

import re
import subprocess
import sys

from ..constants import MAX_TOOL_OBSERVATION_CHARS


class _ToolBase:
    """Minimal base class mirroring tools.Tool — avoids circular import."""
    name = ""
    description = ""
    system_prompt = ""
    parameters = {}
    do_not_truncate_observations = False

    def execute(self, params, workdir=None):
        raise NotImplementedError


# ── Active manager singleton ───────────────────────────────────────────
_active_manager = None


def set_active_manager(mgr):
    """Set the module-level JobManager used by job tools."""
    global _active_manager
    _active_manager = mgr


def get_active_manager():
    return _active_manager


# ── Subprocess worker ──────────────────────────────────────────────────

def _subprocess_worker(job, command, workdir):
    """Run a shell command as a subprocess, streaming output to the job log."""
    kwargs = dict(
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=workdir,
    )
    from ..platform import terminal
    kwargs.update(terminal.subprocess_flags())

    proc = subprocess.Popen(command, **kwargs)
    progress_re = re.compile(r'\[?(\d+(?:\.\d+)?)%\]?')

    output_lines = []
    for raw_line in proc.stdout:
        line = raw_line.decode("utf-8", errors="replace")
        output_lines.append(line)
        job.append_log(line.rstrip())
        m = progress_re.search(line)
        if m:
            job.update_progress(float(m.group(1)) / 100.0)
        if job.cancel_event.is_set():
            from ..process import kill_proc_tree
            kill_proc_tree(proc)
            break

    proc.wait(timeout=5)
    if job.cancel_event.is_set():
        return "[cancelled]"
    rc = proc.returncode
    combined = "".join(output_lines).strip()
    if rc != 0:
        raise RuntimeError(f"Exit code {rc}\n{combined[-2000:]}")
    return combined[-5000:]


# ── Tool-wrap worker ───────────────────────────────────────────────────

def _tool_wrap_worker(job, tool_name, params, workdir):
    """Run an existing tool inside the worker thread."""
    from . import get as _get
    tool = _get(tool_name)
    if tool is None:
        raise RuntimeError(f"Unknown tool: {tool_name}")
    result = tool.execute(params, workdir=workdir)
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(result["error"])
    return result


# ── Tools ──────────────────────────────────────────────────────────────

class JobSubmitTool(_ToolBase):
    name = "job_submit"
    description = "Submit a long-running task as a background job"
    parameters = {
        "name": {"type": "string", "required": True, "description": "Display name"},
        "type": {"type": "string", "required": True, "description": "Job type: video_timestamp, model_analysis, custom"},
        "command": {"type": "string", "required": False, "description": "Shell command to run (for subprocess jobs)"},
        "params": {"type": "object", "required": False, "description": "Parameters for the task"},
        "tool": {"type": "string", "required": False, "description": "Tool name to wrap (for tool-wrap mode)"},
        "timeout": {"type": "number", "required": False, "description": "Timeout in seconds"},
    }
    system_prompt = """## job_submit

Submit a long-running task (video processing, model analysis) as a background job.
Provide 'command' for shell commands, or 'type'+'params' to wrap a tool.
Returns job_id immediately. Use job_list to check status, job_result to get output.

Parameters (JSON object):
- name (string, required): Display name for the job
- type (string, required): Job type: video_timestamp, model_analysis, custom
- command (string, optional): Shell command to run (for subprocess jobs)
- params (object, optional): Parameters for the task (for tool-wrap mode)
- tool (string, optional): Tool name to wrap (for tool-wrap mode)
- timeout (number, optional): Timeout in seconds

Examples:
- {"name": "encode video", "type": "custom", "command": "ffmpeg -i in.mp4 out.mp4"}
- {"name": "analyze", "type": "model_analysis", "tool": "image_analysis", "params": {"path": "img.png"}}"""

    def execute(self, params, workdir=None):
        mgr = get_active_manager()
        if mgr is None:
            return {"error": "No job manager available."}

        name = params.get("name", "").strip()
        if not name:
            return {"error": "Parameter 'name' is required."}
        job_type = params.get("type", "").strip()
        if not job_type:
            return {"error": "Parameter 'type' is required."}

        command = params.get("command")
        tool_name = params.get("tool")
        job_params = params.get("params", {})
        timeout = params.get("timeout")

        if command:
            worker_fn = lambda j: _subprocess_worker(j, command, workdir)
        elif tool_name:
            worker_fn = lambda j: _tool_wrap_worker(j, tool_name, job_params, workdir)
        else:
            return {"error": "Either 'command' or 'tool' must be provided."}

        job_id = mgr.submit(name, job_type, job_params, worker_fn, timeout=timeout)
        # Wait briefly to catch immediate failures (e.g. command not found)
        import time as _time
        _time.sleep(0.3)
        status, result = mgr.get_result(job_id)
        if status in ("failed", "cancelled"):
            error = result if isinstance(result, str) else str(result)
            return {"job_id": job_id, "status": status, "error": error,
                    "message": f"Job {job_id} {status}: {error}"}
        return {"job_id": job_id, "status": status, "message": f"Job {job_id} submitted. Use job_list to check status."}


class JobListTool(_ToolBase):
    name = "job_list"
    description = "List all jobs with their status, progress, and elapsed time"
    parameters = {
        "status": {"type": "string", "required": False, "description": "Filter by status: pending, running, completed, failed, cancelled"},
    }
    system_prompt = """## job_list

List all jobs with their status, progress, and elapsed time.

Parameters (JSON object):
- status (string, optional): Filter by status: pending, running, completed, failed, cancelled

Example:
- {} → list all jobs
- {"status": "running"} → list only running jobs"""

    def execute(self, params, workdir=None):
        mgr = get_active_manager()
        if mgr is None:
            return {"error": "No job manager available."}
        status_filter = params.get("status")
        jobs = mgr.list_jobs(status_filter=status_filter)
        if not jobs:
            return {"jobs": [], "message": "No jobs found."}
        return {"jobs": jobs}


class JobResultTool(_ToolBase):
    name = "job_result"
    description = "Get the result/output of a completed job"
    parameters = {
        "job_id": {"type": "string", "required": True, "description": "The job ID returned by job_submit"},
    }
    system_prompt = """## job_result

Get the result/output of a completed job. Returns (status, result).

Parameters (JSON object):
- job_id (string, required): The job ID returned by job_submit

Example:
- {"job_id": "custom-001"}"""

    def execute(self, params, workdir=None):
        mgr = get_active_manager()
        if mgr is None:
            return {"error": "No job manager available."}
        job_id = params.get("job_id", "").strip()
        if not job_id:
            return {"error": "Parameter 'job_id' is required."}
        status, result = mgr.get_result(job_id)
        if status == "not_found":
            return {"error": f"Job {job_id} not found."}
        # Cache full output to .uhu/.cache/ and truncate for context
        cache_url = None
        if isinstance(result, str) and len(result) > MAX_TOOL_OBSERVATION_CHARS:
            import os
            cache_dir = os.path.join(workdir or ".", ".uhu", ".cache")
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, f"job_{job_id}_result.txt")
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(result)
            cache_url = f"file:///{os.path.abspath(cache_path).replace(os.sep, '/')}"
            result = result[:MAX_TOOL_OBSERVATION_CHARS] + (
                f"\n... (truncated, {len(result)} total chars. Full output: {cache_url})"
            )
        resp = {"job_id": job_id, "status": status, "result": result}
        if cache_url:
            resp["cache_url"] = cache_url
        return resp


class JobCancelTool(_ToolBase):
    name = "job_cancel"
    description = "Cancel a running job"
    parameters = {
        "job_id": {"type": "string", "required": True, "description": "The job ID to cancel"},
    }
    system_prompt = """## job_cancel

Cancel a running job. Cooperative for threads, forceful for subprocesses.

Parameters (JSON object):
- job_id (string, required): The job ID to cancel

Example:
- {"job_id": "custom-001"}"""

    def execute(self, params, workdir=None):
        mgr = get_active_manager()
        if mgr is None:
            return {"error": "No job manager available."}
        job_id = params.get("job_id", "").strip()
        if not job_id:
            return {"error": "Parameter 'job_id' is required."}
        ok = mgr.cancel(job_id)
        if not ok:
            return {"error": f"Job {job_id} not found."}
        return {"job_id": job_id, "status": "cancelled", "message": f"Job {job_id} cancellation requested."}


class JobLogTool(_ToolBase):
    name = "job_log"
    description = "Get the last N log lines from a job"
    parameters = {
        "job_id": {"type": "string", "required": True, "description": "The job ID"},
        "last_n": {"type": "integer", "required": False, "description": "Number of lines from the end (default 50)"},
    }
    system_prompt = """## job_log

Get the last N log lines from a job (default 50).

Parameters (JSON object):
- job_id (string, required): The job ID
- last_n (integer, optional): Number of lines from the end (default 50)

Example:
- {"job_id": "custom-001", "last_n": 20}"""

    def execute(self, params, workdir=None):
        mgr = get_active_manager()
        if mgr is None:
            return {"error": "No job manager available."}
        job_id = params.get("job_id", "").strip()
        if not job_id:
            return {"error": "Parameter 'job_id' is required."}
        last_n = params.get("last_n", 50)
        lines = mgr.get_log(job_id, last_n=last_n)
        if lines is None:
            return {"error": f"Job {job_id} not found."}
        return {"job_id": job_id, "lines": lines}
