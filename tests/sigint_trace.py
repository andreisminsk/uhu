import signal
import sys
import threading

_last_handler = [signal.getsignal(signal.SIGINT)]
_monitor_stop = threading.Event()

def _monitor():
    import time
    while not _monitor_stop.is_set():
        current = signal.getsignal(signal.SIGINT)
        if current != _last_handler[0]:
            print("\n*** [SIGINT HANDLER CHANGED] ***", file=sys.stderr)
            print("    was: " + str(_last_handler[0]), file=sys.stderr)
            print("    now: " + str(current), file=sys.stderr)
            import traceback
            traceback.print_stack(file=sys.stderr)
            _last_handler[0] = current
        time.sleep(0.05)

monitor_thread = threading.Thread(target=_monitor, daemon=True)
monitor_thread.start()

print("[trace] Initial SIGINT handler: " + str(signal.getsignal(signal.SIGINT)), file=sys.stderr)

from ollama_agent.cli import main
try:
    main()
finally:
    _monitor_stop.set()
