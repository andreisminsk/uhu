#!/usr/bin/env python3
"""Python tutor progress tracker and code runner for the learn-python skill."""

import json
import os
import sys
import tempfile
import traceback
from datetime import datetime

# Fix Windows console encoding for emoji and non-ASCII output
if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr:
    sys.stderr.reconfigure(encoding='utf-8')

# ── Configuration ────────────────────────────────────────────────────────

PROGRESS_DIR = os.path.join(os.path.expanduser("~"), ".uhu", "learn-python")
PROGRESS_FILE = os.path.join(PROGRESS_DIR, "progress.json")

LESSONS = {
    # Module 1: Fundamentals
    "01-print": "Hello World & print()",
    "02-variables": "Variables & Types",
    "03-arithmetic": "Arithmetic & Expressions",
    "04-input": "Input & Output",
    "05-strings": "String Operations",
    "06-logic": "Comparison & Logic",
    "07-conditionals": "Conditional Statements",
    "08-m1-review": "Module 1 Review",
    # Module 2: Data Structures
    "09-lists": "Lists",
    "10-list-ops": "List Operations",
    "11-tuples-sets": "Tuples & Sets",
    "12-dicts": "Dictionaries",
    "13-formatting": "String Formatting",
    "14-files": "Working with Files",
    "15-errors": "Error Handling",
    "16-m2-review": "Module 2 Review",
    # Module 3: Functions & Modularity
    "17-functions": "Defining Functions",
    "18-kwargs": "Default & Keyword Arguments",
    "19-scope": "Scope & Closures",
    "20-lambda": "Lambda & Higher-Order Functions",
    "21-modules": "Modules & Imports",
    "22-comprehensions": "List Comprehensions",
    "23-decorators": "Decorators",
    "24-m3-review": "Module 3 Review",
    # Module 4: OOP & Beyond
    "25-classes": "Classes & Objects",
    "26-inheritance": "Inheritance & Polymorphism",
    "27-magic": "Magic Methods",
    "28-iterators": "Iterators & Generators",
    "29-context": "Context Managers",
    "30-json-api": "Working with JSON & APIs",
    "31-testing": "Testing Basics",
    "32-m4-review": "Module 4 Review",
    # Module 5: Real-World Python
    "33-venv": "Virtual Environments & pip",
    "34-organization": "File Organization",
    "35-dates": "Working with Dates",
    "36-regex": "Regular Expressions",
    "37-data": "Data Processing",
    "38-cli": "Command-Line Scripts",
    "39-debugging": "Debugging Techniques",
    "40-final": "Final Project",
}

MODULES = {
    1: ("Module 1: Fundamentals", "01-print", "08-m1-review"),
    2: ("Module 2: Data Structures", "09-lists", "16-m2-review"),
    3: ("Module 3: Functions & Modularity", "17-functions", "24-m3-review"),
    4: ("Module 4: OOP & Beyond", "25-classes", "32-m4-review"),
    5: ("Module 5: Real-World Python", "33-venv", "40-final"),
}


# ── Progress Management ─────────────────────────────────────────────────

def _load_progress():
    """Load progress from JSON file."""
    if not os.path.exists(PROGRESS_FILE):
        return {"lessons": {}, "started": None, "current_module": 1}
    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"lessons": {}, "started": None, "current_module": 1}


