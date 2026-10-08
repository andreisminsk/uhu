"""pytest tool — run test suites with structured, bounded output.

Replaces the frequent RUN pattern `python -m pytest tests/ -q` seen in
session logs. Auto-approved (project's own test code), with output
truncation that preserves the summary line and failed test names.
"""

import os
import subprocess
import sys

from ..actions import agent_print


class PytestTool:
    """Run pytest with bounded, structured output."""
    name = "pytest"
    description = "Run pytest tests with structured, bounded output (auto-approved)."
    system_prompt = (
        "## pytest\n"
        "Run pytest test suites with structured, bounded output. Auto-approved — no confirmation needed.\n"
        "Parameters (JSON object):\n"
        "- path (string, optional, default 'tests'): Test file, directory, or node id "
        "(e.g. 'tests', 'tests/test_app.py', 'tests/test_app.py::test_name')\n"
        "- args (string or list, optional): Extra pytest args (e.g. '-x', '--tb=short', '-k pattern', '--lf')\n"
        "- timeout (integer, optional, default 300): Max seconds for the run (max 1800)\n"
        "Use this instead of RUN with 'python -m pytest' — it is auto-approved and output-bounded.\n"
        "For very long suites (>5 min), wrap this tool via job_submit (tool: 'pytest')."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Test file, directory, or node id (default: 'tests')",
            "required": False,
        },
        "args": {
            "type": "string",
            "description": "Extra pytest args, e.g. '-x --tb=short' or '-k login'",
            "required": False,
        },
        "timeout": {
            "type": "integer",
            "description": "Max seconds for the run (default 300, max 1800)",
            "required": False,
        },
    }

    # Output budget: summary + failed names + traceback tail
    MAX_OUTPUT_CHARS = 4000
    MAX_FAILED_LINES = 30
    TAIL_CHARS = 2500

    def execute(self, params, workdir=".", **kwargs):
        path = params.get("path", "tests")
        args = params.get("args", [])
        timeout = min(1800, int(params.get("timeout", 300)))

        if isinstance(args, str):
            args = args.split()
        elif isinstance(args, (list, tuple)):
            args = [str(a) for a in args]
        else:
            args = []

        cmd = [sys.executable, "-m", "pytest", path, "-q", "--tb=short", "-rf"] + args

        try:
            proc = subprocess.run(
                cmd, cwd=workdir, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"Error: pytest timed out after {timeout}s (path: {path})"
        except FileNotFoundError as e:
            return f"Error running pytest: {e}"

        out = (proc.stdout or "")
        err = (proc.stderr or "")
        # Collection errors and crashes go to stderr
        if proc.returncode not in (0, 1) and err and not out.strip():
            out = err

        lines = [l for l in out.splitlines() if l.strip()]
        # Summary is the last line, e.g. "5 failed, 12 passed in 2.34s"
        summary = lines[-1] if lines else "(no output)"
        failed_lines = [l for l in lines if l.startswith(("FAILED", "ERROR"))]

        parts = [f"[pytest exit={proc.returncode}] {summary}"]
        if failed_lines:
            parts.append("Failed:")
            parts.extend(f"  {l}" for l in failed_lines[: self.MAX_FAILED_LINES])
            if len(failed_lines) > self.MAX_FAILED_LINES:
                parts.append(f"  ... and {len(failed_lines) - self.MAX_FAILED_LINES} more")
        if proc.returncode != 0:
            tail = out[-self.TAIL_CHARS:]
            parts.append("Output tail:\n" + tail)

        result = "\n".join(parts)
        if len(result) > self.MAX_OUTPUT_CHARS:
            result = result[: self.MAX_OUTPUT_CHARS] + "\n[... truncated]"
        return result
