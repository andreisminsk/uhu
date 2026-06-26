"""Base classes for skills — kept separate to avoid circular imports."""

import json


class Skill:
    """Base class for all skills.

    A skill is a structured development workflow that the model can invoke.
    Skills differ from tools: tools are atomic API operations (web search,
    calendar), while skills are multi-step development workflows (code review,
    test generation, documentation) that gather context and guide the model.

    Attributes:
        name: Unique skill identifier (used in **SKILL:`name`** blocks).
        description: One-line human-readable description.
        system_prompt: Detailed instructions appended to the system prompt
            when skills mode is enabled. Tells the model how and when to
            use this skill.
        parameters: Dict of parameter_name -> {"type", "required", "description"}.
        scripts: Dict of script_name -> script_path for executable scripts.
        references: List of reference file paths for context documents.
        skill_dir: Path to the skill directory (for directory-based skills).
    """
    name = ""
    description = ""
    system_prompt = ""
    parameters = {}
    scripts = {}
    references = []
    triggers = []
    skill_dir = None

    def execute(self, params, workdir=None, session=None):
        """Execute the skill with the given parameters.

        Args:
            params: Dict of skill parameters from the SKILL block JSON.
            workdir: Working directory for file operations.
            session: Optional ChatSession reference for advanced skills.

        Returns:
            A string observation to be fed back to the model.
        """
        raise NotImplementedError


class PromptOnlySkill(Skill):
    """A skill defined by a JSON file — prompt-only, no execution logic.

    When executed, returns a confirmation that the skill was invoked.
    The model's system prompt already contains the skill's instructions,
    so it knows how to respond.
    """

    def __init__(self, name, description, system_prompt, parameters=None):
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.parameters = parameters or {}

    def execute(self, params, workdir=None, session=None):
        param_str = json.dumps(params, ensure_ascii=False) if params else "{}"
        return f"[Skill {self.name} invoked]\nParameters: {param_str}\n{self.system_prompt}"


