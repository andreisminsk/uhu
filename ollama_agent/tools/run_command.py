"""Run command tool: execute shell commands with structured output."""

import os
import re
import subprocess
import sys
import tempfile


class RunCommandTool:
    """Execute a shell command and return structured output."""
    name = "run_command"
    description = "Execute a shell command and return structured output (stdout, stderr, exit code)."
    system_prompt = (
        "## run_command\n"
        "Execute a shell command and return structured output.\n"
        "Parameters (JSON object):\n"
        "- command (string, required): The command to execute\n"
        "- cwd (string, optional): Working directory (defaults to workdir)\n"
        "- timeout (integer, optional, default 30): Timeout in seconds\n"
        "- shell (string, optional): Shell to use — 'cmd', 'powershell', 'bash' (defaults to platform shell)\n"
        "Returns: stdout, stderr, and exit code. Use this instead of RUN: when you need structured output.\n"
        "Supported RUN fence languages: bash, sh, shell, cmd, bat, powershell, ps1, pwsh, zsh. Use the appropriate language for the current platform."
    )
    parameters = {
        "command": {
            "type": "string",
            "description": "The command to execute",
            "required": True,
        },
        "cwd": {
            "type": "string",
            "description": "Working directory (defaults to workdir)",
            "required": False,
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds (default 30)",
            "required": False,
        },
        "shell": {
            "type": "string",
            "description": "Shell to use: 'cmd', 'powershell', 'bash' (defaults to platform shell)",
            "required": False,
        },
    }

    @staticmethod
    def _needs_powershell_fallback():
        """Check if the system codepage is non-Latin, where cmd.exe may mangle paths.

        On Russian/CJK/etc. locales, cmd.exe can misinterpret backslash-escaped
        path segments (e.g. \\QuickTime\\QTSystem). PowerShell handles these correctly.
        """
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            oem_cp = ctypes.windll.kernel32.GetOEMCP()
            # Latin codepages: 437 (US), 850 (Western European), 1252 (Windows Latin-1)
            # Anything else is likely to cause path mangling in cmd.exe
            latin_cps = {437, 850, 852, 857, 860, 861, 863, 865, 1250, 1252, 1254, 1257, 28591, 28515}
            return oem_cp not in latin_cps
        except Exception:
            return False

    @staticmethod
    def _cmd_needs_script(command):
        """Check if a cmd command needs a temp script due to set VAR= with spaces/semicolons."""
        for m in re.finditer(r'set\s+(\w+)\s*=\s*(.+)', command, re.IGNORECASE):
            value = m.group(2).strip()
            if ' ' in value or ';' in value:
                return True
        return False

    @staticmethod
    def _write_temp_script(command, ext, workdir="."):
        """Write command to a temp script file and return its path."""
        fd, path = tempfile.mkstemp(
            suffix=f".{ext}", prefix="run_cmd_",
            dir=workdir if os.path.isdir(workdir) else None,
        )
        newline = "\r\n" if ext == "bat" else "\n"
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as f:
            f.write(command + "\n")
        return path

    @staticmethod
    def _quote_powershell_paths(command):
        """Wrap unquoted paths containing spaces in single quotes for PowerShell -Command."""
        def _wrap(match):
            path = match.group(0)
            start = match.start()
            before = command[:start]
            # If already inside quotes, don't re-quote
            if before.count("'") % 2 == 1 or before.count('"') % 2 == 1:
                return path
            return f"'{path}'"
        # Match Windows paths with spaces that aren't already quoted
        return re.sub(
            r'[A-Za-z]:\\(?:[^\s\'"]*\s+[^\s\'"]*)+(?:\\[^\s\'"]*)*',
            _wrap, command,
        )

    def execute(self, params, workdir=".", **kwargs):
        command = params.get("command", "")
        cwd = params.get("cwd", workdir)
        timeout = params.get("timeout", 30)
        shell_name = params.get("shell", "")
        temp_script = None

        if not command:
            return "Error: 'command' is required"

        if not os.path.isabs(cwd):
            cwd = os.path.join(workdir, cwd)

        # Determine shell
        if not shell_name:
            shell_name = "cmd" if sys.platform == "win32" else "bash"

        if shell_name in ("powershell", "pwsh", "ps1"):
            if shell_name == "ps1":
                shell_name = "powershell"
            # Wrap paths with spaces in single quotes for PowerShell
            command = self._quote_powershell_paths(command)
            shell_cmd = [shell_name, "-Command", command]
        elif shell_name == "bash":
            shell_cmd = ["/bin/bash", "-c", command]
        elif shell_name in ("cmd", "bat"):
            # cmd.exe treats '=' and ';' as command separators in 'set VAR=value;...'
            # If the command has 'set' with a value containing spaces or ';',
            # write a temp .bat file to avoid parsing issues.
            # Also, on non-Latin codepages cmd can mangle paths — use PowerShell instead.
            if self._cmd_needs_script(command) or self._needs_powershell_fallback():
                if self._needs_powershell_fallback():
                    # Non-Latin codepage: use PowerShell to avoid path mangling
                    command = self._quote_powershell_paths(command)
                    shell_cmd = ["powershell", "-Command", command]
                elif self._cmd_needs_script(command):
                    temp_script = self._write_temp_script(command, "bat", workdir)
                    shell_cmd = ["cmd", "/c", temp_script]
            else:
                shell_cmd = ["cmd", "/c", command]
        elif shell_name in ("sh", "shell"):
            shell_cmd = ["/bin/sh", "-c", command]
        else:
            shell_cmd = command

        # Encoding strategy for Windows: try UTF-8 first, then OEM codepage with replace
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
                shell_cmd if isinstance(shell_cmd, list) else command,
                shell=isinstance(shell_cmd, str),
                capture_output=True,
                cwd=cwd,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout}s"
        except FileNotFoundError as e:
            return f"Error: Command not found: {e}"
        except Exception as e:
            return f"Error: {e}"
        finally:
            # Clean up temp script
            if temp_script:
                try:
                    os.unlink(temp_script)
                except Exception:
                    pass

        # Decode output with fallback
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

        # Truncate large output
        max_output = 10000
        if len(stdout) > max_output:
            stdout = stdout[:max_output] + f"\n... [truncated, {len(stdout)} chars total]"
        if len(stderr) > max_output:
            stderr = stderr[:max_output] + f"\n... [truncated, {len(stderr)} chars total]"

        parts = [f"Exit code: {proc.returncode}"]
        if stdout:
            parts.append(f"stdout:\n{stdout}")
        if stderr:
            parts.append(f"stderr:\n{stderr}")
        if not stdout and not stderr:
            parts.append("(no output)")

        return "\n".join(parts)
