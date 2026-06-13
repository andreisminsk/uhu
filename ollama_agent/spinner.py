"""Spinner animation for indicating waiting states."""

import itertools
import re
import sys
import threading


class Spinner:
    """A terminal spinner that animates while waiting, with optional thinking display."""

    def __init__(self, message="Thinking", prefix="", max_thinking_lines=5):
        self.message = message
        self.prefix = prefix
        self.max_thinking_lines = max_thinking_lines
        self.thinking_text = ""
        self._frames = ["◰", "◳", "◲", "◱"]
        self._stop = threading.Event()
        self._thread = None
        self._last_lines = 0
        # Regex to strip ANSI escape sequences from thinking text
        self._ansi_re = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\].*?\x07|\x1b[\[\]()][0-9;]*")

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
        result = []
        for line in recent:
            display = self._sanitize(line)
            if len(display) > 100:
                display = "..." + display[-97:]
            result.append("  " + display)
        return result

    def _spin(self):
        first = True
        try:
            for frame in itertools.cycle(self._frames):
                if self._stop.is_set():
                    break
                thinking_lines = self._get_thinking_lines()
                total_lines = 1 + len(thinking_lines)

                if first:
                    sys.stdout.write(f"\r{self.prefix}{frame} {self.message}...\n")
                    for tl in thinking_lines:
                        sys.stdout.write(f"\033[2m{tl}\033[0m\n")
                    self._last_lines = total_lines
                    first = False
                else:
                    # Move cursor up past all previously displayed lines
                    if self._last_lines > 0:
                        sys.stdout.write(f"\033[{self._last_lines}A")
                    # Clear from cursor to end of screen
                    sys.stdout.write("\033[J")
                    # Redraw all lines
                    sys.stdout.write(f"\r{self.prefix}{frame} {self.message}...\n")
                    for tl in thinking_lines:
                        sys.stdout.write(f"\033[2m{tl}\033[0m\n")
                    self._last_lines = total_lines

                sys.stdout.flush()
                self._stop.wait(0.25)
        except Exception:
            pass
        try:
            # Clear all displayed lines
            if self._last_lines > 0:
                sys.stdout.write(f"\033[{self._last_lines}A")
                sys.stdout.write("\033[J")
            sys.stdout.flush()
        except Exception:
            pass

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
