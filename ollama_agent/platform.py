"""Platform abstraction for terminal, process, and shell operations.

Provides a unified TerminalBackend interface with Win32 and POSIX implementations,
eliminating scattered sys.platform checks across modules. POSIX backend handles
both Linux and macOS with shell auto-detection.
"""

import os
import re
import shutil
import subprocess
import sys


# ── Platform detection ─────────────────────────────────────────────────

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_POSIX = not IS_WINDOWS


def _detect_shell():
    """Detect the user's login shell (zsh, bash, sh, etc.)."""
    if IS_WINDOWS:
        return "cmd"
    # Check $SHELL first
    shell = os.environ.get("SHELL", "")
    if shell:
        return os.path.basename(shell)
    # Fallback: check /etc/shells or default
    if IS_MACOS:
        return "zsh"
    return "bash"


def _detect_platform_label():
    if IS_WINDOWS:
        return "win32"
    if IS_MACOS:
        return "macOS"
    return sys.platform


def _detect_shell_label():
    if IS_WINDOWS:
        return "cmd/powershell"
    shell = _detect_shell()
    if shell in ("zsh", "bash"):
        return f"{shell}/sh"
    return f"{shell}/sh"


def _detect_shell_lang():
    if IS_WINDOWS:
        return "cmd"
    return _detect_shell()


# ── Base backend ───────────────────────────────────────────────────────

class TerminalBackend:
    """Abstract terminal/platform operations backend.

    Subclasses provide platform-specific implementations for:
    - ANSI escape code enablement
    - Terminal echo control
    - Paste detection and buffered char reading
    - Subprocess creation flags
    - Process tree killing
    - Encoding fallback for subprocess output
    - Safe/blocked/warning command sets
    - Shell guidance for the system prompt
    """

    is_windows = False
    is_macos = False
    is_posix = False

    platform_label = ""
    shell_label = ""
    shell_lang = ""

    # ── ANSI / display ──────────────────────────────────────────────

    def enable_ansi(self):
        """Enable ANSI escape code processing in the terminal."""
        pass  # no-op on POSIX (native support)

    supports_bracketed_paste = False

    def enable_bracketed_paste(self):
        """Enable bracketed paste mode (deterministic paste detection)."""
        pass

    def disable_bracketed_paste(self):
        """Disable bracketed paste mode."""
        pass

    # ── Echo control ─────────────────────────────────────────────────

    def set_echo(self, enabled):
        """Toggle terminal echo on/off."""
        pass  # no-op on POSIX (handled by readline/terminal)

    # ── Paste detection ──────────────────────────────────────────────

    def is_chars_buffered(self):
        """Return True if characters are buffered in the input queue (paste)."""
        return False

    def read_buffered_chars(self):
        """Read all buffered characters and return as a string.

        Returns None if paste detection is not supported on this platform.
        """
        return None

    # ── Process management ───────────────────────────────────────────

    def subprocess_flags(self):
        """Return kwargs for subprocess.Popen for process-group isolation."""
        return {}

    def kill_process_tree(self, proc):
        """Kill a process and its entire process group."""
        try:
            proc.kill()
        except Exception:
            pass

    # ── Encoding ────────────────────────────────────────────────────

    def fallback_encoding(self):
        """Return a fallback encoding for subprocess output, or None."""
        return None

    # ── Command sets ────────────────────────────────────────────────

    @property
    def safe_commands(self):
        return set()

    @property
    def blocked_commands(self):
        return set()

    @property
    def warning_commands(self):
        return set()

    @property
    def warning_base_commands(self):
        return set()

    # ── Shell guidance ──────────────────────────────────────────────

    def shell_guidance(self):
        """Return platform-specific shell guidance for the system prompt."""
        return ""

    # ── Surrogate handling ───────────────────────────────────────────

    def combine_surrogates(self, text):
        """Combine UTF-16 surrogate pairs into proper Unicode (Windows only)."""
        return text


# ── Windows backend ───────────────────────────────────────────────────

