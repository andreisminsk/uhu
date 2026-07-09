#!/usr/bin/env python3
"""Standalone interactive touch-typing tutor with curses UI.

Run directly from the terminal (NOT through the skill system):
    python typing_tutor.py
    python typing_tutor.py --level beginner
    python typing_tutor.py --lesson 3
    python typing_tutor.py --level advanced --duration 120

Features:
    - Real-time curses UI with color-coded feedback
    - 24 progressive lessons (beginner → advanced)
    - WPM and accuracy tracking
    - Progress saved between sessions
    - Visual keyboard with finger hints
    - Problem key analysis
"""

import argparse
import json
import os
import sys
import time

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
PROGRESS_FILE = os.path.join(SKILL_DIR, "progress.json")

# Import lesson definitions from generate_lesson
sys.path.insert(0, SCRIPT_DIR)
from generate_lesson import LESSONS, generate_lesson_text


# ── Progress ────────────────────────────────────────────────────────────

def load_progress():
    if os.path.isfile(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"sessions": [], "current_level": "beginner", "current_lesson": 1}


def save_progress(progress):
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


# ── Finger-to-key mapping for visual keyboard ──────────────────────────

FINGER_COLORS = {
    "L5": 1, "L4": 2, "L3": 3, "L2": 4, "L1": 5,
    "R1": 6, "R2": 7, "R3": 8, "R4": 9, "R5": 10,
}

KEY_FINGER = {
    # Left hand
    "1": "L5", "2": "L4", "3": "L3", "4": "L2", "5": "L1",
    "q": "L5", "w": "L4", "e": "L3", "r": "L2", "t": "L1",
    "a": "L5", "s": "L4", "d": "L3", "f": "L2", "g": "L1",
    "z": "L5", "x": "L4", "c": "L3", "v": "L2", "b": "L1",
    # Right hand
    "6": "R1", "7": "R2", "8": "R3", "9": "R4", "0": "R5",
    "y": "R1", "u": "R2", "i": "R3", "o": "R4", "p": "R5",
    "h": "R1", "j": "R2", "k": "R3", "l": "R4", ";": "R5",
    "n": "R1", "m": "R2", ",": "R3", ".": "R4", "/": "R5",
}

KEYBOARD_ROWS = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl;"),
    list("zxcvbnm,./"),
]


# ── Curses UI ───────────────────────────────────────────────────────────

