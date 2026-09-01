"""System info tool — RAM, CPU, GPU load, top processes.

Wraps scripts/sys_info.py (psutil-based, cross-platform).
Supports --json mode for structured output.
"""

import json
import os
import subprocess
import sys


class SysInfoTool:
    name = "sys_info"
    description = "Get system resource usage: RAM, CPU, GPU load, top processes"
    system_prompt = """## sys_info

Get current system resource usage: RAM (total/used/free/reclaimable/available),
CPU load (overall + per-core), GPU load (best-effort, platform-specific),
and top 5 processes by CPU and RAM.

No parameters. Output is JSON.

Use this tool when the user asks about system resources, memory pressure,
CPU load, GPU usage, or which processes are consuming resources.

Example:
- {}"""
    parameters = {}
    do_not_truncate_observations = False

    def execute(self, params, workdir=None):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "sys_info.py")
        if not os.path.isfile(script):
            return {"error": f"Script not found: {script}"}
        try:
            result = subprocess.run(
                [sys.executable, script, "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return {"error": "System info collection timed out (30s)"}
        except Exception as e:
            return {"error": f"Failed to run sys_info script: {e}"}
        if result.returncode != 0:
            err = (result.stderr or "").strip()
            return {"error": f"sys_info script failed: {err or 'unknown error'}"}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"error": "sys_info returned invalid JSON", "raw": result.stdout[:2000]}


# psutil check at import time — give a helpful error if missing
try:
    import psutil  # noqa: F401
except ImportError:
    SysInfoTool.system_prompt += "\n\nNOTE: psutil is not installed. Install with: pip install psutil"
