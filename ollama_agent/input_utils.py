"""Terminal input helpers: multiline, paste detection, echo control.

Input is handled through a chain of InputStrategy implementations:
  1. PromptToolkitInput   — prompt_toolkit-based (Windows primary, multiline)
  2. PosixReadlineInput   — readline + termios paste detection (POSIX tty)
  3. WindowsFallbackInput — bracketed paste + msvcrt timing (Windows / non-tty)

read_full_input() is a thin dispatcher that tries each strategy in order;
the first one that returns a non-None InputResult wins.
"""

import re
import sys
import time

from .platform import terminal

# Import readline on POSIX to enable arrow key editing, history, etc.
# in input() calls. On Windows, readline is not available (and not needed —
# prompt_toolkit or msvcrt handles input there).
if not terminal.is_windows:
    try:
        import readline  # noqa: F401
    except ImportError:
        pass

_stdout_reconfigured = False


# Control characters that should be stripped from user input.
# Keeps \t (tab), \n (newline), \r (carriage return) — those are legitimate.
# Removes ANSI escape sequences, terminal control codes (clear screen, cursor
# movement, etc.), and other C0 control chars that could corrupt display or
# be sent to the LLM API as injection vectors.
_CONTROL_CHAR_RE = re.compile(
    r'\x1b\[[0-9;]*[A-Za-z]'       # CSI sequences (colors, cursor, clear)
    r'|\x1b\][^\x07\x1b]*\x07'     # OSC sequences (title set, etc.)
    r'|\x1b[=>NMOc]'               # Single-char ESC sequences
    r'|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]'  # C0 controls (except \t \n \r)
)


def _sanitize_input(text):
    """Strip ANSI escape sequences and control characters from user input.

    Prevents terminal control characters (e.g. \\x1b[2J clear screen) from
    corrupting the display or being sent to the LLM API. Keeps tabs, newlines,
    and carriage returns which are legitimate input.
    """
    return _CONTROL_CHAR_RE.sub('', text)


class InputResult(str):
    """String subclass carrying paste-detection metadata.

    Behaves as a plain string for all existing callers (.strip(), .lower(), etc.)
    but exposes a ``was_paste`` attribute so consumers can check whether the
    input arrived as a paste event — without reading a module-level global.
    """

    was_paste: bool = False

    def __new__(cls, text, was_paste=False):
        obj = super().__new__(cls, text)
        obj.was_paste = was_paste
        return obj


def _combine_surrogates(text):
    """Combine UTF-16 surrogate pairs into proper Unicode (delegates to platform)."""
    return terminal.combine_surrogates(text)


def _reconfigure_stdout():
    """Reconfigure sys.stdout to replace unencodable characters instead of crashing.

    On Windows, the console encoding may be a legacy codepage (e.g. cp1251,
    cp1252) that cannot represent emoji or other Unicode characters. By
    default, print() raises UnicodeEncodeError for such characters.

    This reconfigures stdout with errors='replace' so unencodable characters
    are replaced with '?' instead of crashing the program.
    """
    global _stdout_reconfigured
    if _stdout_reconfigured:
        return
    _stdout_reconfigured = True
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(errors='replace')
        elif hasattr(sys.stdout, 'buffer'):
            import io
            buf = sys.stdout.buffer
            enc = getattr(sys.stdout, 'encoding', 'utf-8') or 'utf-8'
            sys.stdout = io.TextIOWrapper(buf, encoding=enc, errors='replace',
                                         line_buffering=True)
    except Exception:
        pass
    try:
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(errors='replace')
    except Exception:
        pass


def _enable_ansi_windows():
    """Enable ANSI escape code processing (delegates to platform backend)."""
    terminal.enable_ansi()


def _set_echo(enabled):
    """Toggle terminal echo (delegates to platform backend)."""
    terminal.set_echo(enabled)


# ── Bracketed paste mode ───────────────────────────────────────────────
# Terminal escape sequences for deterministic paste detection.
# When enabled, the terminal wraps pasted content with \033[200~ ... \033[201~.
# This replaces the timing-based heuristic (sleep + kbhit/select) with
# a deterministic protocol: if the start marker is present, it's a paste.

_BP_START = '\033[200~'
_BP_END = '\033[201~'


