"""Display helpers — extracted from actions.py for testability."""

import sys

from .constants import ANSI_AGENT, ANSI_RESET, ANSI_TOOL


def agent_print(*args, **kwargs):
    """Print with agent color (bright yellow) when stdout is a TTY."""
    if sys.stdout.isatty():
        print(ANSI_AGENT, end="", flush=True)
        print(*args, **kwargs)
        print(ANSI_RESET, end="", flush=True)
    else:
        print(*args, **kwargs)


def tool_print(*args, **kwargs):
    """Print with tool color (dim bright white italic) when stdout is a TTY."""
    if sys.stdout.isatty():
        print(ANSI_TOOL, end="", flush=True)
        print(*args, **kwargs)
        print(ANSI_RESET, end="", flush=True)
    else:
        print(*args, **kwargs)


def show_diff_colored(diff_text):
    """Display a diff or detail text with color coding (green=+, red=-, cyan=hunks)."""
    if not diff_text or diff_text == "(no changes)":
        print("[No changes]\n")
        return
    from .platform import terminal
    terminal.enable_ansi()
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
