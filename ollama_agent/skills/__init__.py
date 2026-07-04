"""Skill registry, base class, and loader for custom development skills.

Supports two skill formats:
1. Directory-based (SKILL.md) — the primary format for project-level custom skills.
   Each skill is a directory containing SKILL.md, optional scripts/ and references/.
   Categories are top-level subdirectories that group related skills.
2. Flat files — JSON (.json) for prompt-only skills, Python (.py) for executable skills.
"""

import importlib.util
import json
import os
import re

from .base import Skill, PromptOnlySkill, MarkdownSkill
from .code_review import CodeReviewSkill
from .test_gen import TestGenSkill
from .doc_gen import DocGenSkill
from .plan import PlanSkill
from .md2pdf import Md2PdfSkill
from .what_if import WhatIfSkill
from .root_cause import RootCauseSkill
from .problem_solving import ProblemSolvingSkill
from .architect import ArchitectSkill
from .medicine import MedicineSkill
from .business_coach import BusinessCoachSkill
from .pro_bidder import ProBidderSkill
from .docx2md import Docx2MdSkill
from .text_writer import TextWriterSkill
from .graph_ai import GraphAiSkill


# ── Registry ───────────────────────────────────────────────────────────

_registry = {}


def register(skill_instance):
    """Register a skill instance."""
    _registry[skill_instance.name] = skill_instance


def get(name):
    """Get a skill by name."""
    return _registry.get(name)


def all_skills():
    """Return all registered skill instances."""
    return list(_registry.values())


def unregister(name):
    """Remove a skill from the registry."""
    _registry.pop(name, None)


def resolve_script(script_name, workdir=None):
    """Resolve a script name to a workdir-relative path across all registered skills.

    Searches all skills for a script matching script_name (without .py extension)
    or a path fragment. Returns the workdir-relative path if found, or None.

    This is used by the RUN block rewriter to fix short script paths.
    """
    for skill in _registry.values():
        if not hasattr(skill, 'scripts') or not skill.scripts:
            continue
        if script_name in skill.scripts:
            resolved = skill.resolve_script_path(script_name, workdir)
            if resolved:
                return resolved
    return None


def find_script_in_cmd(cmd_text, workdir=None):
    """Find and resolve any skill script references in a command string.

    Looks for patterns like:
    - scripts/name.py or scripts\name.py (skill-dir-relative)
    - name.py (bare script name)

    Skips patterns that are already part of a longer valid path
    (e.g., .skills/.../scripts/name.py is already workdir-relative).

    Returns list of (matched_text, resolved_path) tuples for replacement.
    Only returns the longest matching pattern per script (avoids overlapping
    matches like both 'scripts/foo.py' and 'foo.py').
    """
    import re as _re
    replacements = []
    for skill in _registry.values():
        if not hasattr(skill, 'scripts') or not skill.scripts:
            continue
        for script_name, script_rel_path in skill.scripts.items():
            resolved = skill.resolve_script_path(script_name, workdir)
            if not resolved:
                continue
            # Patterns that need rewriting, ordered longest-first
            # so we prefer 'scripts/name.py' over bare 'name.py'
            patterns = [
                f"scripts/{script_name}.py",
                f"scripts\\{script_name}.py",
                f"{script_name}.py",
            ]
            best_match = None
            for pattern in patterns:
                pos = cmd_text.find(pattern)
                if pos == -1:
                    continue
                # Check character before the match — if it's a path separator
                # or letter, this is part of a longer path, not a standalone ref
                if pos > 0:
                    ch_before = cmd_text[pos - 1]
                    # Allow: space, quote, start-of-string, equals, pipe, semicolon, ampersand, backtick, paren
                    if ch_before not in (' ', '\"', "'", '=', '|', ';', '&', '`', '('):
                        continue
                # Check if already part of a resolved workdir-relative path
                # e.g., ".skills/media/newsfeed/scripts/fetch_news.py" should NOT
                # trigger replacement of "scripts/fetch_news.py"
                before = cmd_text[:pos]
                prefix = resolved[:-len(pattern)] if resolved.endswith(pattern) else None
                if prefix and before.endswith(prefix):
                    continue  # Already a full workdir-relative path
                best_match = (pattern, resolved)
                break  # Use longest match only
            if best_match:
                replacements.append(best_match)
    return replacements