def _read_bracketed_paste(first_line):
    """Read pasted content using bracketed paste markers (deterministic).

    Called when the first readline() contains the \\033[200~ start marker.
    Reads until the \\033[201~ end marker is found, using select() with a
    short timeout to avoid blocking if the marker is missing.
    """
    # Strip the start marker from the first line
    first = first_line.replace(_BP_START, '', 1)

    # Single-line paste: both markers in the first line
    if _BP_END in first:
        first = first.replace(_BP_END, '', 1)
        return InputResult(first.rstrip('\n\r'), was_paste=True)

    lines = []
    if first.strip():
        lines.append(first.rstrip('\n\r'))

    # Read remaining lines until we find the end marker
    import select
    while True:
        ready, _, _ = select.select([sys.stdin], [], [], 2.0)
        if not ready:
            break  # Timeout — treat what we have as the paste
        line = sys.stdin.readline()
        if not line:
            break
        if _BP_END in line:
            line = line.replace(_BP_END, '', 1)
            if line.strip():
                lines.append(line.rstrip('\n\r'))
            break
        lines.append(line.rstrip('\n\r'))

    return InputResult('\n'.join(lines), was_paste=True)


# Module-level history for prompt_toolkit — persists across calls within a
# session so arrow-up/down navigation works between prompts.
_pt_history = None


def _get_pt_history():
    """Lazily create a shared InMemoryHistory for prompt_toolkit sessions."""
    global _pt_history
    if _pt_history is None:
        try:
            from prompt_toolkit.history import InMemoryHistory
            _pt_history = InMemoryHistory()
        except ImportError:
            pass
    return _pt_history


# ── ANSI SGR → prompt_toolkit color mapping ────────────────────────────
# prompt_toolkit uses CSS-like style strings, not raw ANSI codes.
# Map the SGR foreground codes we use to prompt_toolkit color names.
_ANSI_SGR_COLOR_MAP = {
    '30': 'ansiblack', '31': 'ansired', '32': 'ansigreen',
    '33': 'ansiyellow', '34': 'ansiblue', '35': 'ansimagenta',
    '36': 'ansicyan', '37': 'ansiwhite',
    '90': 'ansibrightblack', '91': 'ansibrightred', '92': 'ansibrightgreen',
    '93': 'ansibrightyellow', '94': 'ansibrightblue', '95': 'ansibrightmagenta',
    '96': 'ansibrightcyan', '97': 'ansibrightwhite',
}


def _ansi_sgr_to_ptk_color(ansi_code):
    """Convert an ANSI SGR escape sequence to a prompt_toolkit style string.

    e.g. '\033[37m' → 'ansiwhite', '\033[93m' → 'ansibrightyellow'.
    Returns None if the code is not a recognized foreground color.
    """
    if not ansi_code:
        return None
    m = re.match(r'\x1b\[(\d+)m', ansi_code)
    if not m:
        return None
    return _ANSI_SGR_COLOR_MAP.get(m.group(1))