class MarkdownSkill(Skill):
    """A skill defined by a SKILL.md file in a directory-based layout.

    This is the primary skill format for project-level custom skills.
    The skill directory may contain:
    - SKILL.md: The skill definition with instructions
    - scripts/: Executable Python scripts the skill can invoke
    - references/: Context/reference documents the skill uses

    When executed, returns the skill's instructions along with any
    reference content, so the model knows how to proceed.

    Absolute paths detected at load time (e.g., /Users/andreis/HermesArea/)
    are stored in `base_paths` and replaced with the current workdir at
    execution time, making skills portable across machines and projects.
    """

    def __init__(self, name, description, system_prompt, parameters=None,
                 scripts=None, references=None, skill_dir=None, base_paths=None,
                 _script_warnings=None):
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.parameters = parameters or {}
        self.scripts = scripts or {}
        self.references = references or []
        self.skill_dir = skill_dir
        self.base_paths = base_paths or []
        self._script_warnings = _script_warnings or []

    def _rewrite_paths(self, text, workdir):
        """Replace hardcoded absolute paths with the current workdir.

        At load time, base_paths are detected from the SKILL.md content
        (e.g., /Users/andreis/HermesArea/). At execution time, those
        paths are replaced with the current project workdir so the
        skill works regardless of where the project is located.
        """
        if not self.base_paths or not workdir:
            return text
        import os
        # Normalize workdir for replacement (ensure trailing separator)
        workdir_normalized = workdir.rstrip(os.sep) + os.sep
        for base_path in self.base_paths:
            # Replace the base path with workdir throughout the text
            text = text.replace(base_path, workdir_normalized)
        return text

    def run_script(self, script_name, args=None, workdir=None):
        """Run a Python script from the skill's scripts/ directory.

        Args:
            script_name: Name of the script (without .py extension) or
                         relative path like 'scripts/fetch_news'.
            args: Optional list of string arguments to pass to the script.
            workdir: Working directory for the subprocess.

        Returns:
            Tuple of (return_code, stdout, stderr) from the script execution.
        """
        import subprocess
        import sys as _sys

        if not self.skill_dir or not self.scripts:
            return (1, "", f"No scripts available for skill '{self.name}'")

        # Resolve script path
        if script_name in self.scripts:
            rel_path = self.scripts[script_name]
        else:
            # Try as a direct path
            rel_path = script_name

        script_path = os.path.join(self.skill_dir, rel_path) if not os.path.isabs(rel_path) else rel_path
        if not os.path.isfile(script_path):
            # Try adding .py extension
            if not script_path.endswith('.py'):
                script_path_py = script_path + '.py'
                if os.path.isfile(script_path_py):
                    script_path = script_path_py
                else:
                    return (1, "", f"Script not found: {script_name}")
            else:
                return (1, "", f"Script not found: {script_name}")

        cmd = [_sys.executable, script_path]
        if args:
            cmd.extend(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=workdir or self.skill_dir,
            )
            return (result.returncode, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return (1, "", f"Script timed out after 60s: {script_name}")
        except Exception as e:
            return (1, "", f"Script execution failed: {e}")

    def validate_scripts(self, workdir=None):
        """Validate that all declared script files exist.

        Returns a list of (script_name, rel_path, exists_bool) tuples.
        """
        import os
        results = []
        for sname, spath in self.scripts.items():
            full_path = self.resolve_script_path(sname, workdir)
            exists = full_path is not None and os.path.isfile(full_path)
            results.append((sname, spath, exists))
        return results

    def resolve_script_path(self, script_name, workdir=None):
        """Resolve a script name to a workdir-relative path suitable for execution.

        Returns the workdir-relative path (e.g., '.skills/weather/scripts/fetch_weather.py')
        or None if the script cannot be found.
        """
        import os
        if script_name not in self.scripts:
            return None
        rel_path = self.scripts[script_name]
        # Build absolute path from skill_dir + relative path
        if self.skill_dir and not os.path.isabs(rel_path):
            abs_path = os.path.join(self.skill_dir, rel_path)
        else:
            abs_path = rel_path
        if not os.path.isfile(abs_path):
            # Try with .py extension
            if not abs_path.endswith('.py'):
                abs_path_py = abs_path + '.py'
                if os.path.isfile(abs_path_py):
                    abs_path = abs_path_py
                else:
                    return None
            else:
                return None
        # Convert to workdir-relative path for execution
        if workdir:
            try:
                rel = os.path.relpath(abs_path, workdir)
                return rel.replace('\\', '/')
            except ValueError:
                # Different drives on Windows
                return abs_path.replace('\\', '/')
        return abs_path.replace('\\', '/')

    def execute(self, params, workdir=None, session=None):
        import os
        param_str = json.dumps(params, ensure_ascii=False) if params else "{}"
        parts = [f"[Skill {self.name} invoked]", f"Parameters: {param_str}"]

        # Rewrite paths in system_prompt for portability
        prompt = self._rewrite_paths(self.system_prompt, workdir)

        # Validate scripts and report missing ones
        if self.scripts:
            validation = self.validate_scripts(workdir)
            missing = [(sname, spath) for sname, spath, exists in validation if not exists]
            if missing:
                missing_desc = ", ".join(f"{sname} ({spath})" for sname, spath in missing)
                parts.append(f"\n⚠ WARNING: Missing script files: {missing_desc}")
                parts.append("The skill may not work correctly. Check that script paths in SKILL.md are relative to the skill directory.")

        # Include reference content if available
        if self.references and self.skill_dir:
            ref_parts = []
            for ref_path in self.references:
                full_path = os.path.join(self.skill_dir, ref_path) if not os.path.isabs(ref_path) else ref_path
                if os.path.isfile(full_path):
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                        # Also rewrite paths inside reference content
                        content = self._rewrite_paths(content, workdir)
                        max_chars = 8000
                        if len(content) > max_chars:
                            content = content[:max_chars] + "\n[... truncated]"
                        ref_parts.append(f"--- Reference: {ref_path} ---\n{content}")
                    except Exception:
                        pass
            if ref_parts:
                parts.append(f"References ({len(ref_parts)} file(s)):")
                parts.extend(ref_parts)

        # Include available scripts with workdir-relative paths
        if self.scripts:
            script_list = []
            for sname, spath in self.scripts.items():
                resolved = self.resolve_script_path(sname, workdir)
                if resolved:
                    script_list.append(f"  {sname}: {resolved}")
                else:
                    script_list.append(f"  {sname}: {spath} [MISSING]")
            parts.append(f"\nAvailable scripts (use **RUN:** to execute):")
            parts.extend(script_list)

        parts.append(prompt)
        return "\n".join(parts)