# ── System prompt builder ──────────────────────────────────────────────

def skills_system_prompt(enabled_names=None):
    """Build the system prompt section for enabled skills."""
    skills = all_skills() if enabled_names is None else [
        s for s in all_skills() if s.name in enabled_names
    ]
    if not skills:
        return ""

    parts = [
        "You have access to the following skills. To invoke a skill, use this format:",
        "",
        "**SKILL:`skill_name`**",
        "```json",
        '{"param": "value"}',
        "```",
        "**EOF:`skill_name`**",
        "",
        "IMPORTANT — SKILL ACTIVATION RULES:",
        "- When a user's request matches a skill (by trigger words or description), you MUST invoke that skill.",
        "- Do NOT just answer directly when a skill applies — invoke the skill and let it guide your response.",
        "- Match broadly: if the user asks about buying, pricing, deals, or valuations → use pro-bidder.\n"
        "  If they ask about symptoms, health, or medical concerns → use medicine.\n"
        "  If they ask 'what if' or about consequences → use what-if.\n"
        "  If they ask why something is happening → use root-cause.\n"
        "  If they ask how to solve a problem → use problem-solving.\n"
        "  If they ask about software/system design or architecture → use architect.\n"
        "  If they ask about business, startups, or entrepreneurship → use business-coach.\n"
        "  If they mention a .docx file or want to convert a Word document → use docx2md.\n"
        "  If they want to write, edit, or polish text → use text-writer.\n"
        "  If they want a diagram, dependency graph, ancestry, fishbone, timeline, or roadmap → use graph-ai.\n"
        "- Use tools (file I/O, git, web search, etc.) only when NO skill matches the user's intent.",
        "",
        "Available skills:",
        "",
    ]

    for s in skills:
        trigger_line = ""
        if hasattr(s, 'triggers') and s.triggers:
            trigger_line = f"\nTriggers: {', '.join(s.triggers)}"
        parts.append(f"**{s.name}** — {s.description}{trigger_line}")
        # Only include full instructions for built-in skills (code_review, test_gen, etc.)
        # Custom skills (MarkdownSkill) get their instructions when invoked,
        # not in the system prompt — this prevents the model from shortcutting
        # and using tools directly instead of invoking the skill.
        if not isinstance(s, MarkdownSkill):
            parts.append(s.system_prompt)
        parts.append("")

    return "\n".join(parts)


# ── SKILL.md parser ────────────────────────────────────────────────────

