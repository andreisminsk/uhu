---
name: touch-typing
description: Learn and practice touch typing with adaptive lessons and real-time feedback
triggers:
  - learn to type
  - typing practice
  - touch typing
  - typing lesson
  - improve my typing
  - typing speed
  - WPM
  - keyboard practice
  - blind typing
---

# Touch Typing Skill

Teach touch typing through progressive lessons conducted **in the chat**.

## ⚠️ IMPORTANT: Practice happens in the chat, NOT in a script

Typing practice is interactive — the user types text in the chat, and you evaluate their accuracy. Do NOT run any interactive script. The scripts are only for generating lessons, recording results, and showing progress. They complete in under 2 seconds.

## Workflow

1. **Assess level**: If no progress file exists, ask about their experience (beginner / intermediate / advanced). Check existing progress:
   ```
   python scripts/typing_practice.py progress --json
   ```

2. **Generate lesson**: Create lesson text appropriate for the user's level:
   ```
   python scripts/generate_lesson.py --level <beginner|intermediate|advanced> [--lesson <number>] [--focus <keys>] --output json
   ```
   This outputs JSON with `lesson_id`, `title`, `text`, `focus_keys`.

3. **Present the text**: Show the lesson text to the user. Keep it short — 30-60 characters for beginners, up to 100 for advanced. Format it clearly:
   ```
   Type this text:
   fff ddd sss aaa
   ```

4. **Evaluate**: When the user types their response, compare it character by character:
   - Count correct characters, errors, and extra/missing characters
   - Calculate accuracy: correct / total × 100%
   - Estimate WPM: (correct / 5) / (time in minutes). Ask the user how long it took, or estimate ~30 seconds for short texts.
   - Show which characters were wrong: highlight errors with ❌ and correct with ✅

5. **Record results**: Save the session to progress tracking:
   ```
   python scripts/typing_practice.py record --lesson <lesson_id> --wpm <number> --accuracy <number> --duration <seconds>
   ```
   For error details, use `--errors-file` (write errors to a temp JSON file first):
   ```
   python scripts/typing_practice.py record --lesson beginner-01 --wpm 15.2 --accuracy 87.3 --duration 30 --errors-file errors.json
   ```

6. **Show progress**: Periodically show improvement trends:
   ```
   python scripts/typing_practice.py progress
   ```

7. **Adapt**: Based on results:
   - Accuracy < 85%: repeat same lesson, focus on weak keys
   - Accuracy 85-95%: try next lesson
   - Accuracy > 95%: advance to next level

## Levels

- **Beginner** (lessons 1-8): Home row, then G, H, R, U, T, Y, common words
- **Intermediate** (lessons 9-16): Top row, bottom row, numbers, bigrams
- **Advanced** (lessons 17-24): Shift, punctuation, symbols, speed drills

## Scripts

- `scripts/generate_lesson.py` — Generate lesson text (JSON or text output)
- `scripts/typing_practice.py` — Record results (`record` subcommand) and show progress (`progress` subcommand)

> All script paths are relative to this SKILL.md's directory.
> At runtime, they are automatically resolved to workdir-relative paths.

## Tips

- Keep practice texts short (30-100 chars) — users type in chat, not a terminal
- Be encouraging! Celebrate improvements
- Suggest finger positions for new keys (see references/keyboard_layout.md)
- If the user makes many errors on specific keys, focus the next lesson on those keys
- Ask the user to time themselves or estimate how long the typing took
