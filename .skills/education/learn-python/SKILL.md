---
name: learn-python
description: Learn Python programming from fundamentals through guided interactive lessons with exercises and progress tracking
triggers:
  - learn python
  - python lesson
  - python tutorial
  - teach me python
  - python basics
  - python course
  - study python
  - python for beginners
  - python exercise
  - practice python
---

# Learn Python Skill

Teach Python programming through progressive interactive lessons conducted **in the chat**.

## ⚠️ IMPORTANT: Teaching happens in the chat, NOT in a script

The model explains concepts, gives examples, and evaluates exercises interactively. Scripts are only for tracking progress and running code — they complete in under 2 seconds.

## Workflow

1. **Assess level**: Check existing progress:
   ```
   python scripts/python_tutor.py progress --json
   ```
   If no progress exists, ask: "Have you programmed before? In what language(s)? What's your goal with Python?"
   
   **⚠️ STOP HERE.** Do NOT start teaching until the user answers. Wait for their response before choosing a starting point. End your message after the question.

2. **Determine starting point**: Based on the user's answer or progress:
   - Complete beginner → start at Module 1
   - Some experience → suggest a module and **ask for confirmation** before proceeding
   - Returning learner → check progress, resume where they left off
   
   **⚠️ Always wait for user confirmation before starting a lesson.** Never assume and jump into teaching.

3. **Teach a concept**: For each lesson:
   - Explain the concept clearly with **real-world analogies**
   - Show 2-3 concise code examples with expected output
   - Highlight common mistakes and pitfalls
   - Keep explanations under 200 words per concept — be CONCISE

4. **Give an exercise**: After each concept, provide a short exercise:
   - State the problem clearly
   - Give a hint if the user is stuck (but don't reveal the answer)
   - Wait for the user's code response

5. **Evaluate the exercise**:
   - Write the user's code to a temp file first (e.g., `lessons/exercise.py`), then run it:
     ```
     python scripts/python_tutor.py run --code-file lessons/exercise.py --lesson <lesson_id>
     ```
   - **NEVER use `--code` with inline code** — shell quoting on Windows corrupts multiline code with quotes. Always use `--code-file`.
   - If the code has errors, explain them clearly and suggest fixes
   - If correct, celebrate and move on
   - If the user is stuck after 2 attempts, show the solution with explanation

6. **Record progress**: After completing a lesson:
   ```
   python scripts/python_tutor.py record --lesson <lesson_id> --score <0-100> --completed
   ```

7. **Review periodically**: Every 3-4 lessons, suggest a quick review:
   - Mix concepts from recent lessons
   - Ask the user to write a small program combining what they've learned
   - Use `python scripts/python_tutor.py run` to test it

8. **Adapt pace**:
   - If the user breezes through exercises → skip ahead or add challenge problems
   - If the user struggles → slow down, add more examples, revisit fundamentals
   - Ask "Ready for the next topic?" before moving on

## Curriculum

### Module 1: Fundamentals (Lessons 1-8)
1. **Hello World & print()** — Output, strings, f-strings
2. **Variables & Types** — int, float, str, bool, type conversion
3. **Arithmetic & Expressions** — Operators, order of operations, modulo
4. **Input & Output** — input(), type casting, simple programs
5. **String Operations** — Indexing, slicing, methods, formatting
6. **Comparison & Logic** — ==, !=, <, >, and, or, not
7. **Conditional Statements** — if, elif, else, nested conditions
8. **Module 1 Review** — Combined exercise: simple calculator or quiz

### Module 2: Data Structures (Lessons 9-16)
9. **Lists** — Creation, indexing, slicing, methods, list comprehension intro
10. **List Operations** — append, insert, remove, sort, reverse, copy
11. **Tuples & Sets** — Immutable sequences, unique elements, set operations
12. **Dictionaries** — Key-value pairs, CRUD, iteration, nested dicts
13. **String Formatting** — f-strings, .format(), % formatting, template strings
14. **Working with Files** — open(), read, write, with statement, CSV intro
15. **Error Handling** — try/except, common exceptions, raising errors
16. **Module 2 Review** — Combined exercise: contact book or word counter

### Module 3: Functions & Modularity (Lessons 17-24)
17. **Defining Functions** — Parameters, return values, docstrings
18. **Default & Keyword Arguments** — *args, **kwargs, type hints
19. **Scope & Closures** — Local, global, nonlocal, LEGB rule
20. **Lambda & Higher-Order Functions** — map, filter, sorted with key
21. **Modules & Imports** — import, from, as, __name__, creating modules
22. **List Comprehensions** — Syntax, filtering, nesting, generator expressions
23. **Decorators** — Function wrappers, @syntax, practical examples
24. **Module 3 Review** — Combined exercise: utility library

### Module 4: OOP & Beyond (Lessons 25-32)
25. **Classes & Objects** — __init__, self, attributes, methods
26. **Inheritance & Polymorphism** — super(), overriding, isinstance
27. **Magic Methods** — __str__, __repr__, __len__, operator overloading
28. **Iterators & Generators** — yield, generator expressions, itertools intro
29. **Context Managers** — __enter__, __exit__, contextlib
30. **Working with JSON & APIs** — json module, requests library intro
31. **Testing Basics** — assert, unittest, doctest
32. **Module 4 Review** — Combined exercise: class-based project

### Module 5: Real-World Python (Lessons 33-40)
33. **Virtual Environments & pip** — venv, requirements.txt, installing packages
34. **File Organization** — __main__, packages, __init__.py, project structure
35. **Working with Dates** — datetime, timedelta, formatting, parsing
36. **Regular Expressions** — re module, patterns, groups, common tasks
37. **Data Processing** — csv, collections.Counter, statistics intro
38. **Command-Line Scripts** — argparse, sys.argv, entry points
39. **Debugging Techniques** — print debugging, pdb, logging basics
40. **Final Project** — Build a complete program combining all modules

## Exercise Format

When giving an exercise, use this format:

```
📝 **Exercise: <title>** (Lesson <number>)

**Task**: <clear description of what to write>

**Example**:
Input: <example input>
Expected output: <example output>

**Hint**: <optional hint>

Write your code and I'll check it!
```

When evaluating, use:

```
✅ **Correct!** <brief explanation of why it works>
```
or
```
❌ **Not quite right.** <explain the error clearly>
   Try again, or type "hint" for a clue, or "solution" to see the answer.
```

## Scripts

- `scripts/python_tutor.py` — Track progress (`progress`), run code (`run`), record results (`record`)

> All script paths are relative to this SKILL.md's directory.
> At runtime, they are automatically resolved to workdir-relative paths.

## Tips

- Be patient and encouraging — everyone learns at a different pace
- Use analogies from everyday life to explain programming concepts
- When the user makes an error, explain WHY it's wrong, not just that it IS wrong
- Celebrate small wins — "Great job!" goes a long way
- Don't overwhelm — one concept at a time, short exercises
- If the user asks "why?" about something, always answer — curiosity is good
- Suggest the user save their exercise code in files (e.g., `lessons/lesson_01.py`) for later review
- For complex topics, break into multiple mini-lessons rather than one long explanation
- If the user wants to skip ahead, let them — but warn if prerequisites are missing
- **Always use `--code-file`** to run user code — write the code to a file first, then pass `--code-file <path>`. Never use `--code` with inline strings (shell quoting breaks multiline code with quotes).