def _detect_base_paths(content):
    """Detect hardcoded absolute path prefixes in SKILL.md content.

    Finds common absolute path patterns (e.g., /Users/username/project/,
    C:\\Users\\username\\project\\) and extracts the project root — the
    shortest meaningful prefix (typically 3-4 path segments) — so it can
    be replaced with the current workdir at execution time.

    For example, if paths include:
      /Users/andreis/HermesArea/sapium/RUNBOOK.md
      /Users/andreis/HermesArea/be-aware.json
      /Users/andreis/HermesArea/travel-images/

    The project root is /Users/andreis/HermesArea/ — replacing it with
    the workdir preserves the subdirectory structure (sapium/, etc.).

    Returns a list of base path strings to replace.
    """
    import re as _re

    # Find all absolute path prefixes (directory paths ending with / or \)
    # Match paths like /Users/andreis/HermesArea/sapium/ or /home/user/project/
    unix_paths = _re.findall(r'/Users/\w+/[^/\s,\]"\')]+(?:/[^/\s,\]"\')]+)*/', content)
    unix_paths += _re.findall(r'/home/\w+/[^/\s,\]"\')]+(?:/[^/\s,\]"\')]+)*/', content)
    # Match Windows paths like C:\Users\username\project\
    win_paths = _re.findall(r'[A-Z]:\\Users\\\w+\\[^\\\s,\]"\']+(?:\\[^\\\s,\]"\']+)*\\', content)

    all_paths = unix_paths + win_paths

    if not all_paths:
        return []

    # Find the project root: the shortest path prefix that is at least
    # 3 levels deep (e.g., /Users/username/project/).
    # This preserves subdirectory structure when replacing.
    # Strategy: find the shortest detected path — that's the project root.
    all_paths.sort(key=len)

    # The shortest path is likely the project root
    # But verify: check if all other paths start with it
    candidate = all_paths[0]

    # If the shortest path is very short (< 3 segments), try to find
    # a better candidate by extracting the common 3-segment prefix
    def _segment_count(p, sep):
        return p.count(sep)

    # For Unix paths, the project root is typically /Users/<username>/<project>/
    # which is 3 segments after the leading /
    # For Windows: C:\Users\<username>\<project>\
    if '/' in candidate:
        # Extract /Users/<username>/<project>/ prefix
        m = _re.match(r'(/Users/\w+/[^/]+/)', candidate)
        if m:
            candidate = m.group(1)
        else:
            m = _re.match(r'(/home/\w+/[^/]+/)', candidate)
            if m:
                candidate = m.group(1)
    elif '\\' in candidate:
        m = _re.match(r'([A-Z]:\\Users\\\w+\\[^\\]+\\)', candidate)
        if m:
            candidate = m.group(1)

    # Verify all paths start with the candidate
    all_start = all(p.startswith(candidate) for p in all_paths)
    if all_start:
        return [candidate]

    # If not all paths share the same root, find unique roots
    # Group by the first 3 segments
    roots = set()
    for p in all_paths:
        if '/' in p:
            m = _re.match(r'(/Users/\w+/[^/]+/)', p) or _re.match(r'(/home/\w+/[^/]+/)', p)
            if m:
                roots.add(m.group(1))
        elif '\\' in p:
            m = _re.match(r'([A-Z]:\\Users\\\w+\\[^\\]+\\)', p)
            if m:
                roots.add(m.group(1))

    return sorted(roots)


def _parse_yaml_frontmatter(content):
    """Parse YAML frontmatter from markdown content.

    Frontmatter is delimited by --- at the start of the file.
    Returns (frontmatter_dict, body_content) or (None, content) if no frontmatter.
    """
    if not content.startswith('---'):
        return None, content

    lines = content.split('\n')
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            end_idx = i
            break

    if end_idx is None:
        return None, content

    frontmatter_text = '\n'.join(lines[1:end_idx])
    body = '\n'.join(lines[end_idx + 1:]).strip()

    # Simple YAML parser (no dependency needed)
    fm = {}
    current_key = None
    current_list = None

    for line in frontmatter_text.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        # List item: "  - value"
        if line.startswith('  - ') and current_key:
            if current_list is None:
                current_list = []
            current_list.append(stripped[2:].strip().strip('"').strip("'"))
            fm[current_key] = current_list
            continue

        # Key-value: "key: value"
        m = re.match(r'^(\w[\w-]*)\s*:\s*(.*)', stripped)
        if m:
            if current_list is not None and current_key in fm:
                fm[current_key] = current_list

            key = m.group(1).lower()
            value = m.group(2).strip()
            if value:
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                fm[key] = value
            else:
                fm[key] = None
            current_key = key
            current_list = None if value else []
            continue

    if current_list is not None and current_key in fm:
        fm[current_key] = current_list

    return fm, body


def _parse_markdown_sections(content):
    """Parse markdown content into sections by ## headings.

    Returns dict of section_name (lowercase) -> section_content (stripped).
    """
    sections = {}
    current_section = None
    current_lines = []
    for line in content.split('\n'):
        section_match = re.match(r'^##\s+(.+)', line)
        if section_match:
            if current_section is not None:
                sections[current_section] = '\n'.join(current_lines).strip()
            current_section = section_match.group(1).strip().lower()
            current_lines = []
        elif current_section is not None:
            current_lines.append(line)
    if current_section is not None:
        sections[current_section] = '\n'.join(current_lines).strip()
    return sections


