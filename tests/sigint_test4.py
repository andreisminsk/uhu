"""
Paste this into your project directory and run it standalone.
It simulates the full _send -> _call_model -> _feedback_loop chain.
Press Ctrl+C during the fake token output and watch what happens.
"""
import queue as _queue
import sys
import time
import threading
import signal

print(f"[startup] SIGINT handler: {signal.getsignal(signal.SIGINT)}")

# ── fake spinner ──────────────────────────────────────────────────────────────
import itertools
class Spinner:
    def __init__(self, prefix=""):
        self.prefix = prefix
        self._stop = threading.Event()
        self._thread = None
    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
    def _spin(self):
        first = True
        for frame in itertools.cycle(["◰","◳","◲","◱"]):
            if self._stop.is_set(): break
            if first:
                sys.stdout.write(f"\r{self.prefix}{frame} Thinking...\n"); first = False
            else:
                sys.stdout.write(f"\033[A\r{self.prefix}{frame} Thinking...\n")
            sys.stdout.flush()
            self._stop.wait(0.13)
    def stop(self):
        self._stop.set()
        if self._thread: self._thread.join(timeout=1); self._thread = None

# ── fake _call_model (streaming) ──────────────────────────────────────────────
def fake_call_model():
    print("[call_model] entered")
    spinner = Spinner(prefix="AI: ")
    spinner.start()
    msg = ""
    first = True
    chunk_queue = _queue.Queue()
    stream_error = [None]

    def _stream_reader():
        try:
            for i in range(200):
                time.sleep(0.15)
                chunk_queue.put({"message": {"content": f"word{i} "}, "done": i==199})
        except Exception as e:
            stream_error[0] = e
        finally:
            chunk_queue.put(None)

    threading.Thread(target=_stream_reader, daemon=True).start()
    last_chunk_time = time.time()

    try:
        while True:
            try:
                chunk = chunk_queue.get_nowait()
            except _queue.Empty:
                if time.time() - last_chunk_time > 30:
                    break
                time.sleep(0.05)
                continue
            if chunk is None:
                break
            token = chunk.get("message", {}).get("content", "")
            if first and token:
                spinner.stop()
                sys.stdout.write("AI: ")
                sys.stdout.flush()
                first = False
            if not first:
                print(token, end="", flush=True)
            msg += token
    except KeyboardInterrupt:
        print("\n[call_model] KeyboardInterrupt caught — re-raising")
        spinner.stop()
        raise

    spinner.stop()
    print("\n")
    return msg

# ── fake _feedback_loop ───────────────────────────────────────────────────────
def fake_feedback_loop():
    print("[feedback_loop] entered")
    for round_num in range(3):
        print(f"[feedback_loop] round {round_num}")
        try:
            msg = fake_call_model()
        except KeyboardInterrupt:
            print(f"[feedback_loop] KeyboardInterrupt in round {round_num} — returning")
            return
        print(f"[feedback_loop] round {round_num} done, msg length={len(msg)}")

# ── fake _send ────────────────────────────────────────────────────────────────
def fake_send():
    print("[send] entered")
    try:
        msg = fake_call_model()
        print(f"[send] first call done, calling feedback_loop")
        fake_feedback_loop()
    except KeyboardInterrupt:
        print("\n[send] KeyboardInterrupt — returning to prompt")
        return
    print("[send] completed normally")

# ── main ──────────────────────────────────────────────────────────────────────
print("Simulating full send->call_model->feedback_loop chain.")
print("Press Ctrl+C during token output.\n")
print(f"[before send] SIGINT handler: {signal.getsignal(signal.SIGINT)}")
fake_send()
print("\n[back at prompt]")
