"""Regression tests: Ctrl+C during Spinner/Thinking streaming.

Two user-visible bugs fixed:
1. AI green color (\\033[38;2;0;255;0m) leaked past KeyboardInterrupt —
   the next "You:" prompt and user text rendered green. Fix: _ai_color_off()
   on every abort path in OllamaNativeBackend (E2E tests below).
2. Spinner.stop() abandoned a possibly-alive redraw thread after a 1s join —
   the zombie re-erased/redrew over the freshly rendered input prompt,
   desyncing prompt_toolkit's cursor (duplicated input after Enter). New
   contract: stop() joins the thread and is the single owner of screen
   erasure; the render thread never erases and refuses to draw once stop
   was requested (SpinnerGuard unit tests).

Run: python -m pytest tests/test_interrupt_regression.py -v
"""
import io
import os
import re
import select
import signal
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ollama_agent.spinner import Spinner  # noqa: E402

ANSI_AI = b"\x1b[38;2;0;255;0m"
FRAME_RE = re.compile("[\u25f0\u25f1\u25f2\u25f3]")  # ◰◳◲◱


# ───────────────────────────── unit tests ─────────────────────────────

class _RecStdout(io.StringIO):
    """StringIO that claims to be a TTY so Spinner enables its color paths."""
    def isatty(self):
        return True
    def flush(self):
        pass


class SpinnerGuard(unittest.TestCase):
    """stop() owns erasure; the render thread cannot paint after stop()."""

    def test_stop_erases_drawn_lines(self):
        real, sys.stdout = sys.stdout, _RecStdout()
        try:
            sp = Spinner(color="\x1b[38;2;0;255;0m")
            sp.start()
            time.sleep(0.4)                      # ≥1 frame drawn
            self.assertEqual(sp._last_lines, 1)  # owns the spinner row
            sp.stop()
            self.assertEqual(sp._last_lines, 0)  # erased, ownership released
            self.assertIn("\x1b[1A\x1b[J", sys.stdout.getvalue())
        finally:
            sys.stdout = real

    def test_stop_idempotent_after_return(self):
        """A second stop() must not emit extra erase bytes (no double-clean)."""
        real, sys.stdout = sys.stdout, _RecStdout()
        try:
            sp = Spinner(color=None)
            sp.start()
            time.sleep(0.4)
            sp.stop()
            first = sys.stdout.getvalue()
            sp.stop()
            sp._erase()
            second = sys.stdout.getvalue()
        finally:
            sys.stdout = real
        self.assertEqual(first, second)

    def test_zombie_thread_cannot_redraw(self):
        """A render thread that lost the join race must paint nothing."""
        real, sys.stdout = sys.stdout, _RecStdout()
        started = threading.Event()
        orig_render = Spinner._render

        def slow_render(self, frame):
            started.set()
            time.sleep(0.8)              # simulate KI-unwind starvation
            orig_render(self, frame)     # must early-return: stop already set

        try:
            Spinner._render = slow_render
            sp = Spinner(color=None)
            sp.start()
            self.assertTrue(started.wait(2))
            sp.stop()                    # returns while _render still sleeping
            baseline = sys.stdout.getvalue()
            time.sleep(0.6)              # zombie's window to paint
            after = sys.stdout.getvalue()
        finally:
            Spinner._render = orig_render
            sys.stdout = real
        tail = after[len(baseline):]
        self.assertEqual(FRAME_RE.findall(tail), [],
                         "zombie spinner repainted after stop() returned")

    def test_append_thinking_bounded(self):
        sp = Spinner(max_thinking_lines=5)
        for i in range(500):
            sp.append_thinking(f"line {i}\n")
        self.assertLessEqual(len(sp.thinking_text.splitlines()), 7)


# ─────────────────────────── PTY end-to-end ───────────────────────────
# Drives the REAL OllamaNativeBackend._call_streaming (fake httpx transport)
# inside a forkpty child; the child self-interrupts via Timer→SIGINT.
# NOTE: multiline=False → readline/input() path. prompt_toolkit's event loop
# stalls under a raw pty (CPR + asyncio select); these tests assert backend/
# spinner behavior, not PT rendering (SpinnerGuard + manual runs cover it).

CHILD_SCRIPT = r'''
import faulthandler, json, os, signal, sys, threading, time
os.environ.setdefault("TERM", "xterm-256color")
sys.path.insert(0, sys.argv[4])
faulthandler.dump_traceback_later(15, exit=True)
from ollama_agent.backends import OllamaNativeBackend
from ollama_agent.input_utils import read_full_input

DLY = float(sys.argv[1]); mode = sys.argv[2]

def mark(m):
    sys.stderr.write("\n[MARK] " + m + "\n"); sys.stderr.flush()

def _read():
    return read_full_input("You: ", multiline=False)

class FakeResp:
    def raise_for_status(self): pass
    def iter_lines(self):
        if mode == "think":
            for i in range(20):
                time.sleep(0.05)
                yield json.dumps({"message": {"thinking": "tl %d\n" % i}})
        for tok in ["Hello ", "brave ", "new ", "world\n"]:
            time.sleep(0.30)
            yield json.dumps({"message": {"content": tok}})
        time.sleep(0.05)
        yield json.dumps({"message": {"content": "end\n"}, "done": True})
    def close(self): pass
class FakeStream:
    def __enter__(self): return FakeResp()
    def __exit__(self, *a): return False
class FakeClient:
    @property
    def _client(self): return self
    def stream(self, method, url, json=None):
        mark("reader started")
        return FakeStream()

be = OllamaNativeBackend(host="http://localhost:11434", model="fake",
                         ctx_size=8192, thinking=True)
be.client = FakeClient()

res = _read()
mark("READ " + repr(str(res)))
threading.Timer(DLY, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
try:
    be.call([{"role": "user", "content": str(res)}], stream=True)
    mark("NO-KI")
except KeyboardInterrupt:
    mark("KI-CAUGHT")

res2 = _read()
mark("READ2 " + repr(str(res2))[:60])
mark("CHILD-DONE")
'''