def _parse_skill_md(skill_md_path):
    """Parse a SKILL.md file into a MarkdownSkill.

    Supports two formats:

    1. YAML frontmatter (common in Hermes-style skills):
       ---
       name: my-skill
       description: What this skill does
       triggers:
         - "trigger phrase"
       ---
       Instructions in markdown...

    2. Markdown sections (structured headings):
       # Skill: my-skill
       ## Description
       What this skill does.
       ## Instructions
       Detailed instructions...
       ## Parameters
       - path (string, required): File to process

    Returns a MarkdownSkill instance or None on failure.
    """
    try:
        with open(skill_md_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return None

    skill_dir = os.path.dirname(skill_md_path)

    # Try YAML frontmatter first
    frontmatter, body = _parse_yaml_frontmatter(content)

    name = ""
    description = ""
    instructions = ""
    sections = {}

    if frontmatter:
        # YAML frontmatter format
        name = frontmatter.get('name', '')
        if isinstance(name, list):
            name = name[0] if name else ''
        name = str(name).strip()

        description = frontmatter.get('description', '')
        if isinstance(description, list):
            description = description[0] if description else ''
        description = str(description).strip()

        # Body after frontmatter is the instructions
        instructions = body

        # Parse sections from the body (if any ## headings exist)
        sections = _parse_markdown_sections(body)
    else:
        # Markdown section format
        name_match = re.match(r'^#\s+(?:Skill:\s*)?(.+)', content, re.MULTILINE)
        if name_match:
            name = name_match.group(1).strip()

        sections = _parse_markdown_sections(content)

        description = sections.get('description', '').split('\n')[0].strip() if sections.get('description') else ""

        instructions = sections.get('instructions', '')
        if not instructions:
            instructions = content

    # If no name from heading/frontmatter, try description
    if not name and description:
        name = description.split('.')[0].strip()

    # Build system_prompt from instructions + examples
    system_prompt_parts = []
    if instructions:
        system_prompt_parts.append(instructions)
    if sections.get('examples'):
        system_prompt_parts.append("\nExamples:\n" + sections['examples'])
    if sections.get('scripts'):
        system_prompt_parts.append("\nScripts:\n" + sections['scripts'])
    system_prompt = '\n'.join(system_prompt_parts)

    # Parse parameters section
    parameters = _parse_parameters_section(sections.get('parameters', ''))

    # Discover scripts/ directory
    scripts = {}
    scripts_dir = os.path.join(skill_dir, 'scripts')
    if os.path.isdir(scripts_dir):
        for fn in sorted(os.listdir(scripts_dir)):
            if fn.endswith('.py') and not fn.startswith('_'):
                scripts[fn[:-3]] = os.path.join('scripts', fn)

    # Also check for scripts mentioned in the Scripts section
    if sections.get('scripts'):
        for line in sections['scripts'].split('\n'):
            line = line.strip().lstrip('- ').strip()
            if line and line not in scripts:
                script_path = line if os.path.isabs(line) else os.path.join(skill_dir, line)
                if os.path.isfile(script_path):
                    script_name = os.path.basename(line).replace('.py', '')
                    scripts[script_name] = line

    # Discover references/ directory
    references = []
    refs_dir = os.path.join(skill_dir, 'references')
    if os.path.isdir(refs_dir):
        for fn in sorted(os.listdir(refs_dir)):
            fpath = os.path.join('references', fn)
            if not fn.startswith('.') and os.path.isfile(os.path.join(skill_dir, fpath)):
                references.append(fpath)

    # Also check for references mentioned in the References section
    if sections.get('references'):
        for line in sections['references'].split('\n'):
            line = line.strip().lstrip('- ').strip()
            if line and line not in references:
                ref_path = line if os.path.isabs(line) else os.path.join(skill_dir, line)
                if os.path.isfile(ref_path):
                    references.append(line)

    # Detect hardcoded absolute paths for portability rewriting
    base_paths = _detect_base_paths(content)

    if not name:
        name = os.path.basename(skill_dir)

    # Normalize name: lowercase, replace spaces with hyphens
    name = name.lower().replace(' ', '-')

    # Validate that discovered script files actually exist
    script_warnings = []
    for sname, spath in scripts.items():
        full_script_path = os.path.join(skill_dir, spath) if not os.path.isabs(spath) else spath
        if not os.path.isfile(full_script_path):
            # Try with .py extension
            if not full_script_path.endswith('.py'):
                full_script_path_py = full_script_path + '.py'
                if not os.path.isfile(full_script_path_py):
                    script_warnings.append(f"{sname}: {spath} (file not found)")
    if script_warnings:
        # Store warnings on the skill for later reporting
        pass  # Will be reported via load_skills_from_dir return value

    return MarkdownSkill(
        name=name,
        description=description,
        system_prompt=system_prompt,
        parameters=parameters,
        scripts=scripts,
        references=references,
        skill_dir=skill_dir,
        base_paths=base_paths,
        _script_warnings=script_warnings,
    )


def _parse_parameters_section(text):
    """Parse a Parameters section into a dict of parameter definitions.

    Supports formats like:
    - path (string, required): File or directory to review
    - focus (string, optional): Focus area
    """
    if not text:
        return {}

    params = {}
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r'^[-*]\s+', '', line)
        m = re.match(r'`?(\w[\w-]*)`?\s*\((\w+)(?:,\s*(\w+))?\)\s*[:\-]\s*(.+)', line)
        if m:
            pname = m.group(1)
            ptype = m.group(2)
            prequired = m.group(3) or ""
            pdesc = m.group(4).strip()
            params[pname] = {
                "type": ptype,
                "required": "required" in prequired.lower(),
                "description": pdesc,
            }
    return params


