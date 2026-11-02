"""Spinner animation for indicating waiting states."""

import itertools
import re
import shutil
import sys
import threading


class Spinner:
    """A terminal spinner that animates while waiting, with optional thinking display.

    Screen-cleanup ownership (Ctrl+C fix): the animation thread only DRAWS.
    ``stop()`` is the single owner of erasing — it signals the thread, joins
    it, and then erases the drawn lines itself. Previously the thread erased
    on exit AND ``stop()`` abandoned it after a 1s join timeout, so a zombie
    thread (starved by KeyboardInterrupt unwinding / GIL contention) could
    wake up later, re-animate and erase over a freshly rendered input prompt
    — desyncing the terminal cursor from prompt_toolkit's internal cursor
    (visible as duplicated user input after Enter) and, in the worst case,
    hanging the process holding the stdout buffer mid-write.
    """

    def __init__(self, message="Thinking", prefix="", max_thinking_lines=5, color=None, thinking_color=None):
        self.message = message
        self.prefix = prefix
        self.max_thinking_lines = max_thinking_lines
        # Optional ANSI color for the spinner line and thinking lines.
        # Applied only when stdout is a TTY. thinking_color overrides the
        # color of the scrolling thinking preview lines (defaults to color).
        self.color = color if (color and sys.stdout.isatty()) else None
        self.thinking_color = (thinking_color if (thinking_color and sys.stdout.isatty()) else None) or self.color
        self.thinking_text = ""
        self._frames = ["◰", "◳", "◲", "◱"]
        self._stop = threading.Event()
        self._thread = None
        self._last_lines = 0

    def start(self):
        self._stop.clear()
        self._last_lines = 0
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    @staticmethod
    def _sanitize(text):
        """Strip ANSI escapes, control characters, and Unicode formatting
        characters to prevent thinking output from corrupting the terminal
        display or causing visual confusion."""
        # Remove ANSI escape sequences
        text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\].*?\x07|\x1b[\[\]()][0-9;]*", "", text)
        # Remove other control characters (keep tabs and newlines)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        # Remove Unicode bidirectional/formatting characters that could
        # cause visual confusion (RTL overrides, zero-width spaces, etc.)
        text = re.sub(r"[\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u2060\ufeff]", "", text)
        return text

    def append_thinking(self, text):
        """Append thinking text and trim to keep only the last few lines.
        Prevents unbounded memory growth from long model thinking output."""
        self.thinking_text += text
        lines = self.thinking_text.splitlines(keepends=True)
        # Keep a small buffer beyond what we display to handle partial lines
        keep = self.max_thinking_lines + 2
        if len(lines) > keep:
            self.thinking_text = "".join(lines[-keep:])

    @property
    def is_running(self):
        """True while the spinner thread is active."""
        return self._thread is not None and self._thread.is_alive()

    def _get_thinking_lines(self):
        """Get the last N lines of thinking text for display."""
        if not self.thinking_text:
            return []
        lines = self.thinking_text.splitlines()
        recent = lines[-self.max_thinking_lines:]
        limit = self._thinking_width_limit()
        result = []
        for line in recent:
            display = self._sanitize(line)
            if len(display) > limit:
                display = "..." + display[-(limit - 3):]
            result.append("  " + display)
        return result

    def _thinking_width_limit(self):
        """Max content chars per thinking line.

        Defaults to 100; shrinks to the terminal width on narrow terminals
        (e.g. Termux on a phone) so lines never wrap — wrapped lines break
        the cursor-up redraw logic in _render(). Subtracts the 2-space indent
        plus a 1-column safety margin; never goes below 10 chars. Re-queried
        on every redraw frame, so terminal resizes take effect live.
        """
        try:
            if sys.stdout.isatty():
                cols = shutil.get_terminal_size(fallback=(0, 0)).columns
                if 0 < cols < 100:
                    return max(10, cols - 3)
        except Exception:
            pass
        return 100

    def _render(self, frame):
        """Draw one frame: spinner line + thinking preview below it.

        Redraws over previously drawn lines by moving the cursor up and
        clearing to end of screen. ``_last_lines`` tracks how many terminal
        rows we currently own; ``_erase()`` (called exclusively by stop())
        removes them. Skips drawing after stop() was requested, so a thread
        that lost the join race can never paint over subsequent output.
        """
        if self._stop.is_set():
            return
        thinking_lines = self._get_thinking_lines()
        if self._last_lines > 0:
            sys.stdout.write(f"\033[{self._last_lines}A")
        sys.stdout.write("\033[J")
        sys.stdout.write(f"\r{self.color or ''}{self.prefix}{frame} {self.message}...\033[0m\n")
        for tl in thinking_lines:
            sys.stdout.write(f"{self.thinking_color or ''}{tl}\033[0m\n")
        self._last_lines = 1 + len(thinking_lines)
        sys.stdout.flush()

    def _spin(self):
        try:
            for frame in itertools.cycle(self._frames):
                if self._stop.is_set():
                    break
                self._render(frame)
                # Wait on the stop event: shutdown latency ≤ one frame tick,
                # and the thread exits promptly when stop() is requested.
                if self._stop.wait(0.25):
                    break
        except Exception:
            pass
        # NOTE: no screen cleanup here — stop() owns erasure. A thread that
        # survives the join timeout below can emit at most the single frame
        # it was already writing; it never erases over subsequent output.

    def _erase(self):
        """Erase everything the spinner drew (idempotent)."""
        n, self._last_lines = self._last_lines, 0
        if n > 0:
            try:
                sys.stdout.write(f"\033[{n}A\033[J")
                sys.stdout.flush()
            except Exception:
                pass

    def stop(self):
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            # 2.5s headroom — ample even when the GIL is contended by
            # KeyboardInterrupt unwinding. Previously 1s, after which the
            # zombie thread was silently abandoned while still able to
            # write/erase the screen (see class docstring).
            thread.join(timeout=2.5)
        self._erase()