def run_tutor(stdscr, lesson_num, text, max_duration):
    """Main curses typing tutor loop."""
    import curses

    # Initialize colors
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)    # correct
    curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)      # error
    curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)     # info
    curses.init_pair(4, curses.COLOR_YELLOW, curses.COLOR_BLACK)   # highlight
    curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLUE)     # header
    curses.init_pair(6, curses.COLOR_MAGENTA, curses.COLOR_BLACK)  # left hand
    curses.init_pair(7, curses.COLOR_BLUE, curses.COLOR_BLACK)     # right hand
    curses.init_pair(8, curses.COLOR_WHITE, curses.COLOR_BLACK)    # dim key
    curses.init_pair(9, curses.COLOR_BLACK, curses.COLOR_WHITE)    # active key

    curses.noecho()
    curses.cbreak()
    stdscr.nodelay(False)
    stdscr.keypad(True)

    # State
    typed = []
    start_time = None
    finished = False
    errors = {}
    paused = False

    # Layout
    max_y, max_x = stdscr.getmaxyx()
    header_y = 0
    text_start_y = 3
    stats_y = max_y - 8
    kb_start_y = max_y - 6
    help_y = max_y - 1

    lesson_title = LESSONS.get(lesson_num, {}).get("title", f"Lesson {lesson_num}")

    def _draw_keyboard(highlight_key=None):
        """Draw a visual keyboard with finger color coding."""
        for row_idx, row in enumerate(KEYBOARD_ROWS):
            y = kb_start_y + row_idx
            offset = row_idx  # stagger rows like a real keyboard
            for col_idx, key in enumerate(row):
                x = 2 + offset + col_idx * 2
                if x >= max_x - 1 or y >= max_y - 1:
                    continue

                finger = KEY_FINGER.get(key, "")
                is_home = key in ("f", "j")

                if key == highlight_key:
                    try:
                        stdscr.addch(y, x, key.upper() if key.isalpha() else key[0],
                                     curses.color_pair(9) | curses.A_BOLD)
                    except curses.error:
                        pass
                elif finger.startswith("L"):
                    try:
                        ch = key.upper() if key.isalpha() else key[0]
                        attr = curses.color_pair(6) | (curses.A_BOLD if is_home else curses.A_DIM)
                        stdscr.addch(y, x, ch, attr)
                    except curses.error:
                        pass
                elif finger.startswith("R"):
                    try:
                        ch = key.upper() if key.isalpha() else key[0]
                        attr = curses.color_pair(7) | (curses.A_BOLD if is_home else curses.A_DIM)
                        stdscr.addch(y, x, ch, attr)
                    except curses.error:
                        pass
                else:
                    try:
                        stdscr.addch(y, x, key[0], curses.A_DIM)
                    except curses.error:
                        pass

    def _draw():
        stdscr.clear()

        # Header
        header = f" ⌨ Touch Typing Tutor — {lesson_title} "
        stdscr.addstr(header_y, 0, header, curses.color_pair(5) | curses.A_BOLD)
        stdscr.addstr(header_y, len(header), " " * max(0, max_x - len(header)),
                      curses.color_pair(5))

        # Separator
        stdscr.addstr(1, 0, " " * max_x, curses.A_DIM)

        # Text display — wrap to screen width
        text_lines = []
        current_line = ""
        words = text.split(" ")
        for word in words:
            if len(current_line) + len(word) + 1 > max_x - 4:
                text_lines.append(current_line)
                current_line = word
            else:
                current_line = current_line + " " + word if current_line else word
        if current_line:
            text_lines.append(current_line)

        # Show typed portion with color coding
        char_count = 0
        for line_idx, line in enumerate(text_lines):
            y = text_start_y + line_idx
            if y >= stats_y - 1:
                break
            for ch_idx, ch in enumerate(line):
                global_pos = char_count + ch_idx
                x = 2 + ch_idx

                if global_pos < len(typed):
                    # Already typed
                    if global_pos < len(text) and typed[global_pos] == text[global_pos]:
                        try:
                            stdscr.addch(y, x, ch, curses.color_pair(1))
                        except curses.error:
                            pass
                    else:
                        try:
                            stdscr.addch(y, x, ch, curses.color_pair(2) | curses.A_BOLD)
                        except curses.error:
                            pass
                elif global_pos == len(typed):
                    # Current position — cursor
                    try:
                        stdscr.addch(y, x, ch, curses.color_pair(4) | curses.A_BOLD | curses.A_UNDERLINE)
                    except curses.error:
                        pass
                else:
                    try:
                        stdscr.addch(y, x, ch, curses.A_DIM)
                    except curses.error:
                        pass

            char_count += len(line) + 1

        # Stats
        elapsed = time.time() - start_time if start_time else 0
        remaining = max(0, max_duration - elapsed) if max_duration else 0

        if start_time and elapsed > 0:
            correct_so_far = sum(1 for i, c in enumerate(typed) if i < len(text) and c == text[i])
            running_wpm = (correct_so_far / 5) / (elapsed / 60) if elapsed > 1 else 0
            running_acc = (correct_so_far / len(typed) * 100) if typed else 100
        else:
            running_wpm = 0
            running_acc = 100

        # Stats line
        stats_line = f" WPM: {running_wpm:.0f}  |  Accuracy: {running_acc:.0f}%  |  "
        if max_duration:
            stats_line += f"Time: {int(remaining)}s  |  "
        stats_line += f"Progress: {len(typed)}/{len(text)} "
        try:
            stdscr.addstr(stats_y, 0, stats_line, curses.color_pair(3))
        except curses.error:
            pass

        # Progress bar
        bar_len = max_x - 2
        progress = len(typed) / len(text) if text else 0
        filled = int(bar_len * progress)
        bar = "█" * filled + "░" * (bar_len - filled)
        try:
            stdscr.addstr(stats_y + 1, 1, bar, curses.color_pair(3))
        except curses.error:
            pass

        # Keyboard
        next_key = text[len(typed)] if len(typed) < len(text) else None
        _draw_keyboard(highlight_key=next_key)

        # Help
        help_text = " ESC: end session  |  Backspace: delete  |  Type the highlighted character "
        try:
            stdscr.addstr(help_y, 0, help_text, curses.A_DIM)
        except curses.error:
            pass

        stdscr.refresh()

    # Initial draw
    _draw()

    while True:
        try:
            key = stdscr.getch()
        except KeyboardInterrupt:
            break

        if key == 27:  # ESC
            break

        if finished:
            break

        # Start timer on first keypress
        if start_time is None:
            start_time = time.time()

        # Handle backspace
        if key in (curses.KEY_BACKSPACE, 127, 8):
            if typed:
                typed.pop()
            _draw()
            continue

        # Handle regular character
        if key >= 32 and key <= 126:
            ch = chr(key)
            typed.append(ch)

            # Track errors
            pos = len(typed) - 1
            if pos < len(text) and ch != text[pos]:
                expected = text[pos]
                errors[expected] = errors.get(expected, 0) + 1

            # Check if finished
            if len(typed) >= len(text):
                finished = True

        _draw()

        # Check time limit
        if start_time and max_duration:
            elapsed = time.time() - start_time
            if elapsed >= max_duration:
                break

    end_time = time.time()
    duration = end_time - start_time if start_time else 0

    # Compute final stats
    correct = 0
    final_errors = {}
    min_len = min(len(text), len(typed))
    for i in range(min_len):
        if typed[i] == text[i]:
            correct += 1
        else:
            expected = text[i] if text[i] != " " else "␣"
            final_errors[expected] = final_errors.get(expected, 0) + 1

    extra = max(0, len(typed) - len(text))
    missing = max(0, len(text) - len(typed))

    total_chars = len(text)
    accuracy = (correct / total_chars * 100) if total_chars > 0 else 0
    minutes = duration / 60
    wpm = (correct / 5) / minutes if minutes > 0 else 0

    # Merge errors
    for k, v in errors.items():
        final_errors[k] = final_errors.get(k, 0) + v

    return wpm, accuracy, duration, final_errors, "".join(typed)


