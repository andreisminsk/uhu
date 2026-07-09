#!/usr/bin/env python3
"""Generate touch-typing lesson text for a given level and focus area.

Usage:
    python generate_lesson.py --level beginner [--focus asdf] [--lesson 1] [--output json|text]

Output (JSON mode):
    {
        "lesson_id": "beginner-01",
        "title": "Home Row Left: F D S A",
        "level": "beginner",
        "lesson_number": 1,
        "focus_keys": ["f", "d", "s", "a"],
        "text": "fff ddd sss aaa fff ddd ...",
        "word_count": 50
    }
"""

import argparse
import json
import sys

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# ── Lesson definitions ──────────────────────────────────────────────────

LESSONS = {
    # Beginner lessons
    1: {
        "title": "Home Row Left: F D S A",
        "level": "beginner",
        "focus_keys": ["f", "d", "s", "a"],
        "words": ["fad", "ads", "sad", "dad", "ass", "add", "saf", "fas", "dda", "afd",
                   "fad", "sad", "add", "dad", "ass", "saf", "fas", "ads", "afd", "dda"],
        "drills": ["fff ddd sss aaa", "fff aaa ddd sss", "fad sad dad add",
                   "ads saf fas dda", "fff ddd aaa sss fff", "sad fad add dad"],
    },
    2: {
        "title": "Home Row Right: J K L ;",
        "level": "beginner",
        "focus_keys": ["j", "k", "l", ";"],
        "words": ["jkl", "lkj", "jlk", "klj", "jkk", "lll", "kkk", "jjj"],
        "drills": ["jjj kkk lll ;;;", "jjj kkk lll ;;;", "jkl lkj jlk klj",
                   "jjj kkk ;;; lll", "jkl jlk klj lkj", "jjj lll kkk ;;;"],
    },
    3: {
        "title": "Home Row Combined",
        "level": "beginner",
        "focus_keys": ["a", "s", "d", "f", "j", "k", "l", ";"],
        "words": ["flash", "lads", "flags", "glad", "half", "jags", "salad", "flask",
                  "shall", "fall", "hall", "dash", "ask", "has", "had", "lad",
                  "sad", "dad", "add", "fad", "jkl", "ask", "lash", "gash"],
        "drills": ["fff jjj ddd kkk sss lll aaa ;;;", "flash lads flags glad",
                   "ask dad had lad sad fad", "shall fall hall dash flask",
                   "asdf jkl; asdf jkl;", "flags glad half jags salad"],
    },
    4: {
        "title": "Home Row + G and H",
        "level": "beginner",
        "focus_keys": ["a", "s", "d", "f", "g", "h", "j", "k", "l", ";"],
        "words": ["gash", "hash", "lash", "dash", "glad", "half", "flag", "slag",
                  "shag", "gash", "hag", "lag", "gag", "had", "has", "ash"],
        "drills": ["ggg hhh fff jjj ggg hhh", "gash hash lash dash",
                   "glad half flag slag", "ggg hhh ddd kkk ggg hhh",
                   "shag gash hag lag gag", "had has ash flag glad"],
    },
    5: {
        "title": "Home Row + R and U",
        "level": "beginner",
        "focus_keys": ["a", "s", "d", "f", "g", "h", "j", "k", "l", "r", "u"],
        "words": ["rush", "hush", "gush", "flush", "harsh", "harsh", "surf", "fur",
                  "rug", "jug", "hug", "bug", "dug", "mug", "pug", "lug"],
        "drills": ["rrr uuu rrr uuu fff jjj", "rush hush gush flush",
                   "harsh surf fur rug jug", "rrr uuu ddd kkk fff jjj",
                   "hug bug dug mug pug lug", "surf rush flush harsh gush"],
    },
    6: {
        "title": "Home Row + T and Y",
        "level": "beginner",
        "focus_keys": ["a", "s", "d", "f", "g", "h", "j", "k", "l", "t", "y"],
        "words": ["that", "this", "they", "stay", "day", "say", "way", "may",
                  "lay", "pay", "gay", "hay", "jay", "ray", "say", "tag"],
        "drills": ["ttt yyy ttt yyy fff jjj", "that this they stay",
                   "day say way may lay", "ttt yyy ddd kkk fff jjj",
                   "tag rag lag sag fad had", "that stay day this they"],
    },
    7: {
        "title": "Home Row Review",
        "level": "beginner",
        "focus_keys": ["a", "s", "d", "f", "g", "h", "j", "k", "l", "r", "t", "u", "y"],
        "words": ["that", "flash", "gust", "rush", "harsh", "truth", "slay", "gray",
                  "dash", "gash", "hush", "flag", "glad", "half", "surf", "rug"],
        "drills": ["flash rush that harsh gust", "glad half flag gash dash",
                   "surf rug hug jug slug shrug", "truth slay gray day say",
                   "that this they stay harsh rush", "flag glad half flash lash"],
    },
    8: {
        "title": "Home Row Common Words",
        "level": "beginner",
        "focus_keys": ["a", "s", "d", "f", "g", "h", "j", "k", "l", "r", "t", "u", "y"],
        "words": ["the", "and", "has", "had", "that", "this", "dash", "flash",
                  "glad", "half", "flag", "just", "last", "salt", "shall", "still",
                  "glass", "class", "staff", "harsh", "trash", "slash", "crash", "stash"],
        "drills": ["the and has had that this", "dash flash glad half flag",
                   "just last salt shall still", "glass class staff harsh",
                   "trash slash crash stash", "the last flag had just half"],
    },
    # Intermediate lessons
    9: {
        "title": "Top Row Left: Q W E R",
        "level": "intermediate",
        "focus_keys": ["q", "w", "e", "r"],
        "words": ["we", "were", "where", "there", "here", "were", "require", "quest",
                  "queen", "question", "we", "were", "where", "were", "here"],
        "drills": ["qqq www eee rrr", "we were where there here",
                   "quest queen question require", "www eee rrr qqq www",
                   "we were here there where", "quest question queen require"],
    },
    10: {
        "title": "Top Row Right: I O P",
        "level": "intermediate",
        "focus_keys": ["i", "o", "p"],
        "words": ["oil", "pool", "loop", "polo", "opium", "lip", "hip", "dip",
                  "rip", "tip", "pip", "pop", "hop", "mop", "top", "drop"],
        "drills": ["iii ooo ppp iii ooo", "oil pool loop polo",
                   "lip hip dip rip tip", "pop hop mop top drop",
                   "iii ooo ppp kkk lll ;;;", "oil pool drop loop polo"],
    },
    11: {
        "title": "Top Row Combined",
        "level": "intermediate",
        "focus_keys": ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
        "words": ["typewriter", "property", "question", "power", "quiet", "report",
                  "people", "point", "quite", "quote", "poetry", "puppy",
                  "type", "write", "right", "weight", "their", "would", "could"],
        "drills": ["qwerty uiop asdf jkl", "typewriter property question",
                   "power quiet report people", "quite quote poetry point",
                   "type write right weight", "their would could people quite"],
    },
    12: {
        "title": "Bottom Row Left: Z X C V",
        "level": "intermediate",
        "focus_keys": ["z", "x", "c", "v"],
        "words": ["zinc", "cave", "vice", "size", "zone", "voice", "civil", "exile",
                  "civic", "viz", "cox", "box", "fox", "cox", "zoo", "zen"],
        "drills": ["zzz xxx ccc vvv", "zinc cave vice size zone",
                   "voice civil exile civic", "box fox zoo zen viz",
                   "zzz xxx ccc vvv aaa sss", "civic size voice cave zinc"],
    },
    13: {
        "title": "Bottom Row Right: M , . /",
        "level": "intermediate",
        "focus_keys": ["m", ",", ".", "/"],
        "words": ["milk", "mill", "film", "slim", "him", "dim", "rim", "vim",
                  "mop", "map", "mat", "ham", "jam", "ram", "dam", "cam"],
        "drills": ["mmm ,,, ... ///", "milk mill film slim him",
                   "mop map mat ham jam", "mmm ,,, ... /// kkk lll",
                   "dim rim vim dam cam ram", "milk film slim him dim"],
    },
    14: {
        "title": "Bottom Row Combined",
        "level": "intermediate",
        "focus_keys": ["z", "x", "c", "v", "b", "n", "m"],
        "words": ["combine", "motion", "vision", "zombie", "volume", "benign",
                  "minimize", "vaccine", "vibrant", "convinced", "benzine",
                  "combine", "motion", "vision", "volume", "vibrant"],
        "drills": ["zxcvbnm zxcvbnm", "combine motion vision zombie",
                   "volume benign minimize vaccine", "vibrant convinced benzine",
                   "zxcvbnm asdfjkl", "combine vision volume vibrant motion"],
    },
    15: {
        "title": "Numbers Row",
        "level": "intermediate",
        "focus_keys": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
        "words": ["123", "456", "789", "321", "654", "987", "135", "246", "864", "975",
                  "100", "200", "300", "42", "17", "85", "39", "56", "74", "91"],
        "drills": ["123 456 789 0", "111 222 333 444 555",
                   "135 246 357 468 579", "100 200 300 42 17",
                   "12345 67890 54321 09876", "39 56 74 91 85 17 42"],
    },
    16: {
        "title": "Common Bigrams and Trigrams",
        "level": "intermediate",
        "focus_keys": ["all"],
        "words": ["the", "and", "ing", "tion", "ent", "ion", "thi", "for",
                  "ati", "our", "are", "has", "not", "but", "from", "with",
                  "they", "have", "this", "that", "with", "from", "have", "been"],
        "drills": ["th he in ng ti on en at io", "the and ing tion ent ion",
                   "thi for ati our are has", "not but from with they",
                   "have this that been from", "the and ing tion with have"],
    },
    # Advanced lessons
    17: {
        "title": "Shift Keys: Capital Letters",
        "level": "advanced",
        "focus_keys": ["shift"],
        "words": ["The", "And", "This", "That", "With", "From", "Have", "Been",
                  "They", "Their", "Would", "Could", "Should", "About", "Which",
                  "First", "After", "Going", "Think", "Where", "Right", "Being"],
        "drills": ["The And This That With From", "Have Been They Their Would",
                   "Could Should About Which First", "After Going Think Where Right",
                   "The Quick Brown Fox Jumps Over", "Every Good Boy Does Fine Always"],
    },
    18: {
        "title": "Punctuation Basics",
        "level": "advanced",
        "focus_keys": [".", ",", "!", "?", ";", ":"],
        "words": ["Hello, world!", "How are you?", "I'm fine, thanks.",
                  "Yes; however, no.", "Wait! Stop!", "Really? Why?",
                  "First, second; third.", "Done. Finished! Complete?"],
        "drills": ["Hello, world! How are you?", "I'm fine, thanks. Really?",
                   "Yes; however, no. Wait! Stop!", "First, second; third. Done.",
                   "The quick, brown fox jumps. Over the lazy dog!", "Why? How! When, where."],
    },
    19: {
        "title": "Brackets and Symbols",
        "level": "advanced",
        "focus_keys": ["[", "]", "(", ")", "{", "}", "<", ">", "@", "#"],
        "words": ["[item]", "(note)", "{block}", "<tag>", "@user", "#tag",
                  "array[0]", "func(x)", "dict{k:v}", "email@host.com",
                  "list[1:3]", "set{a,b}", "range(n)", "path/to/file"],
        "drills": ["[ ] ( ) { } < >", "array[0] func(x) dict{k:v}",
                   "@user #tag email@host.com", "list[1:3] set{a,b} range(n)",
                   "if (x > 0) { return y; }", "for i in range(n): print(i)"],
    },
    20: {
        "title": "Numbers Fluency",
        "level": "advanced",
        "focus_keys": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
        "words": ["3.14159", "2.71828", "1.41421", "1.61803", "0.57721",
                  "42", "1337", "256", "1024", "65536",
                  "192.168.1.1", "10.0.0.1", "255.255.255.0", "127.0.0.1"],
        "drills": ["3.14 2.72 1.41 1.62 0.58", "42 256 1024 65536 1337",
                   "192.168.1.1 10.0.0.1", "255.255.255.0 127.0.0.1",
                   "1+2=3 4*5=20 10/2=5 8-3=5", "100*100=10000 2^10=1024"],
    },
    21: {
        "title": "Common English Words (Top 100)",
        "level": "advanced",
        "focus_keys": ["all"],
        "words": ["the", "be", "to", "of", "and", "a", "in", "that", "have", "I",
                  "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
                  "this", "but", "his", "by", "from", "they", "we", "say", "her", "she",
                  "or", "an", "will", "my", "one", "all", "would", "there", "their", "what"],
        "drills": ["the be to of and a in that have", "it for not on with he as you do",
                   "this but his by from they we say her", "or an will my one all would there",
                   "the of and to a in is it you that", "he was for on are as with his they"],
    },
    22: {
        "title": "Common English Words (Top 200)",
        "level": "advanced",
        "focus_keys": ["all"],
        "words": ["about", "after", "again", "below", "could", "every", "first",
                  "found", "great", "house", "large", "learn", "never", "other",
                  "place", "plant", "point", "right", "small", "sound", "spell",
                  "still", "study", "their", "there", "these", "thing", "think",
                  "three", "water", "where", "which", "world", "would", "write"],
        "drills": ["about after again below could every first", "found great house large learn never other",
                   "place plant point right small sound spell", "still study their there these thing think",
                   "three water where which world would write", "about could first great house learn never"],
    },
    23: {
        "title": "Code Snippets (for Programmers)",
        "level": "advanced",
        "focus_keys": ["all"],
        "words": ["def func(x):", "if x > 0:", "return True", "for i in range(n):",
                  "print(f'{x}')", "class MyClass:", "self.value = x", "import os, sys",
                  "try: ... except:", "with open(f) as fp:", "len(items)", "x = [1, 2, 3]",
                  "dict.get(key, default)", "if __name__ == '__main__':"],
        "drills": ["def func(x): return x + 1", "if x > 0: print('yes')",
                   "for i in range(n): yield i", "class MyClass: pass",
                   "with open(f) as fp: data = fp.read()", "try: x = int(s) except: x = 0"],
    },
    24: {
        "title": "Speed Drills",
        "level": "advanced",
        "focus_keys": ["all"],
        "words": ["the quick brown fox jumps over the lazy dog",
                  "pack my box with five dozen liquor jugs",
                  "how vexingly quick daft zebras jump",
                  "the five boxing wizards jump quickly",
                  "sphinx of black quartz judge my vow",
                  "two driven jocks help fax my big quiz"],
        "drills": ["the quick brown fox jumps over the lazy dog",
                   "pack my box with five dozen liquor jugs",
                   "how vexingly quick daft zebras jump",
                   "the five boxing wizards jump quickly",
                   "sphinx of black quartz judge my vow",
                   "two driven jocks help fax my big quiz"],
    },
}


