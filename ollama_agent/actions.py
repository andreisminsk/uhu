"""Action execution: WRITE, EDIT, RUN, FILE, TOOL blocks from LLM output."""

import json
import os
import queue as _queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from .constants import SAFE_SHELL_COMMANDS, SAFE_TOOLS, BLOCKED_COMMANDS, WARNING_COMMANDS
from .constants import SKIP_EXT
from .constants import MAX_OBSERVATION_CHARS, MAX_READ_OBSERVATION_CHARS, MAX_SKILL_OBSERVATION_CHARS, MAX_TOTAL_OBSERVATION_CHARS, MAX_CONSOLE_DISPLAY_CHARS, MAX_BATCH_WRITES
from .edit_utils import make_edit_summary, make_unified_diff
from .input_utils import read_full_input
from .matching import find_match_in_content
from .parser import parse_actions, _PATH_SIGNAL, _BASH_BLOCK
from .process import kill_proc_tree
from .skills.base import PromptOnlySkill


def _fix_win_backslash_quote(m):
    """Fix odd number of backslashes before a closing quote on Windows.

    In cmd.exe, \" is an escaped quote, so "C:\\path\\" is parsed as C:\\path"
    (invalid path). Remove one backslash from odd-length runs so the quote
    properly terminates the argument.
    """
    backslashes = m.group(1)
    if len(backslashes) % 2 == 1:
        return backslashes[:-1] + '"'
    return m.group(0)