def show_results(stdscr, wpm, accuracy, duration, errors, lesson_num, text, typed):
    """Show results screen after practice."""
    import curses

    stdscr.clear()
    max_y, max_x = stdscr.getmaxyx()

    y = 2
    stdscr.addstr(y, 2, "╔══════════════════════════════════════════╗", curses.color_pair(3) | curses.A_BOLD)
    y += 1
    stdscr.addstr(y, 2, "║        Session Complete!                 ║", curses.color_pair(3) | curses.A_BOLD)
    y += 1
    stdscr.addstr(y, 2, "╚══════════════════════════════════════════╝", curses.color_pair(3) | curses.A_BOLD)
    y += 2

    # Stats
    stdscr.addstr(y, 4, f"  Lesson:     {LESSONS.get(lesson_num, {}).get('title', lesson_num)}", curses.A_BOLD)
    y += 1
    stdscr.addstr(y, 4, f"  WPM:        {wpm:.1f}", curses.color_pair(1) | curses.A_BOLD)
    y += 1

    # Color-code accuracy
    if accuracy >= 95:
        acc_color = curses.color_pair(1) | curses.A_BOLD
    elif accuracy >= 85:
        acc_color = curses.color_pair(4) | curses.A_BOLD
    else:
        acc_color = curses.color_pair(2) | curses.A_BOLD
    stdscr.addstr(y, 4, f"  Accuracy:   {accuracy:.1f}%", acc_color)
    y += 1
    stdscr.addstr(y, 4, f"  Duration:   {duration:.1f}s", curses.A_NORMAL)
    y += 1
    stdscr.addstr(y, 4, f"  Characters: {len(typed)}/{len(text)}", curses.A_NORMAL)
    y += 2

    # Problem keys
    if errors:
        stdscr.addstr(y, 4, "  Problem keys:", curses.A_BOLD)
        y += 1
        sorted_errors = sorted(errors.items(), key=lambda x: -x[1])[:8]
        for key, count in sorted_errors:
            bar = "█" * min(count, 15)
            stdscr.addstr(y, 6, f"  '{key}': {count:3d} {bar}", curses.color_pair(2))
            y += 1
    y += 1

    # Recommendation
    if accuracy < 85:
        stdscr.addstr(y, 4, "  📌 Focus on accuracy — repeat this lesson.", curses.color_pair(4))
    elif accuracy < 95:
        stdscr.addstr(y, 4, "  📌 Good! Try increasing speed on this level.", curses.color_pair(4))
    else:
        stdscr.addstr(y, 4, "  📌 Excellent! Ready for the next lesson.", curses.color_pair(1) | curses.A_BOLD)
    y += 2

    stdscr.addstr(y, 4, "  Press any key to exit...", curses.A_DIM)
    stdscr.refresh()

    # Wait for keypress
    stdscr.nodelay(False)
    stdscr.getch()