def _save_progress(data):
    """Save progress to JSON file."""
    os.makedirs(PROGRESS_DIR, exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Commands ────────────────────────────────────────────────────────────

def cmd_progress(json_output=False):
    """Show learning progress."""
    data = _load_progress()
    lessons = data.get("lessons", {})

    if not lessons:
        if json_output:
            print(json.dumps({"status": "new", "completed": 0, "total": len(LESSONS), "current_module": 1}))
        else:
            print("No progress yet. Start with Lesson 1: Hello World & print()!")
        return

    completed = sum(1 for v in lessons.values() if v.get("completed"))
    total = len(LESSONS)
    pct = completed / total * 100 if total else 0

    if json_output:
        print(json.dumps({
            "status": "in_progress",
            "completed": completed,
            "total": total,
            "percent": round(pct, 1),
            "current_module": data.get("current_module", 1),
            "lessons": lessons,
        }))
        return

    print(f"📊 Python Learning Progress: {completed}/{total} lessons ({pct:.0f}%)")
    print()

    for mod_num, (mod_name, first, last) in sorted(MODULES.items()):
        lesson_keys = list(LESSONS.keys())
        first_idx = lesson_keys.index(first)
        last_idx = lesson_keys.index(last)
        mod_lessons = lesson_keys[first_idx:last_idx + 1]

        mod_completed = sum(1 for k in mod_lessons if lessons.get(k, {}).get("completed"))
        mod_total = len(mod_lessons)
        bar_len = 20
        filled = int(bar_len * mod_completed / mod_total) if mod_total else 0
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  {mod_name}")
        print(f"    [{bar}] {mod_completed}/{mod_total}")

        for key in mod_lessons:
            entry = lessons.get(key, {})
            status = "✅" if entry.get("completed") else "⬜"
            score = entry.get("score")
            score_str = f" (score: {score})" if score is not None else ""
            print(f"      {status} {key}: {LESSONS[key]}{score_str}")
        print()


def cmd_record(lesson_id, score=None, completed=False):
    """Record lesson progress."""
    if lesson_id not in LESSONS:
        print(f"Unknown lesson: {lesson_id}")
        print(f"Available lessons: {', '.join(LESSONS.keys())}")
        return

    data = _load_progress()
    if data.get("started") is None:
        data["started"] = datetime.now().isoformat()

    entry = data["lessons"].get(lesson_id, {})
    entry["last_attempt"] = datetime.now().isoformat()
    if score is not None:
        entry["score"] = score
    if completed:
        entry["completed"] = True
        entry["completed_at"] = datetime.now().isoformat()
    data["lessons"][lesson_id] = entry

    # Auto-advance module
    lesson_keys = list(LESSONS.keys())
    current_idx = lesson_keys.index(lesson_id)
    for mod_num, (mod_name, first, last) in sorted(MODULES.items()):
        first_idx = lesson_keys.index(first)
        last_idx = lesson_keys.index(last)
        if first_idx <= current_idx <= last_idx:
            data["current_module"] = mod_num
            break

    _save_progress(data)

    status = "completed ✅" if completed else "attempted"
    score_str = f" (score: {score})" if score is not None else ""
    print(f"Recorded lesson {lesson_id}: {status}{score_str}")


def cmd_run(code, lesson_id=None):
    """Run user's Python code safely and report results."""
    if not code.strip():
        print("No code provided.")
        return

    # Write code to a temp file and execute
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name

    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=os.path.dirname(temp_path),
        )

        output = {
            "exit_code": result.returncode,
            "stdout": result.stdout[:2000] if result.stdout else "",
            "stderr": result.stderr[:2000] if result.stderr else "",
        }

        if result.returncode == 0:
            print(f"✅ Code ran successfully!")
            if result.stdout.strip():
                print(f"Output:\n{result.stdout}")
        else:
            print(f"❌ Code failed with exit code {result.returncode}")
            if result.stderr.strip():
                # Clean up the temp file path from error messages
                err = result.stderr.replace(temp_path, "<user_code>")
                print(f"Error:\n{err}")

        if lesson_id:
            print(f"\n(Lesson: {lesson_id} — {LESSONS.get(lesson_id, 'Unknown')})")

    except subprocess.TimeoutExpired:
        print("⏱️ Code timed out after 10 seconds. Check for infinite loops.")
    except Exception as e:
        print(f"❌ Failed to run code: {e}")
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def cmd_lessons():
    """List all available lessons."""
    print("📚 Python Curriculum\n")
    for mod_num, (mod_name, first, last) in sorted(MODULES.items()):
        lesson_keys = list(LESSONS.keys())
        first_idx = lesson_keys.index(first)
        last_idx = lesson_keys.index(last)
        mod_lessons = lesson_keys[first_idx:last_idx + 1]
        print(f"{mod_name}")
        for key in mod_lessons:
            print(f"  {key}: {LESSONS[key]}")
        print()


def cmd_next():
    """Suggest the next lesson based on progress."""
    data = _load_progress()
    lessons = data.get("lessons", {})

    for key in LESSONS:
        if not lessons.get(key, {}).get("completed"):
            print(f"Next lesson: {key} — {LESSONS[key]}")
            return

    print("🎉 You've completed all lessons! Consider building a project to practice.")


# ── Main ────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Python tutor progress tracker")
    sub = parser.add_subparsers(dest="command")

    # progress
    p_progress = sub.add_parser("progress", help="Show learning progress")
    p_progress.add_argument("--json", action="store_true", help="Output as JSON")

    # record
    p_record = sub.add_parser("record", help="Record lesson progress")
    p_record.add_argument("--lesson", required=True, help="Lesson ID (e.g., 01-print)")
    p_record.add_argument("--score", type=int, help="Score (0-100)")
    p_record.add_argument("--completed", action="store_true", help="Mark lesson as completed")

    # run
    p_run = sub.add_parser("run", help="Run Python code")
    p_run.add_argument("--code", required=True, help="Python code to run")
    p_run.add_argument("--lesson", help="Lesson ID for context")

    # lessons
    sub.add_parser("lessons", help="List all available lessons")

    # next
    sub.add_parser("next", help="Suggest next lesson")

    args = parser.parse_args()

    if args.command == "progress":
        cmd_progress(json_output=args.json)
    elif args.command == "record":
        cmd_record(args.lesson, args.score, args.completed)
    elif args.command == "run":
        cmd_run(args.code, args.lesson)
    elif args.command == "lessons":
        cmd_lessons()
    elif args.command == "next":
        cmd_next()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
