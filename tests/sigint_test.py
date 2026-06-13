"""
Drop this in the same directory and run it standalone:
  python sigint_test.py

It simulates the exact call sequence your app does:
1. Calls prompt_toolkit prompt (as _try_prompt_toolkit_input does)
2. Then checks if SIGINT still works
3. Starts a fake "model output" loop and tells you to press Ctrl+C

Run it, type something at the prompt, press Enter, then press Ctrl+C
during the countdown and see if it stops.
"""
import signal
import sys
import time
import threading

def check_sigint_handler(label):
    h = signal.getsignal(signal.SIGINT)
    print(f"[{label}] SIGINT handler: {h}")
    return h

print("=== SIGINT diagnostic ===\n")
check_sigint_handler("startup")

# Step 1: try prompt_toolkit path (what _try_prompt_toolkit_input does)
print("\nStep 1: Running prompt_toolkit prompt...")
print("(just press Enter)\n")
try:
    import signal as _signal
    from prompt_toolkit import PromptSession
    from prompt_toolkit.key_binding import KeyBindings
    kb = KeyBindings()
    _saved = _signal.getsignal(_signal.SIGINT)
    try:
        session = PromptSession(key_bindings=kb)
        result = session.prompt("test> ", handle_sigint=False)
    finally:
        _signal.signal(_signal.SIGINT, _saved)
    print(f"Got: {result!r}")
except (KeyboardInterrupt, EOFError):
    pass

check_sigint_handler("after prompt_toolkit")

# Step 2: simulate model output loop - press Ctrl+C to stop
print("\nStep 2: Fake model output loop.")
print(">>> PRESS Ctrl+C NOW TO STOP <<<\n")

stop = False
def fake_output():
    global stop
    for i in range(60):
        if stop:
            break
        sys.stdout.write(f"token_{i} ")
        sys.stdout.flush()
        time.sleep(0.3)
    print("\n[output thread done]")

t = threading.Thread(target=fake_output, daemon=True)
t.start()

try:
    t.join()
    print("\n[main thread: loop finished without interrupt]")
except KeyboardInterrupt:
    stop = True
    print("\n[main thread: KeyboardInterrupt received! Ctrl+C WORKS]")

# Step 3: raw signal test
print("\nStep 3: Raw signal delivery test (no threads)")
print(">>> PRESS Ctrl+C in the next 5 seconds <<<")
try:
    time.sleep(5)
    print("[No interrupt received in 5s — Ctrl+C is NOT working]")
except KeyboardInterrupt:
    print("[KeyboardInterrupt received — Ctrl+C IS working]")