def _try_prompt_toolkit_input(prompt_text, multiline_mode="shift_enter", color=None):
    """Try reading input with prompt_toolkit.

    Args:
        prompt_text: The prompt string to display.
        multiline_mode: One of:
            "shift_enter" — Shift+Enter / Ctrl+Enter inserts newline,
                            Enter submits (default for inline multiline).
            "free_form"   — Enter inserts newline; empty line or /end submits
                            (used by /multiline command). Both Shift+Enter and
                            Ctrl+Enter also insert newlines.

    We explicitly pass handle_sigint=False to prevent prompt_toolkit from
    replacing the OS-level SIGINT handler. When handle_sigint=True (the
    default), prompt_toolkit installs its own asyncio signal handler via
    loop.add_signal_handler(SIGINT, ...) and -- due to a known bug (#1576) --
    does not fully restore the C-level PyOS_InitInterrupts handler afterward.
    This leaves KeyboardInterrupt un-raisable in the main thread for the rest
    of the process lifetime, so Ctrl+C during model output is silently eaten.

    With handle_sigint=False, prompt_toolkit never touches the signal handler,
    and Python's default SIGINT -> KeyboardInterrupt delivery is preserved.
    Ctrl+C at the prompt itself still works because prompt_toolkit detects the
    ^C byte from stdin and raises KeyboardInterrupt via its key bindings.
    """
    if not sys.stdin.isatty():
        return None
    try:
        import signal as _signal
        from prompt_toolkit import PromptSession
        from prompt_toolkit.key_binding import KeyBindings

        kb = KeyBindings()

        if multiline_mode == "free_form":
            # Enter inserts a newline; submit on empty line or /end
            @kb.add('enter')
            def _(event):
                buf = event.current_buffer
                text = buf.text.strip()
                if text == "/end" or (text == "" and buf.text.count("\n") >= 1):
                    buf.validate_and_handle()
                else:
                    buf.insert_text('\n')

            @kb.add('s-enter')
            def _(event):
                event.current_buffer.insert_text('\n')

            @kb.add('c-enter')
            def _(event):
                event.current_buffer.insert_text('\n')
        else:
            # shift_enter mode: Enter submits by default. We add one binding:
            # if the current line ends with a backslash, Enter inserts a
                       # newline (line continuation) instead of submitting.
            # This preserves the \ + Enter multiline behavior that the
            # Windows readline fallback previously provided.
            #
            # Shift+Enter / Ctrl+Enter are NOT bindable in prompt_toolkit —
            # those keys don't produce distinct escape sequences on most
            # terminals, and 's-enter'/'c-enter' are not valid Keys enum
            # members. Multiline input is also available via /multiline
            # (free_form mode), which binds 'enter' to insert newlines.

            @kb.add('enter')
            def _(event):
                buf = event.current_buffer
                # Check if the current line ends with a backslash
                line = buf.document.current_line
                if line.rstrip().endswith('\\'):
                    # Remove the trailing backslash and insert a newline
                    buf.delete_before_cursor(count=1)
                    buf.insert_text('\n')
                else:
                    buf.validate_and_handle()

        # Preserve the current SIGINT handler and restore it unconditionally
        # after the prompt returns, guarding against any residual mutation by
        # prompt_toolkit even with handle_sigint=False.
        # Map ANSI SGR color code to prompt_toolkit style for input text.
        _ptk_style = None
        _prompt_obj = prompt_text
        if color:
            from prompt_toolkit.formatted_text import ANSI as _PTK_ANSI
            from prompt_toolkit.styles import Style as _PTK_Style
            _color_name = _ansi_sgr_to_ptk_color(color)
            if _color_name:
                _ptk_style = _PTK_Style.from_dict({'': _color_name})
            # ANSI() parses escape sequences in the prompt text
            _prompt_obj = _PTK_ANSI(f"{color}{prompt_text}")

        _saved_sigint = _signal.getsignal(_signal.SIGINT)
        try:
            history = _get_pt_history()
            session = PromptSession(key_bindings=kb, history=history)
            result = session.prompt(_prompt_obj, handle_sigint=False,
                                    style=_ptk_style)
        finally:
            _signal.signal(_signal.SIGINT, _saved_sigint)

        return result
    except ImportError:
        return None
    except (EOFError, KeyboardInterrupt):
        raise
    except Exception as e:
        # Log the error so silent prompt_toolkit failures are diagnosable.
        # Previously this returned None with no trace, masking bugs like
        # invalid key bindings that caused prompt_toolkit to never work.
        import logging
        logging.getLogger(__name__).debug(
            "prompt_toolkit input failed: %s: %s", type(e).__name__, e
        )
        return None


# ── Input strategies ───────────────────────────────────────────────────


class InputStrategy:
    """Abstract input strategy for read_full_input.

    Each strategy's read() returns an InputResult on success, or None if
    the strategy is not applicable to the current platform/conditions.
    """

    def read(self, prompt, multiline, color):
        """Return an InputResult, or None if this strategy is not applicable."""
        raise NotImplementedError


class PromptToolkitInput(InputStrategy):
    """Read input via prompt_toolkit — provides arrow keys, history, multiline.

    Used as the primary strategy on Windows (where readline is unavailable)
    and for multiline input on all platforms. Returns None if prompt_toolkit
    is not installed or the input is not a tty.
    """

    def read(self, prompt, multiline, color):
        if not (multiline or terminal.is_windows):
            return None
        result = _try_prompt_toolkit_input(prompt, color=color)
        if result is None:
            return None
        return InputResult(
            _sanitize_input(result),
            was_paste=result.count("\n") >= 1,
        )


