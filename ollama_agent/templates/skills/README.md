# User-global skills (~/.uhu/skills)

Skills placed here load in every uhu session, for any workdir.

Formats:
- `my-skill/SKILL.md` — directory skill (YAML frontmatter or markdown sections)
- `category/my-skill/SKILL.md` — grouped under a category
- `my-skill.json` — prompt-only skill
- `my-skill.py` — executable skill (Skill subclass)

Precedence on name collision: workdir `.skills/` > `~/.uhu/skills/` > `extra_skills_dirs`.

See dev-docs/UHU-HOME-ARCH.md and `.skills/README.md` in a project for full format docs.