class Win32Terminal(TerminalBackend):

    is_windows = True
    platform_label = "win32"
    shell_label = "cmd/powershell"
    shell_lang = "cmd"

    _ansi_enabled = False

    def enable_ansi(self):
        if self._ansi_enabled:
            return
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            self._ansi_enabled = True
        except Exception:
            pass

    def set_echo(self, enabled):
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            if enabled:
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            else:
                kernel32.SetConsoleMode(handle, mode.value & ~0x0004)
        except Exception:
            pass

    def is_chars_buffered(self):
        import msvcrt
        return msvcrt.kbhit()

    def read_buffered_chars(self):
        import msvcrt
        buf = []
        while True:
            while msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch == '\x03':
                    raise KeyboardInterrupt
                buf.append(ch)
            import time
            time.sleep(0.05)
            if not msvcrt.kbhit():
                break
        if not buf:
            return None
        text = self.combine_surrogates(''.join(buf))
        return text.replace('\r\n', '\n').replace('\r', '\n')

    def subprocess_flags(self):
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}

    def kill_process_tree(self, proc):
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=5,
            )
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def fallback_encoding(self):
        try:
            import ctypes
            oem_cp = ctypes.windll.kernel32.GetOEMCP()
            return f"cp{oem_cp}"
        except Exception:
            return None

    @property
    def safe_commands(self):
        from .constants import SAFE_SHELL_COMMANDS_WINDOWS
        return SAFE_SHELL_COMMANDS_WINDOWS

    @property
    def blocked_commands(self):
        from .constants import BLOCKED_COMMANDS_WINDOWS
        return BLOCKED_COMMANDS_WINDOWS

    @property
    def warning_commands(self):
        from .constants import WARNING_COMMANDS_WINDOWS
        return WARNING_COMMANDS_WINDOWS

    @property
    def warning_base_commands(self):
        return {
            'del', 'rmdir', 'taskkill', 'sc', 'net', 'netsh',
        }

    def combine_surrogates(self, text):
        result = []
        i = 0
        while i < len(text):
            ch = text[i]
            if '\ud800' <= ch <= '\udbff' and i + 1 < len(text):
                next_ch = text[i + 1]
                if '\udc00' <= next_ch <= '\udfff':
                    code_point = 0x10000 + (ord(ch) - 0xD800) * 0x400 + (ord(next_ch) - 0xDC00)
                    result.append(chr(code_point))
                    i += 2
                    continue
            result.append(ch)
            i += 1
        return ''.join(result)

    def shell_guidance(self):
        from datetime import date
        today = date.today().isoformat()
        return (
            "\n\n"
            f"Platform: {self.platform_label} | Shell: {self.shell_label} | OS: {self.platform_label} | Current date: {today}\n\n"
            "SHELL AND COMMAND GUIDELINES FOR WINDOWS:\n"
            "- You are running on Windows. Use Windows-native commands in RUN blocks.\n"
            "- Use `dir` instead of `ls`\n"
            "- Use `type` instead of `cat`\n"
            "- Use `findstr` instead of `grep`\n"
            "- Use `where` instead of `which` or `command -v`\n"
            "- Use `set` instead of `env` or `printenv`\n"
            "- Use `ver` instead of `uname`\n"
            "- Use `fc` instead of `diff`\n"
            "- Use `dir /s /b` or `tree /F` instead of `find` for locating files\n"
            "- Use backslashes or forward slashes in paths (both work on Windows)\n"
            "- Use `cmd` or `powershell` as the RUN fence language\n"
            "- Do NOT use bash, sh, or Unix-only commands unless running under WSL\n"
        )


# ── POSIX backend (Linux + macOS) ─────────────────────────────────────

class PosixTerminal(TerminalBackend):

    is_posix = True
    is_macos = IS_MACOS

    platform_label = _detect_platform_label()
    shell_label = _detect_shell_label()
    shell_lang = _detect_shell_lang()

    supports_bracketed_paste = True

    def enable_bracketed_paste(self):
        """Enable bracketed paste mode via DECSET 2004."""
        if sys.stdin.isatty():
            sys.stdout.write("\033[?2004h")
            sys.stdout.flush()

    def disable_bracketed_paste(self):
        """Disable bracketed paste mode."""
        if sys.stdin.isatty():
            sys.stdout.write("\033[?2004l")
            sys.stdout.flush()

    def is_chars_buffered(self):
        import select
        return bool(select.select([sys.stdin], [], [], 0.05)[0])

    def read_buffered_chars(self):
        import select
        lines = []
        while select.select([sys.stdin], [], [], 0.05)[0]:
            line = sys.stdin.readline()
            if not line:
                break
            lines.append(line.rstrip('\n\r'))
        if not lines:
            return None
        return '\n'.join(lines)

    def subprocess_flags(self):
        return {"start_new_session": True}

    def kill_process_tree(self, proc):
        import signal
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    @property
    def safe_commands(self):
        from .constants import SAFE_SHELL_COMMANDS_UNIX
        return SAFE_SHELL_COMMANDS_UNIX

    @property
    def blocked_commands(self):
        from .constants import BLOCKED_COMMANDS_UNIX
        return BLOCKED_COMMANDS_UNIX

    @property
    def warning_commands(self):
        from .constants import WARNING_COMMANDS_UNIX
        return WARNING_COMMANDS_UNIX

    @property
    def warning_base_commands(self):
        base = {
            'rm', 'rmdir', 'chmod', 'chown', 'kill', 'killall',
            'apt', 'apt-get', 'yum', 'dnf', 'brew',
            'systemctl', 'service',
        }
        return base

    def shell_guidance(self):
        from datetime import date
        today = date.today().isoformat()
        shell = self.shell_lang
        lines = [
            "\n\n",
            f"Platform: {self.platform_label} | Shell: {self.shell_label} | OS: {self.platform_label} | Current date: {today}\n\n",
            f"SHELL AND COMMAND GUIDELINES FOR {self.platform_label.upper()}:\n",
            f"- You are running on a Unix-like system ({self.platform_label}). Use standard Unix commands in RUN blocks.\n",
            f"- Use `{shell}` or `sh` as the RUN fence language\n",
            "- Standard commands available: ls, cat, grep, find, which, head, tail, diff, wc, etc.\n",
        ]
        if self.is_macos:
            lines.extend([
                "- macOS uses BSD versions of some commands (sed, grep, tar) which differ from GNU:\n"
                "  - `sed -i ''` (requires empty string after -i, unlike GNU sed)\n"
                "  - `grep -P` is not available — use `grep -E` for extended regex\n"
                "  - `tar` does not support `--zstd` natively\n"
                "- Use `brew` for package management (e.g. `brew install ripgrep`)\n"
                "- `find` supports `-print0` but not all GNU extensions\n"
            ])
        return ''.join(lines)


# ── Singleton ─────────────────────────────────────────────────────────

terminal: TerminalBackend = Win32Terminal() if IS_WINDOWS else PosixTerminal()
