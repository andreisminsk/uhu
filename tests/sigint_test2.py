"""
Targeted test: does queue.get(timeout=...) block Ctrl+C on Windows?
Run it and press Ctrl+C during the "Waiting on queue" phase.
"""
import queue
import sys
import time
import threading

q = queue.Queue()

def producer():
    time.sleep(30)  # never produces anything during test window
    q.put("done")

t = threading.Thread(target=producer, daemon=True)
t.start()

print("Waiting on queue.get(timeout=0.1) loop — press Ctrl+C now:")
try:
    while True:
        try:
            item = q.get(timeout=0.1)
            break
        except queue.Empty:
            sys.stdout.write(".")
            sys.stdout.flush()
except KeyboardInterrupt:
    print("\n[KeyboardInterrupt received during queue.get — WORKS]")
    sys.exit(0)

print("\n[Never got interrupt]")
