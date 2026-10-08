"""npm build tool — run npm scripts with structured, bounded output.

Replaces the frequent RUN/job pattern `cd ui && npm run build` seen in
session logs. Output truncation keeps the tail (vite/TS errors print last).
"""

import os
import subprocess

from ..actions import agent_print


class NpmBuildTool:
    """Run npm scripts with bounded, structured output."""
    name = "npm_build"
    description = "Run npm scripts (build, lint, test) with structured, bounded output."
    system_prompt = (
        "## npm_build\n"
        "Run npm scripts with structured, bounded output. Use instead of RUN 'cd ui && npm run build'.\n"
        "Parameters (JSON object):\n"
        "- script (string, optional, default 'build'): npm script name (e.g. 'build', 'lint', 'test')\n"
        "- cwd (string, optional, default 'ui'): Directory containing package.json (relative to workdir)\n"
        "- args (string or list, optional): Extra args passed to the script (e.g. '--mode production')\n"
        "- timeout (integer, optional, default 300): Max seconds (max 1800)\n"
        "Use this instead of RUN with 'npm run' — output is bounded (tail kept, where build errors print).\n"
        "For very long builds (>5 min), wrap this tool via job_submit (tool: 'npm_build')."
    )
    parameters = {
        "script": {
            "type": "string",
            "description": "npm script name (default: 'build')",
            "required": False,
        },
        "cwd": {
            "type": "string",
            "description": "Directory containing package.json (default: 'ui')",
            "required": False,
        },
        "args": {
            "type": "string",
            "description": "Extra args passed to the script",
            "required": False,
        },
        "timeout": {
            "type": "integer",
            "description": "Max seconds for the run (default 300, max 1800)",
            "required": False,
        },
    }

    MAX_OUTPUT_CHARS = 4000
    TAIL_CHARS = 3000

    def execute(self, params, workdir=".", **kwargs):
        script = params.get("script", "build")
        cwd_rel = params.get("cwd", "ui")
        args = params.get("args", [])
        timeout = min(1800, int(params.get("timeout", 300)))

        if isinstance(args, str):
            args = args.split()
        elif isinstance(args, (list, tuple)):
            args = [str(a) for a in args]
        else:
            args = []

        full_cwd = os.path.join(workdir, cwd_rel) if not os.path.isabs(cwd_rel) else cwd_rel
        if not os.path.isfile(os.path.join(full_cwd, "package.json")):
            return f"Error: no package.json in '{cwd_rel}' (workdir: {workdir})"

        cmd = ["npm", "run", script] + args
        try:
            proc = subprocess.run(
                cmd, cwd=full_cwd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
                shell=(os.name == "nt"),
            )
        except subprocess.TimeoutExpired:
            return f"Error: npm run {script} timed out after {timeout}s (cwd: {cwd_rel})"
        except FileNotFoundError:
            return "Error: npm not found — is Node.js installed?"

        out = (proc.stdout or "")
        err = (proc.stderr or "")
        combined = out if out.strip() else err
        if err.strip() and out.strip():
            combined = out + "\n[stderr]\n" + err

        lines = [l for l in combined.splitlines() if l.strip()]
        summary = lines[-1] if lines else "(no output)"

        parts = [f"[npm {script} exit={proc.returncode}] {summary}"]
        if proc.returncode != 0:
            tail = combined[-self.TAIL_CHARS:]
            parts.append("Output tail:\n" + tail)

        result = "\n".join(parts)
        if len(result) > self.MAX_OUTPUT_CHARS:
            result = result[: self.MAX_OUTPUT_CHARS] + "\n[... truncated]"
        return result