class ActionMixin:
    """Action execution methods for ChatSession: WRITE, EDIT, RUN, FILE, TOOL."""

    # Names that are obviously placeholders, not real file paths or tool/skill names
    _PLACEHOLDER_NAMES = {"path", "name", "filepath", "filename", "file_path", "file_name", "skill", "skill_name"}

    # Shell operators that allow chaining multiple commands.
    # If any of these appear, the command is NOT auto-approved as safe.
    _SHELL_OPERATORS = re.compile(r'&&|\|\||[|;&]')

    # Patterns that are ALWAYS blocked — never executed.
    _BLOCKED_PATTERNS = [
        re.compile(r'\brm\s+-[rR].*\s+/\s*$', re.IGNORECASE),  # rm -rf /
        re.compile(r'\brm\s+-[rR].*\s+/\*', re.IGNORECASE),  # rm -rf /*
        re.compile(r'\bdd\s+if=', re.IGNORECASE),  # dd if=...
        re.compile(r'\bmkfs\b', re.IGNORECASE),  # mkfs
        re.compile(r'\bshutdown\b', re.IGNORECASE),  # shutdown
        re.compile(r'\breboot\b', re.IGNORECASE),  # reboot
        re.compile(r'\bpoweroff\b', re.IGNORECASE),  # poweroff
        re.compile(r'\bhalt\b', re.IGNORECASE),  # halt
        re.compile(r'\bformat\s+[A-Za-z]:', re.IGNORECASE),  # format C:
        re.compile(r'\bdel\s+/s\s+/q\s+[cC]:', re.IGNORECASE),  # del /s /q C:
        re.compile(r'\brmdir\s+/s\s+/q\s+[cC]:', re.IGNORECASE),  # rmdir /s /q C:
    ]

    # Base commands that always require explicit confirmation.
    _WARNING_BASE_COMMANDS_UNIX = {
        'rm', 'rmdir', 'chmod', 'chown', 'kill', 'killall',
        'apt', 'apt-get', 'yum', 'dnf', 'brew',
        'systemctl', 'service',
    }
    _WARNING_BASE_COMMANDS_WINDOWS = {
        'del', 'rmdir', 'taskkill', 'sc', 'net', 'netsh',
    }
    _WARNING_BASE_COMMANDS = _WARNING_BASE_COMMANDS_WINDOWS if sys.platform == 'win32' else _WARNING_BASE_COMMANDS_UNIX
    # Substrings that indicate destructive package/git operations
    _WARNING_SUBSTRINGS = {
        'pip uninstall', 'npm uninstall',
        'git push', 'git reset --hard', 'git clean',
    }

    def _check_command_safety(self, cmd):
        """Check a command for safety. Returns (level, message).
        level: 'blocked' — never execute
               'warning' — requires explicit confirmation even with auto-approve
               'chain'   — shell chaining detected, warn but allow with confirmation
               'safe'    — no issues
        """
        # Check blocked patterns
        for pat in self._BLOCKED_PATTERNS:
            if pat.search(cmd):
                return ('blocked', f"Command blocked for safety: {cmd[:80]}")

        # Check blocked commands (exact matches from constants)
        base = self._get_base_command(cmd)
        if base in BLOCKED_COMMANDS:
            return ('blocked', f"Command blocked for safety: {cmd[:80]}")

        # Check warning commands
        if base in WARNING_COMMANDS or base in self._WARNING_BASE_COMMANDS:
            return ('warning', f"⚠ Destructive command requires confirmation: {cmd[:80]}")
        for substr in self._WARNING_SUBSTRINGS:
            if substr in cmd.lower():
                return ('warning', f"⚠ Destructive command requires confirmation: {cmd[:80]}")

        # Check shell chaining operators
        if self._SHELL_OPERATORS.search(cmd):
            return ('chain', f"⚠ Shell chaining detected in: {cmd[:80]}")

        return ('safe', '')

    @staticmethod
    def _get_base_command(cmd):
        """Extract the base command name from a shell command string."""
        cmd = cmd.strip()
        if not cmd:
            return ""
        # Handle quoted executables: "C:\path\app.exe" args
        if cmd[0] == '"':
            end = cmd.find('"', 1)
            if end > 0:
                base = cmd[1:end]
            else:
                base = cmd[1:].split(None, 1)[0] if len(cmd) > 1 else ""
        else:
            base = cmd.split(None, 1)[0]
        # Get just the executable name without path
        base = os.path.basename(base).lower()
        # Remove common executable extensions
        for ext in ('.exe', '.cmd', '.bat', '.com'):
            if base.endswith(ext):
                base = base[:-len(ext)]
                break
        return base

    def _is_safe_command(self, cmd):
        """Check if a command is considered safe/read-only (no confirmation needed).

        Commands containing shell operators (&&, ||, |, &, ;) are never
        auto-approved, since a safe prefix like 'dir' could chain into a
        dangerous command like 'del /s *'.
        """
        if self._SHELL_OPERATORS.search(cmd):
            return False
        base = self._get_base_command(cmd)
        return base in SAFE_SHELL_COMMANDS

    def _show_diff_colored(self, diff_text):
        """Display a diff or detail text with color coding (green=+, red=-, cyan=hunks)."""
        if not diff_text or diff_text == "(no changes)":
            print("[No changes]\n")
            return
        # Enable ANSI escape codes on Windows
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.GetStdHandle(-11)
                mode = ctypes.c_ulong()
                kernel32.GetConsoleMode(handle, ctypes.byref(mode))
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            except Exception:
                pass
        use_color = sys.stdout.isatty()
        for line in diff_text.splitlines():
            if use_color:
                if line.startswith('+') and not line.startswith('+++'):
                    print(f"\033[32m{line}\033[0m")
                elif line.startswith('-') and not line.startswith('---'):
                    print(f"\033[31m{line}\033[0m")
                elif line.startswith('@@'):
                    print(f"\033[36m{line}\033[0m")
                elif line.startswith('+++') or line.startswith('---'):
                    print(f"\033[1m{line}\033[0m")
                else:
                    print(line)
            else:
                print(line)
        print()

    @staticmethod
    def _truncate_for_console(text, limit=MAX_CONSOLE_DISPLAY_CHARS):
        """Truncate text for console display, adding a note if truncated.

        The full text still goes into the observation (and gets truncated
        for context by MAX_OBSERVATION_CHARS / MAX_SKILL_OBSERVATION_CHARS),
        but only `limit` chars are shown on the terminal to prevent flooding.
        """
        if len(text) <= limit:
            return text
        return text[:limit] + f"\n[... {len(text)} chars total, truncated for display]"

    def _confirm_or_auto(self, prompt, path=None, cmd=None, diff_text=None, force_confirm=False):
        """Confirm an action with y/N/auto/all/d options.

        Press 'd' to see a diff or details before confirming.
        The prompt loops back after showing the diff.

        If force_confirm=True, skip auto-approve mechanisms (auto_all, skill, etc.)
        and require explicit user confirmation. Used for destructive commands.
        """
        while True:
            if not force_confirm and self.auto_all:
                print(f"[auto-all] {prompt}")
                return True
            if not force_confirm and self._skill_auto_approve:
                # Detect if this RUN is executing a skill script
                skill_hint = ""
                if cmd and ".skills/" in cmd:
                    # Extract skill name from path like .skills/category/skill-name/scripts/...
                    import re as _re
                    m = _re.search(r'\.skills/(?:[^/]+/)?([^/]+)/', cmd)
                    if m:
                        skill_hint = f" (skill: {m.group(1)})"
                print(f"[auto-skill{skill_hint}] {prompt}")
                return True
            if path and (path in self.auto_writes or path in self.always_writes):
                source = "always" if path in self.always_writes else "auto"
                print(f"[{source}-write: {path}] {prompt}")
                return True
            if cmd:
                for prefix in self.auto_run_prefixes | self.always_runs:
                    if cmd.strip() == prefix or cmd.strip().startswith(prefix + " "):
                        source = "always" if prefix in self.always_runs else "auto"
                        print(f"[{source}-run: {prefix}] {prompt}")
                        return True
            try:
                ans = read_full_input(f"{prompt} (y/N/auto/all/always/d): ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                return False
            if ans in ("y", "yes"):
                return True
            elif ans in ("n", "no"):
                return False
            elif ans == "auto":
                if path:
                    self.auto_writes.add(path)
                    print(f"[Auto-write: {path} — auto-approved this session]\n")
                elif cmd:
                    self.auto_run_prefixes.add(cmd.strip())
                    print(f"[Auto-run: {cmd.strip()} — auto-approved this session]\n")
                return True
            elif ans == "always":
                if path:
                    self.always_writes.add(path)
                    self.auto_writes.add(path)
                    self._save_coder_config()
                    print(f"[Always-write: {path} — auto-approved in all future sessions]\n")
                elif cmd:
                    self.always_runs.add(cmd.strip())
                    self.auto_run_prefixes.add(cmd.strip())
                    self._save_coder_config()
                    print(f"[Always-run: {cmd.strip()} — auto-approved in all future sessions]\n")
                return True
            elif ans == "all":
                self.auto_all = True
                print("[Auto-all enabled — all actions auto-approved this session]\n")
                return True
            elif ans in ("d", "diff"):
                if diff_text:
                    self._show_diff_colored(diff_text)
                else:
                    print("[No details available for this action]\n")
                continue
            return False

    # ── Persistent config ────────────────────────────────────────────────

    def _coder_config_path(self):
        """Return the path to the project's persistent auto-approval config."""
        return os.path.join(self.workdir, ".uhu", "coderconfig.json")

    def _load_coder_config(self):
        """Load persistent auto-approval settings from .uhu/coderconfig.json.

        Settings stored here survive across sessions, so the user doesn't
        have to re-approve the same files/commands every time.
        """
        config_path = self._coder_config_path()
        if not os.path.isfile(config_path):
            return
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            for path in config.get("always_writes", []):
                self.always_writes.add(path)
            for prefix in config.get("always_runs", []):
                self.always_runs.add(prefix)
            n_writes = len(self.always_writes)
            n_runs = len(self.always_runs)
            if n_writes or n_runs:
                parts = []
                if n_writes:
                    parts.append(f"{n_writes} always-write path(s)")
                if n_runs:
                    parts.append(f"{n_runs} always-run command(s)")
                print(f"[Loaded {config_path}: {', '.join(parts)}]")
        except Exception:
            pass

    def _save_coder_config(self):
        """Save persistent auto-approval settings to .uhu/coderconfig.json."""
        config_path = self._coder_config_path()
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            config = {
                "always_writes": sorted(self.always_writes),
                "always_runs": sorted(self.always_runs),
            }
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ── File caching ────────────────────────────────────────────────────

    def _cache_file(self, path, content):
        """Save a copy of file content to .uhu/.cache/ and return a file:: URL.

        Creates the .uhu/.cache/ directory mirroring the project structure.
        Each cache write gets an incrementing numeric suffix before the extension
        (e.g. README.1.md, README.2.md) so multiple versions are preserved.
        Returns the file:// URL, or None if caching is disabled or fails (non-critical).
        """
        if not self.cache_files:
            return None
        cache_dir = os.path.join(self.workdir, ".uhu", ".cache")
        if os.path.isabs(path):
            try:
                rel_path = os.path.relpath(path, self.workdir)
            except ValueError:
                rel_path = os.path.basename(path)
        else:
            rel_path = path
        # Find next available numeric suffix: name.1.ext, name.2.ext, ...
        base, ext = os.path.splitext(rel_path)
        n = 1
        while True:
            suffixed_rel = f"{base}.{n}{ext}" if ext else f"{rel_path}.{n}"
            cache_path = os.path.join(cache_dir, suffixed_rel)
            if not os.path.exists(cache_path):
                break
            n += 1
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            return None
        # Use pathlib for correct URL encoding (spaces, #, non-ASCII),
        # UNC path handling, and platform-appropriate format
        return Path(cache_path).resolve().as_uri()

    # ── Pre-edit tracking and rollback ──────────────────────────────────

    def _save_pre_edit(self, path, pre_edit_content):
        """Save file content before modification for potential rollback.

        Stores the original content in memory keyed by path.
        Only saves the first version (before any edits in this batch).
        """
        if not hasattr(self, '_pre_edit_snapshots'):
            self._pre_edit_snapshots = {}
        if path not in self._pre_edit_snapshots:
            self._pre_edit_snapshots[path] = pre_edit_content

    def _rollback_edits(self, modified, created):
        """Restore files to their pre-edit state and remove newly created files.

        Uses in-memory snapshots saved by _save_pre_edit() before modifications.
        """
        for path in modified:
            if path in self._pre_edit_snapshots:
                full_path = os.path.join(self.workdir, path) if not os.path.isabs(path) else path
                os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(self._pre_edit_snapshots[path])
        for path in created:
            full_path = os.path.join(self.workdir, path) if not os.path.isabs(path) else path
            if os.path.isfile(full_path):
                try:
                    os.remove(full_path)
                except OSError:
                    pass


    # ── Action execution ──────────────────────────────────────────────

    def execute_write(self, action):
        path = action["path"]
        lines = action["code"].count("\n") + 1
        full_path = os.path.join(self.workdir, path) if not os.path.isabs(path) else path
        # Compute diff for on-demand review (d at prompt)
        diff_text = None
        new_content = action["code"]
        if not new_content.endswith("\n"):
            new_content += "\n"
        if os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    old_content = f.read()
                diff_text = make_unified_diff(path, old_content, new_content)
            except Exception:
                pass
        else:
            diff_text = make_unified_diff(path, "", new_content)
        if not self._confirm_or_auto(f"[WRITE] {path} ({lines} lines)", path=path, diff_text=diff_text):
            print("[Skipped]\n")
            return None
        try:
            os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            file_url = self._cache_file(path, new_content)
            obs = f"[Wrote: {path} ({lines} lines)]"
            display_msg = obs
            if file_url:
                display_msg += f" (cached: {file_url})"
            print(display_msg + "\n")
            return obs
        except Exception as e:
            msg = f"[Write failed: {e}]"
            print(msg + "\n")
            return msg

    def execute_edit(self, action):
        path = action["path"]
        edits = action["edits"]
        full_path = os.path.join(self.workdir, path) if not os.path.isabs(path) else path

        if not os.path.isfile(full_path):
            # Try to find the file by basename in the project
            basename = os.path.basename(path)
            suggestion = ""
            for root, dirs, files in os.walk(self.workdir):
                dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', '.cache', '.uhu', 'build', '.gradle'}]
                if basename in files:
                    found = os.path.relpath(os.path.join(root, basename), self.workdir)
                    suggestion = f" Did you mean {found!r}?"
                    break
            msg = f"[EDIT FAILED: {path} does not exist. Use WRITE for new files.{suggestion}]"
            print(msg + "\n")
            return msg

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                original_content = f.read()
        except Exception as e:
            msg = f"[EDIT FAILED: cannot read {path}: {e}]"
            print(msg + "\n")
            return msg

        if not edits:
            msg = f"[EDIT FAILED: {path} — no valid search/replace blocks found]"
            print(msg + "\n")
            return msg

        current_content = original_content
        edits_applied = []
        failures = []

        for search_text, replace_text in edits:
            match = find_match_in_content(current_content, search_text)
            if match is None:
                failures.append(search_text)
                continue
            start, end, quality = match
            file_lines = current_content.split('\n')
            new_lines = file_lines[:start] + replace_text.split('\n') + file_lines[end:]
            current_content = '\n'.join(new_lines)
            edits_applied.append((start, end, quality, search_text, replace_text))

        if not edits_applied:
            snippet_lines = original_content.split('\n')[:20]
            snippet = '\n'.join(snippet_lines)
            if len(snippet_lines) < len(original_content.split('\n')):
                snippet += f"\n... ({len(original_content.split(chr(10)))} lines total)"
            msg = f"[EDIT FAILED: {path} — search text not found]\nFile content:\n{snippet}"
            print(msg + "\n")
            return msg

        if failures:
            failed_snippets = []
            for i, f_text in enumerate(failures):
                preview = f_text[:80].replace('\n', '\\n')
                failed_snippets.append(f"  {i+1}. ...{preview}...")
            msg = (
                f"[EDIT FAILED: {path} — {len(failures)} of {len(edits)} search block(s) not found. "
                f"File left unchanged.]\n"
                f"Missing search blocks:\n" + '\n'.join(failed_snippets)
            )
            print(msg + "\n")
            return msg

        summary = make_edit_summary(path, edits_applied)
        print(summary)

        diff_text = make_unified_diff(path, original_content, current_content)
        if self.show_diff:
            self._show_diff_colored(diff_text)

        if not self._confirm_or_auto(f"Apply {len(edits_applied)} edit(s) to {path}?", path=path, diff_text=diff_text):
            print("[Skipped]\n")
            return None

        try:
            os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(current_content)
            total_lines = current_content.count('\n') + 1
            obs = f"[Edited: {path} ({len(edits_applied)} change(s) applied, {total_lines} lines)]"
            if failures:
                warning = f"\n[WARNING: {len(failures)} search block(s) not found]"
                obs += warning
            print(obs + "\n")
            return obs
        except Exception as e:
            msg = f"[Edit failed: {e}]"
            print(msg + "\n")
            return msg

    def execute_run(self, action):
        cmd = action["code"]

        # Rewrite short script paths to their full workdir-relative paths.
        # The LLM may generate "python scripts/fetch_news.py" instead of
        # "python .skills/media/newsfeed/scripts/fetch_news.py".
        # This now uses a global registry lookup so it works even when
        # _active_skill is not set (e.g., across continuation rounds).
        from .skills import find_script_in_cmd
        script_replacements = find_script_in_cmd(cmd, workdir=self.workdir)
        for matched_text, resolved_path in script_replacements:
            # Only replace if the resolved path is different (avoid double-replacing)
            if matched_text != resolved_path:
                cmd = cmd.replace(matched_text, resolved_path)

        # On Windows cmd.exe, a backslash before a closing quote escapes the quote:
        #   dir "C:\path\"  →  path parsed as C:\path"  →  WinError 267
        # When an odd number of \ precedes ", the last \ escapes the quote.
        # Fix by removing one \ so the quote properly closes the argument:
        #   "C:\path\"  →  "C:\path"  (same directory, valid syntax)
        if sys.platform == "win32":
            cmd = re.sub(r'(\\+)"', _fix_win_backslash_quote, cmd)
        cmd_details = f"[Command details]\n  cwd: {self.workdir}\n  cmd: {cmd}"
        ell = '…' if len(cmd) > 80 else ''

        # Safety checks
        safety_level, safety_msg = self._check_command_safety(cmd)
        if safety_level == 'blocked':
            print(f"⛔ {safety_msg}\n")
            return None
        if safety_level == 'warning':
            # Destructive command — always require explicit confirmation, bypass auto-approve
            print(f"{safety_msg}")
            if not self._confirm_or_auto(f"[CONFIRM DESTRUCTIVE] {cmd[:80]}{ell}", cmd=cmd, diff_text=cmd_details, force_confirm=True):
                print("[Skipped]\n")
                return None
        elif safety_level == 'chain':
            # Shell chaining detected — warn but allow with confirmation
            print(f"{safety_msg}")
            if not self._confirm_or_auto(f"[RUN] {cmd[:80]}{ell}", cmd=cmd, diff_text=cmd_details):
                print("[Skipped]\n")
                return None
        elif self._is_safe_command(cmd):
            base = self._get_base_command(cmd)
            print(f"[auto-safe: {base}] [RUN] {cmd[:80]}{ell}")
        elif not self._confirm_or_auto(f"[RUN] {cmd[:80]}{ell}", cmd=cmd, diff_text=cmd_details):
            print("[Skipped]\n")
            return None
        proc = None
        killed = False

        # Determine fallback encoding for Windows subprocess output.
        # On non-English Windows (e.g. Russian cp866), programs like
        # PowerShell and cmd.exe output text in the OEM codepage, not
        # UTF-8. Decoding as UTF-8 produces garbled text. We try UTF-8
        # first (most modern programs), and fall back to the OEM codepage
        # if UTF-8 produces too many replacement characters.
        _fallback_encoding = None
        if sys.platform == "win32":
            try:
                import ctypes as _ctypes
                _oem_cp = _ctypes.windll.kernel32.GetOEMCP()
                _fallback_encoding = f'cp{_oem_cp}'
            except Exception:
                pass

        def _decode_line(raw_line):
            """Decode subprocess output.

            Try strict UTF-8 first — if it decodes cleanly, the output is UTF-8.
            If it fails (as OEM-encoded bytes will), fall back to the OEM codepage
            (e.g. cp866 on Russian Windows). This avoids garbling OEM output by
            silently replacing high bytes with U+FFFD instead of raising an error.
            """
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
            # Read in binary mode and decode manually — this avoids
            # UnicodeDecodeError from TextIOWrapper on invalid bytes (e.g. 0xAD
            # from Windows-1252 output).  bytes.decode(errors='replace') never
            # raises, unlike TextIOWrapper iteration which can.
            kwargs = dict(shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          cwd=self.workdir)
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            print("[Running — Ctrl+C to kill]\n")
            proc = subprocess.Popen(cmd, **kwargs)

            line_queue = _queue.Queue()

            def _reader():
                for raw_line in proc.stdout:
                    line = _decode_line(raw_line)
                    line_queue.put(line)
                line_queue.put(None)  # sentinel

            t = threading.Thread(target=_reader, daemon=True)
            t.start()

            output_lines = []
            last_output = time.time()
            interrupted = False
            try:
                while True:
                    try:
                        # Use get_nowait() + time.sleep() instead of get(timeout=...).
                        # On Windows, queue.get(timeout=N) blocks inside WaitForSingleObjectEx
                        # which does not wake up for SIGINT, swallowing Ctrl+C silently.
                        # time.sleep() IS interruptible on Windows.
                        line = line_queue.get_nowait()
                    except _queue.Empty:
                        if proc.poll() is not None:
                            break
                        if time.time() - last_output > 30:
                            killed = True
                            print("\n[Run timed out (30s idle) — killing]\n")
                            kill_proc_tree(proc)
                            proc.wait(timeout=5)
                            break
                        time.sleep(0.05)  # interruptible on Windows
                        continue
                    if line is None:
                        break
                    output_lines.append(line)
                    print(line, end='')
                    sys.stdout.flush()
                    last_output = time.time()
            except KeyboardInterrupt:
                interrupted = True
                killed = True
                print("\n[Killing process...]\n")
                kill_proc_tree(proc)
                proc.wait(timeout=5)

            t.join(timeout=2)
            # Drain any remaining lines
            while True:
                try:
                    line = line_queue.get_nowait()
                except _queue.Empty:
                    break
                if line is not None:
                    output_lines.append(line)

            # Re-raise KeyboardInterrupt AFTER the process is dead and output
            # is drained. Without this, Ctrl+C only kills the subprocess but
            # execution continues into _feedback_loop, silently swallowing the
            # interrupt and starting another model call.
            if interrupted:
                raise KeyboardInterrupt

            combined = "".join(output_lines).strip()
            lines = combined.splitlines()
            if len(lines) > 60:
                combined = "\n".join(lines[-60:]) + f"\n[... trimmed, showing last 60 of {len(lines)} lines]"
            if killed:
                obs = f"[Run killed]\n{combined}" if combined else "[Run killed, no output]"
                print("[Run killed]\n")
            else:
                rc = proc.returncode
                obs = f"[Run rc={rc}]\n{combined}" if combined else f"[Run rc={rc}, no output]"
                print(f"[Run rc={rc}]\n")
            return obs
        except Exception as e:
            if proc and proc.poll() is None:
                kill_proc_tree(proc)
            msg = f"[Run failed: {e}]"
            print(msg + "\n")
            return msg

    def execute_read(self, action):
        """Read a file and return its content as an observation for the model."""
        path = action["path"]
        full_path = os.path.join(self.workdir, path) if not os.path.isabs(path) else path
        if not os.path.isfile(full_path):
            msg = f"[READ FAILED: {path} does not exist]"
            print(msg + "\n")
            return msg
        ext = os.path.splitext(path)[1].lower()
        if ext in SKIP_EXT:
            msg = f"[READ FAILED: {path} — binary/skipped extension ({ext})]"
            print(msg + "\n")
            return msg
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            msg = f"[READ FAILED: {path}: {e}]"
            print(msg + "\n")
            return msg
        lines_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        # Cache the full content before truncation so file:// URL points to complete file
        file_url = self._cache_file(path, content)
        # Truncate if very large — cap per-file to half the context window (leaves room for conversation)
        max_chars = min(self.ctx_size // 2, 200000)
        truncated = ""
        if len(content) > max_chars:
            content = content[:max_chars]
            truncated = " (truncated)"
        url_info = f", cached: {file_url}" if file_url else ""
        print(f"[Read: {path} ({lines_count} lines{truncated}{url_info})]")
        # Print file content to terminal so the user can see it
        max_display_lines = 200
        content_lines = content.split('\n')
        if len(content_lines) > max_display_lines:
            for line in content_lines[:max_display_lines]:
                print(line)
            print(f"... ({len(content_lines) - max_display_lines} more lines)")
        else:
            print(content)
        print()
        # Observation sent to model: only the relative path, no cache URL
        # (cache URLs confuse the model about the working directory)
        obs = f"[File: {path}]\n{content}"
        self._log("system", f"[Read: {path} ({lines_count} lines{truncated}{url_info})]")
        return obs

    def execute_tool(self, action):
        """Execute a tool invocation action."""
        from .tools import get as get_tool, all_tools
        tool_name = action["name"]
        params = action.get("params", {})
        tool = get_tool(tool_name)
        if not tool:
            # Fuzzy match: try to find a similar tool name
            all_tool_names = [t.name for t in all_tools()]
            close_match = None
            # 1. Exact match after singular/plural (e.g. list_file → list_files)
            for candidate_name in all_tool_names:
                if tool_name + "s" == candidate_name or tool_name.rstrip("s") == candidate_name.rstrip("s"):
                    close_match = candidate_name
                    break
            # 2. Underscore vs hyphen (e.g. web-search → web_search)
            if not close_match:
                normalized = tool_name.replace("-", "_")
                for candidate_name in all_tool_names:
                    if normalized == candidate_name.replace("-", "_"):
                        close_match = candidate_name
                        break
            if close_match:
                tool = get_tool(close_match)
                print(f"[Auto-corrected tool name: '{tool_name}' → '{close_match}']")
                tool_name = close_match
            else:
                # Common confusion: model emits **TOOL:`some-file.py`** thinking
                # it reads a file. If the name looks like a file (has an extension)
                # and actually exists in workdir, return a friendly hint instead of
                # a generic "Unknown tool" error.
                if "." in tool_name and not tool_name.endswith("()"):
                    candidate = os.path.join(self.workdir, tool_name) if not os.path.isabs(tool_name) else tool_name
                    if os.path.isfile(candidate):
                        msg = (
                            f"[TOOL FAILED: Unknown tool '{tool_name}' — this looks like a file path, not a tool name. "
                            f"To read a file's contents into context, use **FILE:`{tool_name}`** "
                            f"(closed by **EOF:`{tool_name}`**) instead of **TOOL:`{tool_name}`**.]"
                        )
                        print(msg + "\n")
                        return msg
                msg = f"[TOOL FAILED: Unknown tool '{tool_name}']"
                print(msg + "\n")
                return msg
        params_preview = json.dumps(params, ensure_ascii=False)
        if len(params_preview) > 60:
            params_preview = params_preview[:57] + "..."
        # Safety check for run_command tool — block/warn on dangerous commands
        if tool_name == "run_command":
            cmd = params.get("command", "")
            safety_level, safety_msg = self._check_command_safety(cmd)
            if safety_level == 'blocked':
                print(f"⛔ {safety_msg}\n")
                return None
            if safety_level == 'warning':
                print(f"{safety_msg}")
                params_details = f"[Tool details]\n  name: {tool_name}\n  params:\n{json.dumps(params, indent=4, ensure_ascii=False)}"
                if not self._confirm_or_auto(f"[CONFIRM DESTRUCTIVE] {tool_name}({params_preview})", cmd=cmd, diff_text=params_details, force_confirm=True):
                    print("[Skipped]\n")
                    return None
            elif safety_level == 'chain':
                print(f"{safety_msg}")
                params_details = f"[Tool details]\n  name: {tool_name}\n  params:\n{json.dumps(params, indent=4, ensure_ascii=False)}"
                if not self._confirm_or_auto(f"[TOOL] {tool_name}({params_preview})", cmd=cmd, diff_text=params_details):
                    print("[Skipped]\n")
                    return None

        # Auto-approve safe tools (read-only, no side effects)
        if tool_name in SAFE_TOOLS:
            print(f"[auto-safe: {tool_name}] [TOOL] {tool_name}({params_preview})")
        else:
            params_details = f"[Tool details]\n  name: {tool_name}\n  params:\n{json.dumps(params, indent=4, ensure_ascii=False)}"
            if not self._confirm_or_auto(f"[TOOL] {tool_name}({params_preview})", cmd=tool_name, diff_text=params_details):
                print("[Skipped]\n")
                return None
        # Check for missing required parameters
        if not params:
            required = [k for k, v in tool.parameters.items() if v.get("required", False)]
            if required:
                param_hint = ", ".join(f'"{r}": ...' for r in required)
                msg = (
                    f"[TOOL FAILED: {tool_name} — missing required parameters: {', '.join(required)}. "
                    f"Use: **TOOL:`{tool_name}`** then a ```json block with "
                    f"{{{param_hint}}}, then **EOF:`{tool_name}`**]"
                )
                print(msg + "\n")
                return msg
        try:
            result = tool.execute(params, workdir=self.workdir)
            msg = f"[TOOL {tool_name}]: {result}"
            print(self._truncate_for_console(msg) + "\n")
            return msg
        except Exception as e:
            msg = f"[TOOL FAILED: {tool_name}: {e}]"
            print(msg + "\n")
            return msg

    def execute_skill(self, action):
        """Execute a skill invocation action."""
        from .skills import get as get_skill
        skill_name = action["name"]
        params = action.get("params", {})
        skill = get_skill(skill_name)
        if not skill:
            msg = f"[SKILL FAILED: Unknown skill '{skill_name}']"
            print(msg + "\n")
            return msg
        params_preview = json.dumps(params, ensure_ascii=False)
        if len(params_preview) > 60:
            params_preview = params_preview[:57] + "..."
        params_details = f"[Skill details]\n  name: {skill_name}\n  description: {skill.description}\n  params:\n{json.dumps(params, indent=4, ensure_ascii=False)}"
        if hasattr(skill, 'scripts') and skill.scripts:
            script_list = ", ".join(skill.scripts.keys())
            params_details += f"\n  scripts: {script_list}"
            # Validate scripts exist and show resolved paths
            if hasattr(skill, 'validate_scripts'):
                validation = skill.validate_scripts(workdir=self.workdir)
                missing = [(sn, sp) for sn, sp, ex in validation if not ex]
                if missing:
                    missing_desc = ", ".join(f"{sn} ({sp})" for sn, sp in missing)
                    params_details += f"\n  ⚠ MISSING SCRIPTS: {missing_desc}"
        if not self._confirm_or_auto(f"[SKILL] {skill_name}({params_preview})", cmd=skill_name, diff_text=params_details):
            print("[Skipped]\n")
            return None
        # Skill approved — auto-approve subsequent actions in this skill's workflow
        self._skill_auto_approve = True
        self._active_skill = skill
        # Show explicit skill invocation indicator
        skill_type = "prompt-only" if isinstance(skill, PromptOnlySkill) else "markdown"
        desc_preview = skill.description[:80] + "..." if len(skill.description) > 80 else skill.description
        print(f"\n{'='*60}")
        print(f"⚡ SKILL INVOKED: {skill_name} ({skill_type})")
        print(f"  Description: {desc_preview}")
        if params:
            param_items = ", ".join(f"{k}={v!r}" for k, v in params.items())
            print(f"  Params: {param_items}")
        if hasattr(skill, 'scripts') and skill.scripts:
            # Show resolved workdir-relative paths
            resolved_scripts = []
            for sn in skill.scripts:
                if hasattr(skill, 'resolve_script_path'):
                    rp = skill.resolve_script_path(sn, workdir=self.workdir)
                    resolved_scripts.append(f"{sn} → {rp}" if rp else f"{sn} [MISSING]")
                else:
                    resolved_scripts.append(sn)
            print(f"  Scripts: {', '.join(resolved_scripts)}")
        print(f"{'='*60}\n")
        try:
            result = skill.execute(params, workdir=self.workdir, session=self)
            print(f"\n{'─'*60}")
            print(f"⚡ SKILL RESULT: {skill_name} ({skill_type})")
            print(self._truncate_for_console(result))
            print(f"{'─'*60}\n")
            msg = f"⚡ [SKILL {skill_name} ({skill_type})]: {result}"
            return msg
        except Exception as e:
            print(f"\n{'─'*60}")
            print(f"⚡ SKILL FAILED: {skill_name}: {e}")
            print(f"{'─'*60}\n")
            msg = f"[SKILL FAILED: {skill_name}: {e}]"
            return msg

    def process_actions(self, response_text):
        if not self.agent and not self.tools and not self.skills:
            if _PATH_SIGNAL.search(response_text) or _BASH_BLOCK.search(response_text):
                print("[hint: response contains **WRITE:**/**EDIT:**/**TOOL:**/**SKILL:** blocks -- add --agent, --tools, and/or --skills to execute them]\n")
            return (None, False, False, False)
        actions = parse_actions(response_text)
        if not actions:
            # Check if the model wrote signal lines but with incomplete format
            if _PATH_SIGNAL.search(response_text):
                return ("[SYSTEM WARNING: Tool/action signal detected but block format is incomplete. "
                        "For TOOL blocks, use: **TOOL:`tool_name`** then a ```json block with params, then **EOF:`tool_name`**. "
                        "For RUN blocks, use **RUN:** then a ```cmd (or bash/powershell) block with the command. "
                        "Do NOT write bare signal lines without content blocks.]", False, False, False)
            return (None, False, False, False)
        modified = set()
        created = set()
        observations = []
        missing_eof_paths = []
        user_cancelled_run = False
        has_executed_non_read = False
        has_executed_skill = False
        total_read_chars = 0
        max_total_read_chars = min(self.ctx_size, 200000)
        placeholder_warnings = []
        write_count = 0
        batch_limited = False
        for action in actions:
            action_path = action.get("path") or action.get("name")
            if action_path and action_path.lower().strip() in self._PLACEHOLDER_NAMES:
                placeholder_warnings.append(
                    f"[SYSTEM WARNING: {action['type'].upper()} block uses placeholder '{action_path}' "
                    f"instead of a real file path or tool name. "
                    f"Use actual values like **{action['type'].upper()}:`src/app.py`**]"
                )
                continue
            if action["type"] == "write":
                if batch_limited:
                    observations.append(f"[Deferred: WRITE {action['path']} — batch write limit ({MAX_BATCH_WRITES}) reached, will continue next round]")
                    if not action.get("closed"):
                        missing_eof_paths.append(action["path"])
                    continue
                if not self.agent:
                    observations.append(f"[Skipped: WRITE {action['path']} — add --agent to execute]")
                    continue
                path = action["path"]
                if path not in modified and path not in created:
                    full_path = os.path.join(self.workdir, path) if not os.path.isabs(path) else path
                    if os.path.isfile(full_path):
                        try:
                            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                                self._save_pre_edit(path, f.read())
                            modified.add(path)
                        except Exception:
                            modified.add(path)
                    else:
                        created.add(path)
                obs = self.execute_write(action)
                if obs is None:
                    observations.append(f"[Skipped: WRITE {action['path']}]")
                else:
                    has_executed_non_read = True
                    write_count += 1
                    if write_count >= MAX_BATCH_WRITES:
                        batch_limited = True
                if not action.get("closed"):
                    missing_eof_paths.append(action["path"])
            elif action["type"] == "edit":
                if batch_limited:
                    observations.append(f"[Deferred: EDIT {action['path']} — batch write limit ({MAX_BATCH_WRITES}) reached, will continue next round]")
                    if not action.get("closed"):
                        missing_eof_paths.append(action["path"])
                    continue
                if not self.agent:
                    observations.append(f"[Skipped: EDIT {action['path']} — add --agent to execute]")
                    continue
                path = action["path"]
                if path not in modified and path not in created:
                    full_path = os.path.join(self.workdir, path) if not os.path.isabs(path) else path
                    if os.path.isfile(full_path):
                        try:
                            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                                self._save_pre_edit(path, f.read())
                            modified.add(path)
                        except Exception:
                            modified.add(path)
                obs = self.execute_edit(action)
                if obs is None:
                    observations.append(f"[Skipped: EDIT {action['path']}]")
                else:
                    has_executed_non_read = True
                    write_count += 1
                    if write_count >= MAX_BATCH_WRITES:
                        batch_limited = True
                if not action.get("closed"):
                    missing_eof_paths.append(action["path"])
            elif action["type"] == "read":
                if total_read_chars >= max_total_read_chars:
                    observations.append(f"[Skipped: READ {action['path']} — total read size limit ({max_total_read_chars} chars) reached]")
                    if not action.get("closed"):
                        missing_eof_paths.append(action["path"])
                    continue
                if not self.agent:
                    observations.append(f"[Skipped: READ {action['path']} — add --agent to execute]")
                    if not action.get("closed"):
                        missing_eof_paths.append(action["path"])
                    continue
                obs = self.execute_read(action)
                if obs:
                    total_read_chars += len(obs)
                    if total_read_chars > max_total_read_chars:
                        excess = total_read_chars - max_total_read_chars
                        obs = obs[:-excess] + "\n[... truncated to fit read size limit]"
                        total_read_chars = max_total_read_chars
                if not action.get("closed"):
                    missing_eof_paths.append(action["path"])
            elif action["type"] == "tool":
                if not self.tools:
                    observations.append(f"[Skipped: TOOL {action['name']} — add --tools to execute]")
                    continue
                obs = self.execute_tool(action)
                if obs is None:
                    observations.append(f"[Skipped: TOOL {action['name']}]")
                else:
                    has_executed_non_read = True
                if not action.get("closed"):
                    missing_eof_paths.append(action["name"])
            elif action["type"] == "skill":
                if not self.skills:
                    observations.append(f"[Skipped: SKILL {action['name']} — add --skills to execute]")
                    continue
                obs = self.execute_skill(action)
                if obs is None:
                    observations.append(f"[Skipped: SKILL {action['name']}]")
                else:
                    has_executed_skill = True
                if not action.get("closed"):
                    missing_eof_paths.append(action["name"])
            else:
                if not self.agent:
                    cmd_preview = action["code"][:60]
                    observations.append(f"[Skipped: RUN {cmd_preview} — add --agent to execute]")
                    continue
                obs = self.execute_run(action)
                if obs is None:
                    user_cancelled_run = True
                    cmd_preview = action["code"][:60]
                    observations.append(f"[Skipped: RUN {cmd_preview}]")
                else:
                    has_executed_non_read = True
                    # Suggest FILE: for failed file-reading commands
                    cmd = action["code"].strip()
                    cmd_base = self._get_base_command(cmd).lower()
                    if cmd_base in ('type', 'cat', 'less', 'more', 'head', 'tail'):
                        run_failed = (
                            obs.startswith('[Run failed:') or
                            obs.startswith('[Run killed]') or
                            (obs.startswith('[Run rc=') and not obs.startswith('[Run rc=0]'))
                        )
                        if run_failed:
                            parts = cmd.split(None, 1)
                            if len(parts) > 1:
                                file_path = parts[1].strip().strip('"').strip("'")
                                # Remove trailing arguments (e.g., "type file.txt | more")
                                if ' ' in file_path and os.path.sep not in file_path and not file_path.startswith('-'):
                                    first_token = file_path.split()[0]
                                    if '.' in first_token or os.path.sep in first_token:
                                        file_path = first_token
                                obs += (
                                    f"\n[Tip: Use **FILE:**`{file_path}` with **EOF:**`{file_path}` "
                                    f"to read files directly — more reliable than RUN: {cmd_base}]"
                                )
            if obs:
                observations.append(obs)
                if action["type"] in ("write", "edit") and ("FAILED" in obs or "failed" in obs):
                    if modified or created:
                        n_modified = len(modified)
                        n_created = len(created)
                        self._rollback_edits(modified, created)
                        msg = f"[Rolled back {n_modified} modified, {n_created} created file(s) after {action['type']} failure]"
                        print(msg + "\n")
                        observations.append(msg)
                    break
        if missing_eof_paths:
            observations.append(
                f"[SYSTEM WARNING: Missing **EOF:** markers for: {', '.join(missing_eof_paths)}. "
                f"Always conclude file blocks with **EOF:`filename`** (using the same path as the opening marker) to prevent truncation or merging.]"
            )
        if batch_limited:
            note = f"[Batch write limit reached ({MAX_BATCH_WRITES} file changes per round). Remaining WRITE/EDIT actions deferred — continue with them in your next response.]"
            print(note + "\n")
            observations.append(note)
        if placeholder_warnings:
            for w in placeholder_warnings:
                print(w + "\n")
            observations.extend(placeholder_warnings)
        # Truncate large observations to prevent context bloat.
        # Context is precious — raw HTML, verbose tool output, and skill reference
        # content can easily consume the entire context window.
        # Skill and tool observations get much more aggressive truncation since
        # they are intermediate/automated output, not directly requested by the user.
        # The full output is already printed to the terminal — only the context
        # copy is shortened.
        truncated = []
        for obs in observations:
            # Skill/tool observations: aggressive truncation (intermediate output)
            is_skill_or_tool = obs.startswith(("⚡ [SKILL", "[SKILL", "[TOOL"))
            # Read observations: generous limit (agent needs full source code)
            is_read = obs.startswith("[File:")
            if is_skill_or_tool:
                limit = MAX_SKILL_OBSERVATION_CHARS
            elif is_read:
                limit = MAX_READ_OBSERVATION_CHARS
            else:
                limit = MAX_OBSERVATION_CHARS
            if len(obs) > limit:
                trunc_note = f"\n[... truncated, {len(obs)} chars total — use FILE: or TOOL: for full content]"
                truncated.append(obs[:limit] + trunc_note)
            else:
                truncated.append(obs)
        result = "\n".join(truncated) if truncated else None
        if result and len(result) > MAX_TOTAL_OBSERVATION_CHARS:
            trunc_note = f"\n[... total truncated, {len(result)} chars — use FILE: or TOOL: for full content]"
            result = result[:MAX_TOTAL_OBSERVATION_CHARS] + trunc_note
            print(f"[Observations truncated to conserve context ({MAX_TOTAL_OBSERVATION_CHARS} char limit)]")
        return (result, user_cancelled_run, has_executed_non_read, has_executed_skill)
