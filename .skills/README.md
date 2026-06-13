# Custom Skills

Place skill definitions here to extend the model's capabilities.

## Skill Formats

### Directory-based (SKILL.md) — Recommended

Each skill is a directory containing a `SKILL.md` file:

```
.skills/
├── productivity/              # Category (optional grouping)
│   ├── DESCRIPTION.md         # Category description (optional)
│   ├── weather/
│   │   └── SKILL.md           # Skill definition
│   └── travel-plans/
│       ├── SKILL.md
│       └── references/        # Context documents (optional)
│           └── routes.md
├── media/
│   ├── DESCRIPTION.md
│   └── newsfeed/
│       ├── SKILL.md
│       └── scripts/           # Executable scripts (optional)
│           └── fetch_news.py
└── my-skill/
    └── SKILL.md               # Top-level skill (no category)
```

#### SKILL.md Format

```markdown
---
name: my-skill
description: One-line description of what this skill does
triggers:
  - trigger phrase
  - another trigger
---

# My Skill

Detailed instructions for the model when this skill is invoked.

## Steps
1. First, read the target file
2. Run the script: `python scripts/my_script.py <args>`
3. Present the result

## Scripts
- `scripts/my_script.py` — Description of what this script does

## References
- references/my_ref.md
```

### Path Conventions (Important!)

**All paths in SKILL.md must be relative to the skill directory** (the folder containing SKILL.md).

✅ **Correct** — skill-dir-relative paths:
```
python scripts/fetch_weather.py "Batumi" --forecast
```

❌ **Wrong** — workdir-relative paths (breaks portability):
```
python .skills/productivity/weather/scripts/fetch_weather.py "Batumi" --forecast
```

At runtime, the system automatically resolves skill-dir-relative paths to workdir-relative paths.
This means:
- In SKILL.md, write `scripts/fetch_news.py` (relative to the skill folder)
- At execution time, the system rewrites it to `.skills/media/newsfeed/scripts/fetch_news.py`
- Script validation runs at load time and execution time — missing files produce warnings

### Script Validation

When skills are loaded, the system validates that all declared script files exist.
Missing scripts produce warnings like:
```
[Skill load warning: weather: script not found — fetch_weather: scripts/fetch_weather.py (file not found)]
```

When a skill is invoked, missing scripts are flagged in the output:
```
⚠ WARNING: Missing script files: fetch_weather (scripts/fetch_weather.py)
```/context.md: Background information the model should know

## Examples
User: "Review my code"
→ Invokes skill with {"path": "src/main.py", "focus": "security"}
```

### JSON Skills (prompt-only, flat file)

Create a `.json` file in the skills directory:

```json
{
    "name": "my-skill",
    "description": "What this skill does",
    "system_prompt": "Instructions for the model when this skill is invoked...",
    "parameters": {
        "input": {"type": "string", "required": true, "description": "What to process"}
    }
}
```

### Python Skills (executable, flat file)

Create a `.py` file with a Skill subclass:

```python
from ollama_agent.skills.base import Skill

class MySkill(Skill):
    name = "my-skill"
    description = "What this skill does"
    system_prompt = "Instructions for the model..."
    parameters = {
        "input": {"type": "string", "required": True, "description": "What to process"}
    }

    def execute(self, params, workdir=None, session=None):
        # Your custom logic here
        return f"Result: {params}"
```

## Built-in Skills

- **code-review**: Review code for bugs, issues, and improvements
- **test-gen**: Generate test cases for source code
- **doc-gen**: Generate documentation for source code
- **plan**: Create a structured development plan

## Usage

Run with `--skills` to enable:

```bash
python ollama_agent.py --agent --skills
```

Custom skills directory can be changed with `--skills-dir`:

```bash
python ollama_agent.py --agent --skills --skills-dir ./my-skills
```

Use `/skills` in the chat to list all available skills.