def _run_child_pty(interrupt_delay, mode, tag, timeout=15):
    """Fork a pty child, feed tag+Enter at each of its two reads, return bytes."""
    import fcntl
    import struct
    import termios

    with tempfile.NamedTemporaryFile(suffix=".tag", delete=False) as tf:
        tagfile = tf.name  # child writes result here (kept for future use)
    script = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False)
    script.write(CHILD_SCRIPT)
    script.close()
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    pid, fd = os.forkpty()
    if pid == 0:
        try:
            os.execve(sys.executable,
                      [sys.executable, script.name, str(interrupt_delay), mode, "TAG",
                       str(REPO_ROOT)], env)
        except Exception:
            os._exit(127)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 100, 0, 0))

    buf = b""
    fed = 0
    t0 = time.time()
    try:
        while time.time() - t0 < timeout:
            r, _, _ = select.select([fd], [], [], 0.2)
            if r:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                buf += data
            # Never leave a CPR query unanswered (prompt_toolkit stalls on it)
            while b"\x1b[6n" in buf:
                os.write(fd, b"\x1b[1;1R")
                buf = buf.replace(b"\x1b[6n", b"", 1)
            # Feed #1: the first read. Feed #2: once the interrupt is handled.
            if fed == 0 and b"You: " in buf:
                time.sleep(0.4)
                os.write(fd, tag.encode() + b"\r")
                fed = 1
            elif fed == 1 and (b"KI-CAUGHT" in buf or b"NO-KI" in buf):
                time.sleep(0.4)
                os.write(fd, tag.encode() + b"\r")
                fed = 2
            if b"CHILD-DONE" in buf:
                break
    finally:
        try:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
        except (ChildProcessError, ProcessLookupError):
            pass
        os.unlink(script.name)
        os.unlink(tagfile)
    return buf


@unittest.skipUnless(hasattr(os, "forkpty"), "requires forkpty (POSIX)")
class StreamingInterruptE2E(unittest.TestCase):
    TAG = "E2ETAGQ"
    # Child timing, "content" mode: content tokens × 0.30s (no thinking phase).
    DURING_THINK = 0.30     # interrupt lands inside the thinking phase (1.0s)
    DURING_CONTENT = 0.55   # inside the 2nd green content token

    def test_ctrl_c_during_content_resets_ai_color(self):
        """KI after green content started → reset emitted before child notices KI."""
        buf = _run_child_pty(self.DURING_CONTENT, "content", self.TAG)
        self.assertIn(self.TAG.encode(), buf, "child never received input")
        self.assertIn(b"KI-CAUGHT", buf)
        self.assertIn(ANSI_AI, buf, "content never turned green — scenario invalid")
        ki = buf.find(b"KI-CAUGHT")
        last_green = buf.rfind(ANSI_AI)
        self.assertLess(last_green, ki)
        seg = buf[last_green:ki]
        self.assertIn(b"\x1b[0m", seg,
                      "AI green color not reset on the abort path before KI was handled")

    def test_ctrl_c_no_green_reenabled_and_prompt_clean(self):
        """Backend must not re-emit AI green between KI and the next user read.

        Verified pty layout: 'KI-CAUGHT' → 'You: <tag>' echo → 'READ2' mark.
        The property is position-independent: the [KI, READ2) window must
        never contain the AI green SGR.
        """
        buf = _run_child_pty(self.DURING_CONTENT, "content", self.TAG)
        self.assertIn(b"KI-CAUGHT", buf)
        ki = buf.find(b"KI-CAUGHT")
        read2 = buf.find(b"READ2")
        self.assertGreaterEqual(read2, 0, "child never reached the second read")
        seg = buf[ki:read2]
        self.assertNotIn(ANSI_AI, seg, "AI green re-enabled after interrupt")

    def test_ctrl_c_no_zombie_frames_after_ki(self):
        """Interrupt during thinking → no spinner frame may be drawn afterwards."""
        buf = _run_child_pty(self.DURING_THINK, "think", self.TAG, timeout=20)
        self.assertIn(b"KI-CAUGHT", buf)
        ki = buf.find(b"KI-CAUGHT")
        tail = buf[ki:].decode("utf-8", "replace")
        self.assertEqual(FRAME_RE.findall(tail), [],
                         f"spinner redrew after the interrupt was handled: {tail[-200:]!r}")
        self.assertIn(b"You: ", buf[ki:], "second prompt never appeared")

    def test_plain_streaming_path_still_works(self):
        """Sanity: without interrupt the stream completes (harness validity)."""
        buf = _run_child_pty(999, "content", self.TAG, timeout=20)
        self.assertIn(b"NO-KI", buf)
        self.assertIn(b"world", buf)


if __name__ == "__main__":
    unittest.main(verbosity=2)
