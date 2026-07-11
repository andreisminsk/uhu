"""Command runner — extracted from actions.py for testability.

Handles subprocess execution with streaming output, timeout, encoding
fallback, and process tree killing.
"""

import queue as _queue
import re
import subprocess
import sys
import threading
import time

from .display import agent_print
from .process import kill_proc_tree
from .safety import CommandSafetyGate, get_base_command


def _fix_win_backslash_quote(m):
    """Fix odd number of backslashes before a closing quote on Windows.

    In cmd.exe, \\" is an escaped quote, so "C:\\path\\" is parsed as C:\\path"
    (invalid path). Remove one backslash from odd-length runs so the quote
    properly terminates the argument.
    """
    backslashes = m.group(1)
    if len(backslashes) % 2 == 1:
        return backslashes[:-1] + '"'
    return m.group(0)


class CommandRunner:
    """Preprocess and execute shell commands.

    Handles:
    - PowerShell routing (platform check + command wrapping)
    - Skill script path rewriting
    - Windows backslash-quote fixing
    - Safety checks (blocked/warning/chain/safe)
    - Confirmation flow (via callback)
    - Subprocess execution with streaming, timeout, encoding fallback
    """

    def __init__(self, workdir, safety=None):
        self.workdir = workdir
        self._safety = safety or CommandSafetyGate()

    def preprocess(self, cmd, run_lang, workdir):
        """Preprocess a command: PowerShell routing, script rewriting, Windows quoting.

        Returns (processed_cmd, skip_reason).
        - If skip_reason is not None, the command should be skipped (e.g. PS on Unix).
        """
        # Route PowerShell fence blocks through powershell.exe
        if run_lang in ("powershell", "ps1", "pwsh"):
            if sys.platform == "win32":
                cmd = f'powershell -NoProfile -Command "{cmd}"'
            else:
                return (cmd, "PowerShell fence block used on non-Windows platform")

        # Rewrite short script paths to full workdir-relative paths
        from .skills import find_script_in_cmd
        script_replacements = find_script_in_cmd(cmd, workdir=workdir)
        for matched_text, resolved_path in script_replacements:
            if matched_text != resolved_path:
                cmd = cmd.replace(matched_text, resolved_path)

        # Fix Windows backslash-quote escaping
        if sys.platform == "win32":
            cmd = re.sub(r'(\\+)"', _fix_win_backslash_quote, cmd)

        return (cmd, None)

    def check_safety(self, cmd):
        """Return (safety_level, safety_msg) for a command."""
        return self._safety.check(cmd)

    def is_safe(self, cmd):
        """Return True if command is auto-safe (read-only)."""
        return self._safety.is_safe(cmd)

    def run(self, cmd, run_lang="", workdir=None, confirm_fn=None):
        """Execute a shell command with safety checks and confirmation.

        Args:
            cmd: The command string.
            run_lang: The fence language (bash, cmd, powershell, etc.).
            workdir: Working directory (defaults to self.workdir).
            confirm_fn: Callback for confirmation prompts.
                Signature: confirm_fn(prompt, cmd=, diff_text=, force_confirm=) -> bool

        Returns:
            Observation string, or None if skipped/blocked.
        """
        workdir = workdir or self.workdir
        cmd, skip_reason = self.preprocess(cmd, run_lang, workdir)
        if skip_reason:
            agent_print(f"⚠ {skip_reason} — skipping.\n")
            return None

        cmd_details = f"[Command details]\n  cwd: {workdir}\n  cmd: {cmd}"
        ell = '…' if len(cmd) > 80 else ''

        # Safety checks
        safety_level, safety_msg = self._safety.check(cmd)
        if safety_level == 'blocked':
            agent_print(f"⛔ {safety_msg}\n")
            return None
        if safety_level == 'warning':
            agent_print(f"{safety_msg}")
            if confirm_fn and not confirm_fn(
                f"[CONFIRM DESTRUCTIVE] {cmd[:80]}{ell}",
                cmd=cmd, diff_text=cmd_details, force_confirm=True
            ):
                agent_print("[Skipped]\n")
                return None
        elif safety_level == 'chain':
            agent_print(f"{safety_msg}")
            if confirm_fn and not confirm_fn(
                f"[RUN] {cmd[:80]}{ell}", cmd=cmd, diff_text=cmd_details
            ):
                agent_print("[Skipped]\n")
                return None
        elif self._safety.is_safe(cmd):
            base = get_base_command(cmd)
            agent_print(f"[auto-safe: {base}] [RUN] {cmd[:80]}{ell}")
        elif confirm_fn and not confirm_fn(
            f"[RUN] {cmd[:80]}{ell}", cmd=cmd, diff_text=cmd_details
        ):
            agent_print("[Skipped]\n")
            return None

        return self._execute_subprocess(cmd, workdir)

    def _execute_subprocess(self, cmd, workdir):
        """Execute the subprocess with streaming, timeout, and encoding fallback."""
        proc = None
        killed = False

        _fallback_encoding = None
        if sys.platform == "win32":
            try:
                import ctypes as _ctypes
                _oem_cp = _ctypes.windll.kernel32.GetOEMCP()
                _fallback_encoding = f'cp{_oem_cp}'
            except Exception:
                pass

        def _decode_line(raw_line):
            try:
                return raw_line.decode('utf-8')
            except UnicodeDecodeError:
                pass
            if _fallback_encoding:
                try:
                    return raw_line.decode(_fallback_encoding, errors='replace')
                except Exception:
                    pass
            return raw_line.decode('utf-8', errors='replace')

        try:
            kwargs = dict(shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          cwd=workdir)
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            agent_print("[Running — Ctrl+C to kill]\n")
            proc = subprocess.Popen(cmd, **kwargs)

            line_queue = _queue.Queue()

            def _reader():
                for raw_line in proc.stdout:
                    line = _decode_line(raw_line)
                    line_queue.put(line)
                line_queue.put(None)

            t = threading.Thread(target=_reader, daemon=True)
            t.start()

            output_lines = []
            last_output = time.time()
            interrupted = False
            try:
                while True:
                    try:
                        line = line_queue.get_nowait()
                    except _queue.Empty:
                        if proc.poll() is not None:
                            break
                        if time.time() - last_output > 30:
                            killed = True
                            agent_print("\n[Run timed out (30s idle) — killing]\n")
                            kill_proc_tree(proc)
                            proc.wait(timeout=5)
                            break
                        time.sleep(0.05)
                        continue
                    if line is None:
                        break
                    output_lines.append(line)
                    agent_print(line, end='')
                    sys.stdout.flush()
                    last_output = time.time()
            except KeyboardInterrupt:
                interrupted = True
                killed = True
                agent_print("\n[Killing process...]\n")
                kill_proc_tree(proc)
                proc.wait(timeout=5)

            t.join(timeout=2)
            while True:
                try:
                    line = line_queue.get_nowait()
                except _queue.Empty:
                    break
                if line is not None:
                    output_lines.append(line)

            if interrupted:
                raise KeyboardInterrupt

            combined = "".join(output_lines).strip()
            lines = combined.splitlines()
            if len(lines) > 60:
                combined = "\n".join(lines[-60:]) + f"\n[... trimmed, showing last 60 of {len(lines)} lines]"
            if killed:
                obs = f"[Run killed]\n{combined}" if combined else "[Run killed, no output]"
                agent_print("[Run killed]\n")
            else:
                rc = proc.returncode
                obs = f"[Run rc={rc}]\n{combined}" if combined else f"[Run rc={rc}, no output]"
                agent_print(f"[Run rc={rc}]\n")
            return obs
        except Exception as e:
            if proc and proc.poll() is None:
                kill_proc_tree(proc)
            msg = f"[Run failed: {e}]"
            agent_print(msg + "\n")
            return msg
