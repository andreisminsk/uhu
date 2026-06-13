"""Terminal input helpers: multiline, paste detection, echo control."""

import sys
import time

_last_input_was_paste = False

_ansi_enabled_windows = False
_stdout_reconfigured = False


def _combine_surrogates(text):
    """Combine UTF-16 surrogate pairs from msvcrt.getwch() into proper Unicode characters.

    On Windows, msvcrt.getwch() returns UTF-16 code units. For characters
    outside the BMP (e.g. emoji like U+1F3F0), it returns high and low
    surrogates as separate characters. These lone surrogates cannot be
    encoded to UTF-8, causing UnicodeEncodeError later when the string is
    printed, logged, or sent to an API.

    This function detects adjacent high/low surrogate pairs and combines
    them into the corresponding Unicode code point.
    """
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
    """Enable ANSI escape code processing on Windows terminals."""
    global _ansi_enabled_windows
    if _ansi_enabled_windows or sys.platform != "win32":
        _ansi_enabled_windows = True
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        _ansi_enabled_windows = True
    except Exception:
        pass


def _set_echo(enabled):
    """Toggle terminal echo on Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        if enabled:
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        else:
            kernel32.SetConsoleMode(handle, mode.value & ~0x0004)
    except Exception:
        pass


def _try_prompt_toolkit_input(prompt_text):
    """Try reading input with prompt_toolkit (supports Shift+Enter for newline).

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

        @kb.add('s-enter')
        def _(event):
            event.current_buffer.insert_text('\n')

        @kb.add('c-enter')
        def _(event):
            event.current_buffer.insert_text('\n')

        # Preserve the current SIGINT handler and restore it unconditionally
        # after the prompt returns, guarding against any residual mutation by
        # prompt_toolkit even with handle_sigint=False.
        _saved_sigint = _signal.getsignal(_signal.SIGINT)
        try:
            session = PromptSession(key_bindings=kb)
            result = session.prompt(prompt_text, handle_sigint=False)
        finally:
            _signal.signal(_signal.SIGINT, _saved_sigint)

        return result
    except ImportError:
        return None
    except (EOFError, KeyboardInterrupt):
        raise
    except Exception:
        return None


def read_full_input(prompt="", multiline=False, color=None):
    """Read user input with paste detection and multiline continuation support.

    Args:
        prompt: The prompt string to display.
        multiline: If True, enable multiline input modes.
        color: Optional ANSI color code (e.g. "\\033[37m" for light gray).
               When set and stdout is a tty, the prompt and user input are
               displayed in this color. The color is reset after input is read.
    """
    global _last_input_was_paste
    _last_input_was_paste = False
    _reconfigure_stdout()
    _enable_ansi_windows()
    if multiline:
        result = _try_prompt_toolkit_input(prompt)
        if result is not None:
            if result.count("\n") >= 1:
                _last_input_was_paste = True
            return result
    _color_active = bool(color and sys.stdout.isatty())
    if _color_active:
        sys.stdout.write(color)
        sys.stdout.flush()
    try:
        sys.stdout.write(prompt)
        sys.stdout.flush()
        paste_mode = False
        if sys.platform == "win32":
            import msvcrt
            if msvcrt.kbhit():
                paste_mode = True
                _set_echo(False)
        try:
            first = sys.stdin.readline()
        except KeyboardInterrupt:
            if paste_mode:
                _set_echo(True)
            raise
        if not first:
            if paste_mode:
                _set_echo(True)
            raise EOFError
        lines = [first.rstrip('\n\r')]
        time.sleep(0.01)
        try:
            import msvcrt
            if msvcrt.kbhit():
                if not paste_mode:
                    _set_echo(False)
                try:
                    buf = []
                    while True:
                        while msvcrt.kbhit():
                            ch = msvcrt.getwch()
                            if ch == '\x03':
                                raise KeyboardInterrupt
                            # NOTE: We do NOT check for '\x00'/'\xe0' function key
                            # prefixes here. In paste mode, '\xe0' is the character
                            # à (U+00E0), not a function key prefix. The getwch()
                            # function key protocol (0x00/0xE0 + scan code) only
                            # applies to actual key presses, not pasted text.
                            buf.append(ch)
                        time.sleep(0.05)
                        if not msvcrt.kbhit():
                            break
                    if buf:
                        text = _combine_surrogates(''.join(buf)).replace('\r\n', '\n').replace('\r', '\n')
                        remaining = text.split('\n')
                        if remaining and not remaining[-1]:
                            remaining = remaining[:-1]
                        lines.extend(remaining)
                finally:
                    _set_echo(True)
            elif paste_mode:
                _set_echo(True)
                sys.stdout.write(first)
                sys.stdout.flush()
        except ImportError:
            import select
            while select.select([sys.stdin], [], [], 0.05)[0]:
                next_line = sys.stdin.readline()
                if not next_line:
                    break
                lines.append(next_line.rstrip('\n\r'))
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
            return '\n'.join(cont_lines)
        if len(lines) > 1:
            _last_input_was_paste = True
        if len(lines) == 1:
            return lines[0]
        return '\n'.join(lines)
    finally:
        if _color_active:
            sys.stdout.write("\033[0m")
            sys.stdout.flush()
