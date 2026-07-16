"""Command safety gate — extracted from actions.py for testability."""

import os
import re

from .platform import terminal


class CommandSafetyGate:
    """Check shell commands for safety. Returns (level, message).

    level: 'blocked' - never execute
           'warning' - requires explicit confirmation even with auto-approve
           'chain'   - shell chaining detected, warn but allow with confirmation
           'safe'    - no issues
    """

    _SHELL_OPERATORS = re.compile(r'&&|\|\||[|;&]|\$\(|`|\n|\r|<\(|>\(')

    _BLOCKED_PATTERNS = [
        re.compile(r'\brm\s+-[rR].*\s+/\s*$', re.IGNORECASE),
        re.compile(r'\brm\s+-[rR].*\s+/\*', re.IGNORECASE),
        re.compile(r'\brm\s+-[rRf]*\s+/', re.IGNORECASE),
        re.compile(r'\brm\s+--recursive.*\s+/', re.IGNORECASE),
        re.compile(r'\bdd\s+if=', re.IGNORECASE),
        re.compile(r'\bmkfs\b', re.IGNORECASE),
        re.compile(r'\bshutdown\b', re.IGNORECASE),
        re.compile(r'\breboot\b', re.IGNORECASE),
        re.compile(r'\bpoweroff\b', re.IGNORECASE),
        re.compile(r'\bhalt\b', re.IGNORECASE),
        re.compile(r'\bformat\s+[A-Za-z]:', re.IGNORECASE),
        re.compile(r'\bdel\s+/s\s+/q\s+[cC]:', re.IGNORECASE),
        re.compile(r'\brmdir\s+/s\s+/q\s+[cC]:', re.IGNORECASE),
    ]

    _WARNING_SUBSTRINGS = {
        'pip uninstall', 'npm uninstall',
        'git push', 'git reset --hard', 'git clean',
    }

    def warning_base_commands(self):
        """Return platform-appropriate warning base commands set."""
        return terminal.warning_base_commands

    def check(self, cmd):
        """Check a command for safety. Returns (level, message)."""
        for pat in self._BLOCKED_PATTERNS:
            if pat.search(cmd):
                return ('blocked', f"Command blocked for safety: {cmd[:80]}")

        base = get_base_command(cmd)
        if base in terminal.blocked_commands:
            return ('blocked', f"Command blocked for safety: {cmd[:80]}")

        if base in terminal.warning_commands or base in self.warning_base_commands():
            return ('warning', f"Destructive command requires confirmation: {cmd[:80]}")
        for substr in self._WARNING_SUBSTRINGS:
            if substr in cmd.lower():
                return ('warning', f"Destructive command requires confirmation: {cmd[:80]}")

        if self._SHELL_OPERATORS.search(cmd):
            return ('chain', f"AGENT: Shell chaining detected in: {cmd[:80]}")

        return ('safe', '')

    def is_safe(self, cmd):
        """Check if a command is considered safe/read-only."""
        if self._SHELL_OPERATORS.search(cmd):
            return False
        base = get_base_command(cmd)
        return base in terminal.safe_commands


def get_base_command(cmd):
    """Extract the base command name from a shell command string."""
    cmd = cmd.strip()
    if not cmd:
        return ""
    if cmd[0] == '"':
        end = cmd.find('"', 1)
        if end > 0:
            base = cmd[1:end]
        else:
            base = cmd[1:].split(None, 1)[0] if len(cmd) > 1 else ""
    else:
        base = cmd.split(None, 1)[0]
    base = os.path.basename(base).lower()
    for ext in ('.exe', '.cmd', '.bat', '.com'):
        if base.endswith(ext):
            base = base[:-len(ext)]
            break
    return base


def resolve_tool_name(tool_name, all_tool_names, get_tool_fn, workdir):
    """Resolve a tool name, handling fuzzy matching and file-path confusion.

    Returns (tool_instance, corrected_name, error_message).
    - If exact match: (tool, tool_name, None)
    - If fuzzy match: (tool, corrected_name, None)
    - If file-path confusion: (None, None, hint_message)
    - If not found: (None, None, error_message)
    """
    tool = get_tool_fn(tool_name)
    if tool:
        return (tool, tool_name, None)

    close_match = None
    for candidate_name in all_tool_names:
        if tool_name + "s" == candidate_name or tool_name.rstrip("s") == candidate_name.rstrip("s"):
            close_match = candidate_name
            break
    if not close_match:
        normalized = tool_name.replace("-", "_")
        for candidate_name in all_tool_names:
            if normalized == candidate_name.replace("-", "_"):
                close_match = candidate_name
                break

    if close_match:
        tool = get_tool_fn(close_match)
        return (tool, close_match, None)

    if "." in tool_name and not tool_name.endswith("()"):
        candidate = os.path.join(workdir, tool_name) if not os.path.isabs(tool_name) else tool_name
        if os.path.isfile(candidate):
            msg = (
                f"[TOOL FAILED: Unknown tool '{tool_name}' - this looks like a file path, not a tool name. "
                f"To read a file's contents into context, use **FILE:`{tool_name}`** "
                f"(closed by **EOF:`{tool_name}`**) instead of **TOOL:`{tool_name}`**.]"
            )
            return (None, None, msg)

    msg = f"[TOOL FAILED: Unknown tool '{tool_name}']"
    return (None, None, msg)
