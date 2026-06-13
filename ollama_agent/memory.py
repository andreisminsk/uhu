"""Permanent memory system — PROJ-MEMORY.md and AGENT-MEMORY.md."""

import os
import re

PROJ_MEMORY_FILENAME = "PROJ-MEMORY.md"
AGENT_MEMORY_FILENAME = "AGENT-MEMORY.md"

MEMORY_SECTIONS = ["Instructions", "Preferences", "Conventions", "Facts", "Notes"]

DEFAULT_MEMORY_CONFIG = {
    "max_lines": 50,
    "warn_threshold": 40,
}


def get_memory_config(workdir=None):
    """Get memory config merged from .ollama_agent.json defaults."""
    from .tools._config import load_config
    cfg = load_config(workdir)
    mem_cfg = dict(DEFAULT_MEMORY_CONFIG)
    if "memory" in cfg:
        mem_cfg.update(cfg["memory"])
    return mem_cfg


def _memory_path(scope, workdir):
    """Return the file path for the given memory scope."""
    if scope == "agent":
        # Agent memory lives where .ollama_agent.json is found,
        # or in home directory if no config exists (agent memory is cross-project)
        from .tools._config import _find_config_dir, CONFIG_FILENAME
        config_dir = _find_config_dir(workdir)
        if config_dir and os.path.isfile(os.path.join(config_dir, CONFIG_FILENAME)):
            return os.path.join(config_dir, AGENT_MEMORY_FILENAME)
        return os.path.join(os.path.expanduser("~"), AGENT_MEMORY_FILENAME)
    # Project memory lives in workdir
    return os.path.join(workdir, PROJ_MEMORY_FILENAME)


def load_memory(scope, workdir):
    """Load and parse a memory file. Returns list of (section, entries) tuples."""
    path = _memory_path(scope, workdir)
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return parse_memory(content)


def parse_memory(content):
    """Parse memory file content into list of (section, entries) tuples."""
    sections = []
    current_section = None
    current_entries = []

    for line in content.splitlines():
        # Skip title line (# Project Memory / # Agent Memory)
        if line.startswith("# ") and not line.startswith("## "):
            continue
        # Section header
        m = re.match(r'^##\s+(.+)', line)
        if m:
            if current_section and current_entries:
                sections.append((current_section, current_entries))
            # Strip description after em-dash: "Instructions — desc" -> "Instructions"
            section_name = m.group(1).strip()
            if ' — ' in section_name:
                section_name = section_name.split(' — ')[0].strip()
            current_section = section_name
            current_entries = []
            continue
        # Bullet entry
        if line.startswith("- ") and current_section:
            current_entries.append(line[2:].strip())
            continue
        # Non-empty, non-section, non-bullet line — treat as entry
        if line.strip() and current_section:
            current_entries.append(line.strip())

    if current_section and current_entries:
        sections.append((current_section, current_entries))

    return sections


SECTION_DESCRIPTIONS = {
    "Instructions": "Behavioral directives — how the agent should act (highest priority)",
    "Preferences": "Style and format choices — how the agent should respond",
    "Conventions": "Project standards — naming, patterns, workflows",
    "Facts": "Important facts — things the agent must remember as true",
    "Notes": "Miscellaneous notes — anything that doesn't fit elsewhere",
}


def format_memory(sections):
    """Format sections into memory file content optimized for LLM comprehension."""
    lines = []
    for section, entries in sections:
        desc = SECTION_DESCRIPTIONS.get(section, "")
        if desc:
            lines.append(f"## {section} — {desc}")
        else:
            lines.append(f"## {section}")
        for entry in entries:
            lines.append(f"- {entry}")
        lines.append("")  # blank line between sections
    return "\n".join(lines)


def save_memory(scope, workdir, sections):
    """Save sections to the memory file for the given scope."""
    path = _memory_path(scope, workdir)
    title = "Project Memory" if scope == "project" else "Agent Memory"
    scope_desc = "project-specific" if scope == "project" else "agent-wide (applies to all projects)"
    content = f"# {title}\n# Scope: {scope_desc}\n# Sections: Instructions > Preferences > Conventions > Facts > Notes\n\n{format_memory(sections)}"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def add_memory_entry(scope, workdir, text, section=None):
    """Add an entry to a memory file. Returns (path, section_used, was_new_file)."""
    sections = load_memory(scope, workdir)
    # Determine section — default to "Notes"
    target_section = section or _classify_entry(text)
    # Find or create the section
    found = False
    for i, (sec, entries) in enumerate(sections):
        if sec.lower() == target_section.lower():
            entries.append(text)
            sections[i] = (sec, entries)
            found = True
            break
    if not found:
        sections.append((target_section, [text]))

    path = _memory_path(scope, workdir)
    was_new = not os.path.isfile(path)
    save_memory(scope, workdir, sections)
    return path, target_section, was_new