def show_menu(stdscr):
    """Show lesson selection menu."""
    import curses

    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLUE)

    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)

    progress = load_progress()
    current_level = progress.get("current_level", "beginner")
    current_lesson = progress.get("current_lesson", 1)

    # Build lesson list
    lesson_list = sorted(LESSONS.keys())
    selected = current_lesson - 1  # Default to current lesson
    offset = 0

    while True:
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        # Header
        stdscr.addstr(0, 0, " ⌨ Touch Typing Tutor — Select Lesson ", curses.color_pair(5) | curses.A_BOLD)
        stdscr.addstr(0, 40, " " * max(0, max_x - 40), curses.color_pair(5))
        stdscr.addstr(1, 0, f" Current: {current_level} lesson {current_lesson}", curses.color_pair(3))
        stdscr.addstr(2, 0, " ↑/↓: select  |  Enter: start  |  q: quit ", curses.A_DIM)

        # Lesson list
        visible = max_y - 5
        if selected < offset:
            offset = selected
        elif selected >= offset + visible:
            offset = selected - visible + 1

        for i, num in enumerate(lesson_list):
            if i < offset or i >= offset + visible:
                continue
            y = 4 + i - offset
            lesson = LESSONS[num]
            level = lesson["level"]
            title = lesson["title"]
            keys = ", ".join(lesson["focus_keys"][:6])

            # Check if we have stats for this lesson
            sessions = [s for s in progress.get("sessions", []) if s.get("lesson_id", "").endswith(f"-{num:02d}")]
            best_wpm = max((s.get("wpm", 0) for s in sessions), default=0)
            best_acc = max((s.get("accuracy", 0) for s in sessions), default=0)

            marker = "→" if i == selected else " "
            level_tag = {"beginner": "🟢", "intermediate": "🟡", "advanced": "🔴"}.get(level, "⚪")

            line = f" {marker} {level_tag} {num:2d}. {title}"
            if best_wpm > 0:
                line += f" (best: {best_wpm:.0f} WPM, {best_acc:.0f}%)"

            if i == selected:
                try:
                    stdscr.addstr(y, 0, line, curses.color_pair(4) | curses.A_BOLD)
                except curses.error:
                    pass
            else:
                try:
                    stdscr.addstr(y, 0, line, curses.A_NORMAL)
                except curses.error:
                    pass

            # Show focus keys on next line for selected
            if i == selected:
                try:
                    stdscr.addstr(y + 1, 4, f"Keys: {keys}", curses.A_DIM)
                except curses.error:
                    pass

        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_UP and selected > 0:
            selected -= 1
        elif key == curses.KEY_DOWN and selected < len(lesson_list) - 1:
            selected += 1
        elif key in (10, 13):  # Enter
            return lesson_list[selected]
        elif key in (ord('q'), ord('Q'), 27):  # q or ESC
            return None