# ── Skill loader ───────────────────────────────────────────────────────

def load_skills_from_dir(skills_dir, workdir=None):
    """Load skill definitions from a directory.

    Supports three formats:
    1. Directory-based (SKILL.md): skill_dir/category/skill_name/SKILL.md
       Categories are top-level subdirectories that group related skills.
       A category may have a DESCRIPTION.md but is not itself a skill.
    2. JSON files (.json): Flat prompt-only skill definitions
    3. Python files (.py): Executable skill definitions with Skill subclasses

    If workdir is provided, hardcoded absolute paths in SKILL.md content
    are rewritten to use the workdir, making skills portable across machines.

    Returns:
        Tuple of (loaded_count, errors_list)
    """
    if not os.path.isdir(skills_dir):
        return 0, [f"Skills directory not found: {skills_dir}"]

    loaded = 0
    errors = []

    def _finalize_skill(skill):
        """Register a skill, rewrite its paths, and report script warnings."""
        if skill and workdir and hasattr(skill, 'base_paths') and skill.base_paths:
            skill.system_prompt = skill._rewrite_paths(skill.system_prompt, workdir)
            skill.description = skill._rewrite_paths(skill.description, workdir)
        # Report script validation warnings
        if skill and hasattr(skill, '_script_warnings') and skill._script_warnings:
            for w in skill._script_warnings:
                errors.append(f"{skill.name}: script not found — {w}")
        return skill

    for entry in sorted(os.listdir(skills_dir)):
        entry_path = os.path.join(skills_dir, entry)

        # Skip hidden dirs (like .git) and __pycache__
        if entry.startswith('.') or entry == '__pycache__':
            continue

        if os.path.isdir(entry_path):
            skill_md = os.path.join(entry_path, 'SKILL.md')
            if os.path.isfile(skill_md):
                # Direct skill directory
                skill = _parse_skill_md(skill_md)
                if skill and skill.name:
                    _finalize_skill(skill)
                    register(skill)
                    loaded += 1
                else:
                    errors.append(f"{entry}/SKILL.md: could not parse skill name or instructions")
            else:
                # Category directory — scan for skill subdirectories
                loaded_cat, errors_cat = _load_category_dir(entry_path, entry, workdir)
                loaded += loaded_cat
                errors.extend(errors_cat)

        elif entry.endswith(".json"):
            try:
                with open(entry_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                skill_name = data.get("name", "")
                if not skill_name:
                    errors.append(f"{entry}: missing 'name' field")
                    continue
                if not data.get("system_prompt"):
                    errors.append(f"{entry}: missing 'system_prompt' field")
                    continue
                skill = PromptOnlySkill(
                    name=data["name"],
                    description=data.get("description", ""),
                    system_prompt=data["system_prompt"],
                    parameters=data.get("parameters", {}),
                )
                _finalize_skill(skill)
                register(skill)
                loaded += 1
            except Exception as e:
                errors.append(f"{entry}: {e}")

        elif entry.endswith(".py") and not entry.startswith("_"):
            try:
                module_name = f"skill_{entry[:-3]}"
                spec = importlib.util.spec_from_file_location(module_name, entry_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                found = 0
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type)
                            and issubclass(attr, Skill)
                            and attr is not Skill
                            and attr is not PromptOnlySkill
                            and attr is not MarkdownSkill
                            and hasattr(attr, 'name')
                            and attr.name):
                        _finalize_skill(attr())
                        register(attr())
                        found += 1
                        loaded += 1
                if found == 0:
                    errors.append(f"{entry}: no Skill subclasses with a 'name' attribute found")
            except Exception as e:
                errors.append(f"{entry}: {e}")

    return loaded, errors


