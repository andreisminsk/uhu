#!/usr/bin/env python3
"""Touch-typing practice — record results and manage progress.

This script is designed to be called by the touch-typing skill.
It does NOT run interactive practice — that happens in the chat.

Usage:
    # Record a practice session:
    python typing_practice.py record --lesson beginner-01 --wpm 15.2 --accuracy 87.3 --duration 30

    # Record with error details (use --errors-file for complex data on Windows):
    python typing_practice.py record --lesson beginner-01 --wpm 15.2 --accuracy 87.3 --duration 30 --errors-file errors.json

    # Show progress:
    python typing_practice.py progress [--last N] [--json]
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


def _load_progress():
    """Load progress from JSON file."""
    if os.path.isfile(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"sessions": [], "current_level": "beginner", "current_lesson": 1}


def _save_progress(progress):
    """Save progress to JSON file."""
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def _update_level(progress, lesson_id):
    """Update current level/lesson based on lesson_id."""
    if "-" in lesson_id:
        level, num = lesson_id.rsplit("-", 1)
        try:
            num = int(num)
        except ValueError:
            return
        if level in ("beginner", "intermediate", "advanced"):
            progress["current_level"] = level
            progress["current_lesson"] = num


def cmd_record(args):
    """Record a practice session."""
    progress = _load_progress()

    errors = {}
    if args.errors_file:
        try:
            with open(args.errors_file, "r", encoding="utf-8") as f:
                errors = json.load(f)
        except Exception as e:
            print(f"Error reading errors file: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.errors and args.errors != "{}":
        try:
            errors = json.loads(args.errors)
        except (json.JSONDecodeError, TypeError):
            pass

    session = {
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "lesson_id": args.lesson,
        "wpm": round(args.wpm, 1),
        "accuracy": round(args.accuracy, 1),
        "duration_seconds": round(args.duration, 1),
        "errors": errors,
    }

    progress["sessions"].append(session)
    if len(progress["sessions"]) > 100:
        progress["sessions"] = progress["sessions"][-100:]

    _update_level(progress, args.lesson)
    _save_progress(progress)

    result = {
        "status": "recorded",
        "lesson_id": args.lesson,
        "wpm": round(args.wpm, 1),
        "accuracy": round(args.accuracy, 1),
        "duration_seconds": round(args.duration, 1),
        "total_sessions": len(progress["sessions"]),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_progress(args):
    """Show progress report."""
    progress = _load_progress()
    if not progress.get("sessions"):
        print("No practice sessions recorded yet. Start a practice session first!")
        if args.json:
            print(json.dumps({"error": "no_progress_data"}))
        return

    sessions = progress["sessions"]
    if args.last:
        sessions = sessions[-args.last:]

    if args.json:
        print(json.dumps(progress, ensure_ascii=False, indent=2))
        return

    # Human-readable report
    lines = []
    lines.append("=" * 55)
    lines.append("  Touch Typing Progress Report")
    lines.append("=" * 55)

    level = progress.get("current_level", "beginner")
    lesson = progress.get("current_lesson", 1)
    lines.append(f"  Current level: {level} (lesson {lesson})")
    lines.append("")

    lines.append(f"  Recent sessions (last {len(sessions)}):")
    lines.append("-" * 55)

    for s in sessions:
        date = s.get("date", "?")[:10]
        lid = s.get("lesson_id", "?")
        wpm = s.get("wpm", 0)
        acc = s.get("accuracy", 0)
        dur = s.get("duration_seconds", 0)
        lines.append(f"  {date} | {lid:15s} | {wpm:5.1f} WPM | {acc:5.1f}% | {dur:.0f}s")

    lines.append("-" * 55)

    avg_wpm = sum(s.get("wpm", 0) for s in sessions) / len(sessions)
    avg_acc = sum(s.get("accuracy", 0) for s in sessions) / len(sessions)
    avg_dur = sum(s.get("duration_seconds", 0) for s in sessions) / len(sessions)
    lines.append(f"  Averages: {avg_wpm:.1f} WPM | {avg_acc:.1f}% accuracy | {avg_dur:.0f}s")

    # Trend
    if len(sessions) >= 4:
        mid = len(sessions) // 2
        first_half = sessions[:mid]
        second_half = sessions[mid:]
        first_wpm = sum(s.get("wpm", 0) for s in first_half) / len(first_half)
        second_wpm = sum(s.get("wpm", 0) for s in second_half) / len(second_half)
        first_acc = sum(s.get("accuracy", 0) for s in first_half) / len(first_half)
        second_acc = sum(s.get("accuracy", 0) for s in second_half) / len(second_half)

        wpm_change = second_wpm - first_wpm
        acc_change = second_acc - first_acc

        lines.append("")
        lines.append("  Trend (first half → second half):")
        wpm_arrow = "↑" if wpm_change > 0 else "↓" if wpm_change < 0 else "→"
        acc_arrow = "↑" if acc_change > 0 else "↓" if acc_change < 0 else "→"
        lines.append(f"  WPM: {first_wpm:.1f} → {second_wpm:.1f} ({wpm_arrow} {abs(wpm_change):+.1f})")
        lines.append(f"  Accuracy: {first_acc:.1f}% → {second_acc:.1f}% ({acc_arrow} {abs(acc_change):+.1f}%)")

    # Weak keys
    all_errors = {}
    for s in sessions:
        for key, count in s.get("errors", {}).items():
            all_errors[key] = all_errors.get(key, 0) + count

    if all_errors:
        lines.append("")
        lines.append("  Problem keys (most errors):")
        sorted_errors = sorted(all_errors.items(), key=lambda x: -x[1])[:10]
        for key, count in sorted_errors:
            bar = "█" * min(count, 20)
            lines.append(f"    '{key}': {count:3d} {bar}")

    # Best session
    best_wpm = max(sessions, key=lambda s: s.get("wpm", 0))
    best_acc = max(sessions, key=lambda s: s.get("accuracy", 0))
    lines.append("")
    lines.append(f"  Best WPM: {best_wpm.get('wpm', 0):.1f} ({best_wpm.get('lesson_id', '?')})")
    lines.append(f"  Best accuracy: {best_acc.get('accuracy', 0):.1f}% ({best_acc.get('lesson_id', '?')})")

    # Recommendation
    lines.append("")
    if avg_acc < 85:
        lines.append("  📌 Recommendation: Focus on accuracy — repeat lessons for weak keys.")
    elif avg_acc < 95:
        lines.append("  📌 Recommendation: Good accuracy — try increasing speed on current level.")
    else:
        lines.append("  📌 Recommendation: Excellent accuracy — ready to advance to next lesson!")

    lines.append("=" * 55)
    print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Touch-typing practice tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # record command
    rec = subparsers.add_parser("record", help="Record a practice session")
    rec.add_argument("--lesson", required=True, help="Lesson ID (e.g., beginner-01)")
    rec.add_argument("--wpm", type=float, required=True, help="Words per minute")
    rec.add_argument("--accuracy", type=float, required=True, help="Accuracy percentage")
    rec.add_argument("--duration", type=float, default=30, help="Duration in seconds")
    rec.add_argument("--errors", default="{}", help="JSON string of error counts per key")
    rec.add_argument("--errors-file", default=None, help="Path to JSON file with error counts")

    # progress command
    prg = subparsers.add_parser("progress", help="Show progress report")
    prg.add_argument("--last", type=int, default=None, help="Show only last N sessions")
    prg.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.command == "record":
        cmd_record(args)
    elif args.command == "progress":
        cmd_progress(args)
    else:
        parser.print_help()
        print("\nExamples:")
        print("  Record a session:  python typing_practice.py record --lesson beginner-01 --wpm 15.2 --accuracy 87.3 --duration 30")
        print("  Show progress:     python typing_practice.py progress")
        print("  Show progress JSON: python typing_practice.py progress --json")


if __name__ == "__main__":
    main()