class PosixReadlineInput(InputStrategy):
    """Read input via input() + readline with termios-based paste detection.

    Applicable on POSIX systems with a tty. Uses readline for arrow key
    editing and history, then switches to non-canonical mode to detect
    remaining buffered paste data.
    """

    def read(self, prompt, multiline, color):
        if terminal.is_windows or not sys.stdin.isatty():
            return None

        color_active = bool(color and sys.stdout.isatty())
        try:
            # ── POSIX: use input() with readline for arrow key support ──────
            # On POSIX, input() uses the readline module which handles arrow
            # keys, history, and line editing. sys.stdin.readline() does NOT
            # use readline, so arrow keys appear as raw escape sequences.
            #
            # We pass the prompt to input() so readline knows the correct
            # prompt length for cursor positioning. ANSI color codes are
            # wrapped with \001/\002 (RL_PROMPT_START_IGNORE/END_IGNORE)
            # so readline excludes them from the visible prompt width.
            # Without this, arrow keys miscalculate cursor position and
            # jump to the wrong column.
            #
            # We do NOT enable bracketed paste here because readline/libedit
            # conflicts with the raw marker protocol — it may strip markers
            # (losing paste detection) or leak them into the input string.
            # Instead, we detect paste by checking for immediately-buffered
            # data after input() returns (multi-line paste leaves remaining
            # lines in the stdin buffer).
            if color_active:
                rl_prompt = f"\001{color}\002{prompt}"
            else:
                rl_prompt = prompt
            try:
                first = input(rl_prompt)
            except KeyboardInterrupt:
                raise
            except EOFError:
                raise

            # Check if more data is immediately buffered (paste detection).
            #
            # After input() returns the first line, readline (libedit on macOS,
            # GNU readline on Linux) has consumed exactly line 1 — it reads one
            # character at a time via read(fd, &c, 1), so all remaining paste
            # data is still in the kernel buffer.
            #
            # However, readline restores the terminal to canonical (cooked)
            # mode.  In canonical mode, the kernel only delivers COMPLETE lines
            # (terminated by \n) to read().  A final pasted line WITHOUT \n
            # stays trapped in the kernel's line-editing buffer — invisible to
            # both select() and os.read() — and leaks to the next prompt.
            #
            # Fix: temporarily disable ICANON (canonical mode) and ECHO so the
            # kernel returns all available bytes immediately (including a
            # trailing partial line) without double-displaying them.
            #
            # readline only echoes Line1 on screen (it stops at the first \n).
            # Lines 2-N are read with ECHO off, so they're never displayed.
            # After collecting all lines, we erase "You: Line1" by moving up
            # 1 line and clearing to end of screen.
            import select
            import os as _os
            import termios as _termios
            fd = sys.stdin.fileno()

            _old_attrs = _termios.tcgetattr(fd)
            _raw_attrs = _termios.tcgetattr(fd)
            _raw_attrs[3] &= ~_termios.ICANON  # non-canonical: read returns immediately
            _raw_attrs[3] &= ~_termios.ECHO    # don't echo pasted text
            _termios.tcsetattr(fd, _termios.TCSANOW, _raw_attrs)

            lines = [first]
            _pending = ""
            try:
                while True:
                    ready, _, _ = select.select([fd], [], [], 0.1)
                    if not ready:
                        break
                    try:
                        _chunk = _os.read(fd, 65536)
                    except OSError:
                        break
                    if not _chunk:
                        break
                    _pending += _chunk.decode('utf-8', errors='replace')
                    while '\n' in _pending:
                        _line, _pending = _pending.split('\n', 1)
                        lines.append(_line.rstrip('\r'))
                # Any remaining pending data is the final line without \n
                if _pending:
                    lines.append(_pending.rstrip('\r'))
            finally:
                _termios.tcsetattr(fd, _termios.TCSANOW, _old_attrs)

            is_paste = len(lines) > 1

            # Erase the displayed paste text from the terminal.
            # readline only echoes Line1, so we move up 1 line to reach
            # "You: Line1" and clear to end of screen.
            if is_paste and sys.stdout.isatty():
                sys.stdout.write("\033[1A\r\033[0J")
                sys.stdout.flush()

            text = '\n'.join(lines)
            return InputResult(_sanitize_input(text), was_paste=is_paste)
        finally:
            if color_active:
                sys.stdout.write("\033[0m")
                sys.stdout.flush()