def generate_lesson_text(lesson_num):
    """Generate the full text for a lesson from drills and words."""
    if lesson_num not in LESSONS:
        return None

    lesson = LESSONS[lesson_num]
    parts = []

    # Start with drills
    for drill in lesson["drills"]:
        parts.append(drill)

    # Add word practice
    words = lesson["words"]
    # Create word sequences
    for i in range(0, len(words), 4):
        chunk = words[i:i + 4]
        parts.append(" ".join(chunk))

    return " ".join(parts)


def generate_lesson(level="beginner", lesson_num=None, focus_keys=None):
    """Generate a lesson dict."""
    # Determine lesson number
    if lesson_num is not None:
        num = lesson_num
    elif level == "beginner":
        num = 1
    elif level == "intermediate":
        num = 9
    elif level == "advanced":
        num = 17
    else:
        num = 1

    if num not in LESSONS:
        # Find closest lesson
        available = sorted(LESSONS.keys())
        if num < min(available):
            num = min(available)
        elif num > max(available):
            num = max(available)
        else:
            # Find nearest lower
            for a in available:
                if a <= num:
                    num = a

    lesson = LESSONS[num]
    text = generate_lesson_text(num)

    # If focus_keys specified, filter drills to emphasize those keys
    if focus_keys and focus_keys != "all":
        keys = [k.strip().lower() for k in focus_keys.split(",")]
        # Add extra practice lines emphasizing the focus keys
        for key in keys:
            if len(key) == 1:
                parts = [f"{key}{key}{key} {key}{key}{key}"] * 2
                text = " ".join(parts) + " " + text

    return {
        "lesson_id": f"{lesson['level']}-{num:02d}",
        "title": lesson["title"],
        "level": lesson["level"],
        "lesson_number": num,
        "focus_keys": lesson["focus_keys"],
        "text": text,
        "word_count": len(text.split()),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate touch-typing lesson text")
    parser.add_argument("--level", choices=["beginner", "intermediate", "advanced"],
                        default="beginner", help="Difficulty level")
    parser.add_argument("--lesson", type=int, default=None, help="Lesson number (1-24)")
    parser.add_argument("--focus", default=None,
                        help="Comma-separated keys to focus on (e.g., 'a,s,d,f')")
    parser.add_argument("--output", choices=["json", "text"], default="json",
                        help="Output format")
    args = parser.parse_args()

    result = generate_lesson(level=args.level, lesson_num=args.lesson,
                             focus_keys=args.focus)

    if result is None:
        print(f"Error: Lesson not found", file=sys.stderr)
        sys.exit(1)

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Lesson {result['lesson_id']}: {result['title']}")
        print(f"Level: {result['level']}")
        print(f"Focus keys: {', '.join(result['focus_keys'])}")
        print()
        print(result["text"])


if __name__ == "__main__":
    main()