def _load_category_dir(category_path, category_name, workdir=None):
    """Load skills from a category directory.

    A category directory contains skill subdirectories, each with a SKILL.md.
    It may also have a DESCRIPTION.md describing the category.

    Returns:
        Tuple of (loaded_count, errors_list)
    """
    loaded = 0
    errors = []

    def _finalize_skill(skill):
        """Rewrite paths and report script warnings."""
        if skill and workdir and hasattr(skill, 'base_paths') and skill.base_paths:
            skill.system_prompt = skill._rewrite_paths(skill.system_prompt, workdir)
            skill.description = skill._rewrite_paths(skill.description, workdir)
        # Report script validation warnings
        if skill and hasattr(skill, '_script_warnings') and skill._script_warnings:
            for w in skill._script_warnings:
                errors.append(f"{skill.name}: script not found — {w}")
        return skill

    for entry in sorted(os.listdir(category_path)):
        entry_path = os.path.join(category_path, entry)

        if entry.startswith('.') or entry == '__pycache__':
            continue
        if not os.path.isdir(entry_path):
            continue

        skill_md = os.path.join(entry_path, 'SKILL.md')
        if os.path.isfile(skill_md):
            skill = _parse_skill_md(skill_md)
            if skill and skill.name:
                _finalize_skill(skill)
                register(skill)
                loaded += 1
            else:
                errors.append(f"{category_name}/{entry}/SKILL.md: could not parse skill name or instructions")
        else:
            # Could be a nested sub-category — try recursing one level
            for sub_entry in sorted(os.listdir(entry_path)):
                sub_path = os.path.join(entry_path, sub_entry)
                if os.path.isdir(sub_path):
                    sub_md = os.path.join(sub_path, 'SKILL.md')
                    if os.path.isfile(sub_md):
                        skill = _parse_skill_md(sub_md)
                        if skill and skill.name:
                            _finalize_skill(skill)
                            register(skill)
                            loaded += 1
                        else:
                            errors.append(f"{category_name}/{entry}/{sub_entry}/SKILL.md: could not parse")

    return loaded, errors


# Register built-in skills
register(CodeReviewSkill())
register(TestGenSkill())
register(DocGenSkill())
register(PlanSkill())
register(Md2PdfSkill())
register(WhatIfSkill())
register(RootCauseSkill())
register(ProblemSolvingSkill())
register(ArchitectSkill())
register(MedicineSkill())
register(BusinessCoachSkill())
register(ProBidderSkill())
register(Docx2MdSkill())
register(TextWriterSkill())
register(GraphAiSkill())