def main():
    parser = argparse.ArgumentParser(
        description="Interactive touch-typing tutor (standalone — run directly, not through skill system)",
        epilog="Run without arguments to see the lesson selection menu."
    )
    parser.add_argument("--lesson", type=int, default=None,
                        help="Lesson number (1-24). If not specified, shows menu.")
    parser.add_argument("--level", choices=["beginner", "intermediate", "advanced"],
                        default=None, help="Start from first lesson of this level")
    parser.add_argument("--duration", type=int, default=0,
                        help="Time limit in seconds (0 = no limit)")
    parser.add_argument("--text", default=None,
                        help="Custom text to type (overrides lesson)")
    args = parser.parse_args()

    # Determine lesson
    if args.text:
        # Custom text mode
        text = args.text
        lesson_num = 0
        lesson_title = "Custom Text"
    elif args.lesson:
        lesson_num = args.lesson
        if lesson_num not in LESSONS:
            print(f"Error: Lesson {lesson_num} not found. Available: 1-{max(LESSONS.keys())}")
            sys.exit(1)
        text = generate_lesson_text(lesson_num)
        lesson_title = LESSONS[lesson_num]["title"]
    elif args.level:
        level_map = {"beginner": 1, "intermediate": 9, "advanced": 17}
        lesson_num = level_map.get(args.level, 1)
        text = generate_lesson_text(lesson_num)
        lesson_title = LESSONS[lesson_num]["title"]
    else:
        # Show menu
        try:
            import curses
            lesson_num = curses.wrapper(show_menu)
            if lesson_num is None:
                print("Goodbye!")
                return
            text = generate_lesson_text(lesson_num)
            lesson_title = LESSONS[lesson_num]["title"]
        except Exception as e:
            print(f"Error: {e}")
            print("Try specifying a lesson: python typing_tutor.py --lesson 1")
            return

    if not text:
        print("Error: No text to type.")
        sys.exit(1)

    # Truncate very long text
    if len(text) > 600:
        text = text[:600]

    max_duration = args.duration if args.duration > 0 else 0

    # Run the tutor
    try:
        import curses
        wpm, accuracy, duration, errors, typed = curses.wrapper(
            run_tutor, lesson_num, text, max_duration
        )
        # Show results
        curses.wrapper(show_results, wpm, accuracy, duration, errors, lesson_num, text, typed)
    except ImportError:
        print("curses is required for interactive mode.")
        print("Install it with: pip install windows-curses")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nSession cancelled.")
        return

    # Save progress
    progress = load_progress()
    lesson_id = f"{LESSONS.get(lesson_num, {}).get('level', 'practice')}-{lesson_num:02d}" if lesson_num else "custom-00"
    session = {
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "lesson_id": lesson_id,
        "wpm": round(wpm, 1),
        "accuracy": round(accuracy, 1),
        "duration_seconds": round(duration, 1),
        "errors": errors,
    }
    progress["sessions"].append(session)
    if len(progress["sessions"]) > 100:
        progress["sessions"] = progress["sessions"][-100:]

    # Update level
    if lesson_num and lesson_num in LESSONS:
        level = LESSONS[lesson_num]["level"]
        progress["current_level"] = level
        progress["current_lesson"] = lesson_num

    save_progress(progress)

    # Print summary (after curses exits)
    print(f"\n{'='*50}")
    print(f"  Lesson: {lesson_title}")
    print(f"  WPM: {wpm:.1f}")
    print(f"  Accuracy: {accuracy:.1f}%")
    print(f"  Duration: {duration:.1f}s")
    if errors:
        print(f"  Problem keys: {', '.join(sorted(errors.keys()))}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
