"""Display helpers — extracted from actions.py for testability."""

import re
import sys

from .constants import ANSI_AGENT, ANSI_RESET, ANSI_TOOL


def agent_print(*args, **kwargs):
    """Print with agent color (bright yellow) + [AGENT] text prefix.

    The prefix makes agent-voice lines distinctive even in plain-text
    captures (logs, pipes, non-TTY) where ANSI colors are absent. Skipped
    for blank lines, leading-newline separators, pure-punctuation
    banners (═/─ rules), status indicators ([out:/[ctx:/[ollama: lines —
    compact telemetry), and startup banner lines (Connected/Platform/
    Workdir/Logging/Type /help/Version check — session header, not voice).
    """
    if args and isinstance(args[0], str):
        first = args[0]
        stripped = first.strip()
        # Prefix only substantive lines: non-empty, no leading newline,
        # at least one alphanumeric in the first 4 chars (skips ═── banners),
        # and not a status/startup indicator line.
        if (stripped and not first.startswith("\n")
                and any(c.isalnum() for c in stripped[:4])
                and not stripped.startswith(("[out:", "[ctx:", "[ollama:"))
                and not stripped.startswith(("Connected |", "Platform:", "Workdir:",
                                             "Logging to:", "Type /help",
                                             "[Version check:", "[Update available:"))):
            args = ("[AGENT] " + first,) + args[1:]
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
    print()


# Terminal flood guard (dev-docs/TERMINAL-FLOOD-GUARD.md). Screen-control
# escapes wipe/reposition the terminal or switch to the alternate screen
# (which has NO scrollback). SGR color codes pass through untouched.
# Applied ONLY to console echoes — captured observations keep raw bytes
# (faithful record for the model and the log).
_SCREEN_CTRL_RE = re.compile(
    r"\x1b\[[0-9;]*J"         # erase display/scrollback (2J clear, 3J scrollback wipe)
    r"|\x1b\[\?[0-9;]*[hl]"   # private modes: alt-screen (1049), cursor hide (25), ...
    r"|\x1b\[[0-9;]*[Hf]"     # cursor home / absolute positioning
    r"|\x1b\[[0-9;]*[ABCD]"   # cursor up/down/forward/back
    r"|\x1b\[s"               # save cursor position
    r"|\x1b\[u"               # restore cursor position
)


def neutralize_screen_controls(text):
    """Strip screen-control escapes from text (console display only).

    Field-found failure (2026-11-08, SANDBOX): model-run TUI programs
    (curses snakes, `clear`-loop animations) streamed raw \\033[2J /
    \\033[H / \\033[?1049h into the console — blanking the visible screen,
    cycling the fixed scrollback buffer until earlier conversation was
    evicted, and (killed curses processes) stranding the terminal on the
    alternate screen, where nothing enters scrollback at all. Colors
    (SGR, \\033[...m) are preserved; only wipe/position/alt-screen codes
    are removed. Raw bytes stay in the captured observation.
    """
    return _SCREEN_CTRL_RE.sub("", text)
