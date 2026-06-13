"""
Simulates the EXACT structure of _call_model's streaming path.
Run this and press Ctrl+C during the token output.
"""
import queue as _queue
import sys
import time
import threading
import itertools

# --- Fake Spinner (matches real one) ---
class Spinner:
    def __init__(self, prefix=""):
        self.prefix = prefix
        self._frames = ["◰", "◳", "◲", "◱"]
        self._stop = threading.Event()
        self._thread = None
    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
    def _spin(self):
        first = True
        for frame in itertools.cycle(self._frames):
            if self._stop.is_set(): break
            if first:
                sys.stdout.write(f"\r{self.prefix}{frame} Thinking...\n"); first = False
            else:
                sys.stdout.write(f"\033[A\r{self.prefix}{frame} Thinking...\n")
            sys.stdout.flush()
            self._stop.wait(0.13)
    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None

# --- Fake stream reader (matches real one) ---
def run_test():
    spinner = Spinner(prefix="AI: ")
    spinner.start()

    msg = ""
    first = True
    chunk_queue = _queue.Queue()
    stream_error = [None]
    active_response = [None]

    def _stream_reader():
        try:
            for i in range(200):
                time.sleep(0.15)  # simulate token arrival delay
                chunk_queue.put({"message": {"content": f"word{i} "}, "done": i == 199})
        except Exception as e:
            stream_error[0] = e
        finally:
            chunk_queue.put(None)

    reader_thread = threading.Thread(target=_stream_reader, daemon=True)
    reader_thread.start()

    last_chunk_time = time.time()
    chunk_timeout = 30

    try:
        while True:
            try:
                chunk = chunk_queue.get_nowait()
            except _queue.Empty:
                if time.time() - last_chunk_time > chunk_timeout:
                    print("\n[timeout]")
                    break
                time.sleep(0.05)
                continue

            if chunk is None:
                break

            last_chunk_time = time.time()
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
        resp = active_response[0]
        if resp:
            try: resp.close()
            except: pass
        spinner.stop()
        print("\n[Interrupted — KeyboardInterrupt caught in _call_model]")
        raise

print("Starting fake model output. Press Ctrl+C to interrupt.")
print("=" * 50)
try:
    run_test()
    print("\n[Completed without interrupt]")
except KeyboardInterrupt:
    print("[Back in _send — interrupt propagated correctly]")