def _classify_entry(text):
    """Classify a memory entry into the most appropriate section."""
    text_lower = text.lower()

    # Instructions: behavioral directives, commands, how to act
    instruction_words = ["don't", "do not", "never", "always", "must", "should",
                         "avoid", "make sure", "ensure", "remember to",
                         "when you", "if ", "respond", "reply", "format"]
    for w in instruction_words:
        if w in text_lower:
            return "Instructions"

    # Conventions: project standards, naming, patterns
    convention_words = ["naming", "convention", "pattern", "branch", "commit",
                       "standard", "workflow"]
    for w in convention_words:
        if w in text_lower:
            return "Conventions"

    # Preferences: style choices
    preference_words = ["prefer", "like", "style", "use ", "short", "verbose",
                        "concise", "detailed"]
    for w in preference_words:
        if w in text_lower:
            return "Preferences"

    # Facts: things that are true
    fact_words = ["is ", "are ", "has ", "uses ", "runs on", "version",
                  "located", "database", "api", "schema", "port", "url"]
    for w in fact_words:
        if w in text_lower:
            return "Facts"

    return "Notes"


def check_memory_size(scope, workdir):
    """Check memory file size against config thresholds.
    Returns (lines, warn_level) where warn_level is 0=ok, 1=warning, 2=critical."""
    path = _memory_path(scope, workdir)
    if not os.path.isfile(path):
        return 0, 0
    with open(path, "r", encoding="utf-8") as f:
        line_count = sum(1 for _ in f)
    cfg = get_memory_config(workdir)
    if line_count >= cfg["max_lines"]:
        return line_count, 2
    if line_count >= cfg["warn_threshold"]:
        return line_count, 1
    return line_count, 0


def check_conflicts(workdir):
    """Check for contradictory entries between project and agent memory.
    Returns list of conflict descriptions."""
    proj_sections = load_memory("project", workdir)
    agent_sections = load_memory("agent", workdir)

    if not proj_sections or not agent_sections:
        return []

    conflicts = []
    # Build a dict of topics -> values from each memory
    proj_entries = {}
    for section, entries in proj_sections:
        for entry in entries:
            key = _entry_key(entry)
            if key:
                proj_entries[key] = entry

    agent_entries = {}
    for section, entries in agent_sections:
        for entry in entries:
            key = _entry_key(entry)
            if key:
                agent_entries[key] = entry

    for key in set(proj_entries) & set(agent_entries):
        if proj_entries[key] != agent_entries[key]:
            conflicts.append(
                f"Project: {proj_entries[key]} vs Agent: {agent_entries[key]}"
            )
    return conflicts


def _entry_key(entry):
    """Extract a rough topic key from an entry for conflict detection."""
    # Take the first 2 words as a key — short enough to catch related entries
    words = entry.lower().split()
    if len(words) >= 2:
        return " ".join(words[:2])
    return entry.lower()


def build_memory_prompt(workdir):
    """Build the memory injection string for the system prompt.
    Returns (prompt_text, warnings)."""
    warnings = []
    parts = []

    for scope, label in [("project", "Project Memory"), ("agent", "Agent Memory")]:
        sections = load_memory(scope, workdir)
        if not sections:
            continue
        lines_count, warn_level = check_memory_size(scope, workdir)
        if warn_level == 1:
            warnings.append(f"{label} is getting large ({lines_count} lines). Consider /compact memory.")
        elif warn_level == 2:
            warnings.append(f"{label} is at capacity ({lines_count} lines). Use /compact memory to free space.")
        content = format_memory(sections)
        parts.append(f"[{label} — {scope}-scope, overrides agent memory on conflicts]\n{content}")

    # Check conflicts
    conflicts = check_conflicts(workdir)
    if conflicts:
        conflict_str = "; ".join(conflicts)
        warnings.append(f"Memory conflict detected (project takes precedence): {conflict_str}")

    if not parts:
        return "", warnings

    header = "IMPORTANT: Follow these memory entries as instructions. Project memory overrides agent memory on conflicts."
    prompt = header + "\n\n" + "\n\n".join(parts)
    return prompt, warnings


def compact_memory(scope, workdir):
    """Compact a memory file using llm_query to summarize and deduplicate.
    Returns the new line count."""
    from .tools._config import get_config
    sections = load_memory(scope, workdir)
    if not sections:
        return 0

    content = format_memory(sections)
    label = "project" if scope == "project" else "agent-wide"

    prompt = (
        f"You are condensing a {label} memory file for an AI coding assistant. "
        f"Merge duplicate entries, remove redundancy, and keep each entry concise (one line). "
        f"Preserve all unique information. Output in the same markdown format with ## sections and - bullets.\n\n"
        f"Current memory:\n{content}"
    )

    cfg = get_config(workdir)
    model = cfg.get("llm_query", {}).get("model", "qwen3.5:397b-cloud")
    api_url = cfg.get("llm_query", {}).get("api_url", "http://localhost:11434")

    try:
        from ollama import Client
        client = Client(host=api_url)
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2},
        )
        result = response["message"]["content"].strip()
    except Exception as e:
        raise RuntimeError(f"Failed to compact memory: {e}") from e

    # Parse the result and save
    new_sections = parse_memory(result)
    save_memory(scope, workdir, new_sections)
    path = _memory_path(scope, workdir)
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)
