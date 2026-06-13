"""Git read-only tool: status, diff, log."""

import os
import subprocess
import sys


class GitTool:
    """Read-only git operations: status, diff, log."""
    name = "git"
    description = "Read-only git operations (status, diff, log). No write operations."
    system_prompt = (
        "## git\n"
        "Read-only git operations. No write operations (no add, commit, push, branch).\n"
        "Parameters (JSON object):\n"
        "- action (string, required): One of:\n"
        "    'status' — show working tree status\n"
        "    'diff' — show changes (unstaged by default, or staged with staged:true)\n"
        "    'log' — show commit history\n"
        "- path (string, optional): Repository path (defaults to workdir)\n"
        "- file (string, optional): Specific file to diff or log\n"
        "- staged (boolean, optional, default false): Show staged changes (diff only)\n"
        "- count (integer, optional, default 20): Number of commits to show (log only)\n"
        "- oneline (boolean, optional, default true): Short format (log only)\n"
        "Use this instead of RUN: git status/diff/log — it's cross-platform and returns structured output."
    )
    parameters = {
        "action": {
            "type": "string",
            "description": "Action: 'status', 'diff', or 'log'",
            "required": True,
        },
        "path": {
            "type": "string",
            "description": "Repository path (defaults to workdir)",
            "required": False,
        },
        "file": {
            "type": "string",
            "description": "Specific file to diff or log",
            "required": False,
        },
        "staged": {
            "type": "boolean",
            "description": "Show staged changes instead of unstaged (diff only)",
            "required": False,
        },
        "count": {
            "type": "integer",
            "description": "Number of commits to show (log only, default 20)",
            "required": False,
        },
        "oneline": {
            "type": "boolean",
            "description": "Use short one-line format (log only, default true)",
            "required": False,
        },
    }

    # Allowed read-only git subcommands
    _ALLOWED_ACTIONS = {"status", "diff", "log"}

    def execute(self, params, workdir=".", **kwargs):
        action = params.get("action", "").lower()
        if action not in self._ALLOWED_ACTIONS:
            return f"Error: Unknown git action '{action}'. Allowed: {', '.join(sorted(self._ALLOWED_ACTIONS))}"

        repo_path = params.get("path", workdir)
        if not os.path.isabs(repo_path):
            repo_path = os.path.join(workdir, repo_path)

        # Verify it's a git repo
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            # Try git rev-parse to handle worktrees or bare repos
            result = self._run_git(["rev-parse", "--git-dir"], repo_path)
            if result.startswith("Error"):
                return f"Error: Not a git repository: {repo_path}"

        if action == "status":
            return self._status(repo_path, params)
        elif action == "diff":
            return self._diff(repo_path, params)
        elif action == "log":
            return self._log(repo_path, params)

    def _status(self, repo_path, params):
        """Show working tree status."""
        args = ["status", "--porcelain=v1"]
        # Add branch info
        branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)
        if branch.startswith("Error"):
            branch = "(unknown)"

        result = self._run_git(args, repo_path)
        if result.startswith("Error"):
            return result

        if not result.strip():
            return f"Branch: {branch}\nWorking tree clean"

        # Parse porcelain status
        lines = result.strip().splitlines()
        staged_lines = []
        unstaged_lines = []
        untracked_lines = []

        for line in lines:
            if len(line) < 2:
                continue
            xy = line[:2]
            filepath = line[2:].lstrip()
            if xy[0] in ("M", "A", "D", "R", "C"):
                staged_lines.append(f"  {xy[0]} {filepath}")
            if xy[1] in ("M", "D"):
                unstaged_lines.append(f"  {xy[1]} {filepath}")
            if xy == "??":
                untracked_lines.append(f"  {filepath}")

        parts = [f"Branch: {branch}"]
        if staged_lines:
            parts.append(f"Staged changes ({len(staged_lines)}):")
            parts.extend(staged_lines)
        if unstaged_lines:
            parts.append(f"Unstaged changes ({len(unstaged_lines)}):")
            parts.extend(unstaged_lines)
        if untracked_lines:
            parts.append(f"Untracked files ({len(untracked_lines)}):")
            parts.extend(untracked_lines)

        return "\n".join(parts)

    def _diff(self, repo_path, params):
        """Show changes."""
        file = params.get("file", "")
        staged = params.get("staged", False)

        args = ["diff"]
        if staged:
            args.append("--cached")
        if file:
            args.append("--")
            args.append(file)

        result = self._run_git(args, repo_path)
        if result.startswith("Error"):
            return result

        if not result.strip():
            what = "staged" if staged else "unstaged"
            return f"No {what} changes" + (f" in {file}" if file else "")

        # Truncate very large diffs
        max_chars = 30000
        if len(result) > max_chars:
            result = result[:max_chars] + f"\n... [truncated, {len(result)} chars total]"

        return result

    def _log(self, repo_path, params):
        """Show commit history."""
        count = min(100, max(1, int(params.get("count", 20))))
        oneline = params.get("oneline", True)
        file = params.get("file", "")

        if oneline:
            args = ["log", f"--max-count={count}", "--pretty=format:%h %s (%cr) <%an>"]
        else:
            args = ["log", f"--max-count={count}",
                    "--pretty=format:%h %s%n  Author: %an <%ae>%n  Date:   %ci"]

        if file:
            args.extend(["--", file])

        result = self._run_git(args, repo_path)
        if result.startswith("Error"):
            return result

        if not result.strip():
            return "No commits found" + (f" for {file}" if file else "")

        # Add branch info
        branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)
        if not branch.startswith("Error"):
            header = f"Branch: {branch} | Showing {min(count, result.strip().count(chr(10))+1)} commits"
        else:
            header = f"Showing {min(count, result.strip().count(chr(10))+1)} commits"

        return header + "\n" + result

    def _run_git(self, args, cwd):
        """Run a git command and return stdout."""
        # Fallback encoding for Windows
        fallback_encoding = None
        if sys.platform == "win32":
            try:
                import ctypes
                oem_cp = ctypes.windll.kernel32.GetOEMCP()
                fallback_encoding = f"cp{oem_cp}"
            except Exception:
                pass

        try:
            proc = subprocess.run(
                ["git"] + args,
                capture_output=True,
                cwd=cwd,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return "Error: git command timed out"
        except FileNotFoundError:
            return "Error: git is not installed or not in PATH"
        except Exception as e:
            return f"Error: {e}"

        def _decode(raw):
            if not raw:
                return ""
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                if fallback_encoding:
                    try:
                        return raw.decode(fallback_encoding, errors="replace")
                    except Exception:
                        pass
                return raw.decode("utf-8", errors="replace")

        stdout = _decode(proc.stdout).strip()
        stderr = _decode(proc.stderr).strip()

        if proc.returncode != 0:
            if stderr:
                return f"Error: {stderr}"
            if stdout:
                return f"Error: {stdout}"
            return f"Error: git exited with code {proc.returncode}"

        return stdout