class WindowsFallbackInput(InputStrategy):
    """Read input via bracketed paste + msvcrt timing heuristic.

    Applicable on Windows (tty or non-tty) and on POSIX non-tty. This is
    the fallback when prompt_toolkit is unavailable and the POSIX readline
    strategy does not apply.
    """

    def read(self, prompt, multiline, color):
        # POSIX + tty is handled by PosixReadlineInput
        if not terminal.is_windows and sys.stdin.isatty():
            return None

        color_active = bool(color and sys.stdout.isatty())
        try:
            if color_active:
                sys.stdout.write(color)
                sys.stdout.flush()
            sys.stdout.write(prompt)
            sys.stdout.flush()
            use_bp = terminal.supports_bracketed_paste and sys.stdin.isatty()
            if use_bp:
                terminal.enable_bracketed_paste()

            try:
                first = sys.stdin.readline()
            except KeyboardInterrupt:
                if use_bp:
                    terminal.disable_bracketed_paste()
                raise
            if not first:
                if use_bp:
                    terminal.disable_bracketed_paste()
                raise EOFError

            # Check for bracketed paste start marker
            if use_bp and _BP_START in first:
                result = _read_bracketed_paste(first)
                terminal.disable_bracketed_paste()
                return InputResult(_sanitize_input(result), was_paste=True)

            if use_bp:
                terminal.disable_bracketed_paste()

            # ── Fallback: timing-based heuristic (Windows, legacy terminals) ──
            lines = [first.rstrip('\n\r')]
            paste_mode = False
            if terminal.is_chars_buffered():
                paste_mode = True
                _set_echo(False)
            time.sleep(0.01)
            if terminal.is_chars_buffered():
                if not paste_mode:
                    _set_echo(False)
                try:
                    text = terminal.read_buffered_chars()
                    if text:
                        remaining = text.split('\n')
                        if remaining and not remaining[-1]:
                            remaining = remaining[:-1]
                        lines.extend(remaining)
                except KeyboardInterrupt:
                    _set_echo(True)
                    raise
                finally:
                    _set_echo(True)
            elif paste_mode:
                _set_echo(True)
                sys.stdout.write(first)
                sys.stdout.flush()
            if paste_mode and len(lines) > 1:
                sys.stdout.write("\r")
                sys.stdout.flush()
            if multiline and len(lines) == 1 and lines[0].rstrip().endswith('\\'):
                cont_lines = [lines[0].rstrip()[:-1]]
                while True:
                    sys.stdout.write("... ")
                    sys.stdout.flush()
                    next_line = sys.stdin.readline()
                    if not next_line:
                        break
                    next_line = next_line.rstrip('\n\r')
                    if next_line.strip() == '':
                        break
                    if next_line.rstrip().endswith('\\'):
                        cont_lines.append(next_line.rstrip()[:-1])
                    else:
                        cont_lines.append(next_line)
                        break
                return InputResult(
                    _sanitize_input('\n'.join(cont_lines)), was_paste=False
                )
            is_paste = len(lines) > 1
            if len(lines) == 1:
                return InputResult(
                    _sanitize_input(lines[0]), was_paste=is_paste
                )
            return InputResult(
                _sanitize_input('\n'.join(lines)), was_paste=is_paste
            )
        finally:
            if color_active:
                sys.stdout.write("\033[0m")
                sys.stdout.flush()


# ── Strategy chain ─────────────────────────────────────────────────────

_strategies = [
    PromptToolkitInput(),
    PosixReadlineInput(),
    WindowsFallbackInput(),
]


def read_full_input(prompt="", multiline=False, color=None):
    """Read user input with paste detection and multiline continuation support.

    Args:
        prompt: The prompt string to display.
        multiline: If True, enable multiline input modes.
        color: Optional ANSI color code (e.g. "\\033[37m" for light gray).
               When set and stdout is a tty, the prompt and user input are
               displayed in this color. The color is reset after input is read.

    Tries each InputStrategy in order; the first that returns a non-None
    InputResult wins. If no strategy applies, returns an empty InputResult.
    """
    _reconfigure_stdout()
    _enable_ansi_windows()
    for strategy in _strategies:
        result = strategy.read(prompt, multiline, color)
        if result is not None:
            return result
    return InputResult("", was_paste=False)
