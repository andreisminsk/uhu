"""Action execution: WRITE, EDIT, RUN, FILE, TOOL blocks from LLM output."""

import json
import os
import queue as _queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from .constants import SAFE_TOOLS, SKIP_EXT
from .constants import MAX_CONSOLE_DISPLAY_CHARS, MAX_BATCH_WRITES
from .constants import ANSI_AGENT
from .approval import ApprovalGate
from .command_runner import CommandRunner, _fix_win_backslash_quote
from .display import agent_print, tool_print, show_diff_colored
from .file_executor import FileExecutor, FileCache, RollbackManager
from .observation import truncate_observations
from .parser import parse_actions, _PATH_SIGNAL, _BASH_BLOCK
from .safety import CommandSafetyGate, get_base_command, resolve_tool_name
from .skills.base import PromptOnlySkill, MarkdownSkill

class ActionMixin:
    """Action execution methods for ChatSession: WRITE, EDIT, RUN, FILE, TOOL."""

    # Names that are obviously placeholders, not real file paths or tool/skill names
    _PLACEHOLDER_NAMES = {"path", "name", "filepath", "filename", "file_path", "file_name", "skill", "skill_name"}

    # Safety gate — extracted to safety.py for testability
    _safety = CommandSafetyGate()

    # Approval gate — extracted to approval.py for testability
    _approval = None  # lazily initialized per-instance

    def _check_command_safety(self, cmd):
        """Check a command for safety. Delegates to CommandSafetyGate."""
        return self._safety.check(cmd)

    @staticmethod
    def _get_base_command(cmd):
        """Extract the base command name from a shell command string."""
        return get_base_command(cmd)

    def _is_safe_command(self, cmd):
        """Check if a command is considered safe/read-only (no confirmation needed)."""
        return self._safety.is_safe(cmd)

    def _show_diff_colored(self, diff_text):
        """Display a diff or detail text with color coding."""
        show_diff_colored(diff_text)

    @staticmethod
    def _truncate_for_console(text, limit=MAX_CONSOLE_DISPLAY_CHARS):
        """Truncate text for console display, adding a note if truncated."""
        if len(text) <= limit:
            return text
        return text[:limit] + f"\n[... {len(text)} chars total, truncated for display]"

    def _get_approval(self):
        """Get or create the ApprovalGate for this instance."""
        if self._approval is None:
            self._approval = ApprovalGate(self.workdir, quiet=getattr(self, 'quiet', False))
            # Sync state from legacy attributes if they exist
            if hasattr(self, 'auto_all'):
                self._approval.auto_all = self.auto_all
            if hasattr(self, 'auto_writes'):
                self._approval.auto_writes = self.auto_writes
            if hasattr(self, 'always_writes'):
                self._approval.always_writes = self.always_writes
            if hasattr(self, 'auto_run_prefixes'):
                self._approval.auto_run_prefixes = self.auto_run_prefixes
            if hasattr(self, 'always_runs'):
                self._approval.always_runs = self.always_runs
            if hasattr(self, '_skill_auto_approve'):
                self._approval._skill_auto_approve = self._skill_auto_approve
        return self._approval

    def _confirm_or_auto(self, prompt, path=None, cmd=None, diff_text=None, force_confirm=False):
        """Confirm an action. Delegates to ApprovalGate."""
        gate = self._get_approval()
        result = gate.confirm(prompt, path=path, cmd=cmd, diff_text=diff_text, force_confirm=force_confirm)
        # Sync state back to legacy attributes
        self.auto_all = gate.auto_all
        self.auto_writes = gate.auto_writes
        self.always_writes = gate.always_writes
        self.auto_run_prefixes = gate.auto_run_prefixes
        self.always_runs = gate.always_runs
        self._skill_auto_approve = gate._skill_auto_approve
        return result

    def _coder_config_path(self):
        """Return the path to the project's persistent auto-approval config."""
        return self._get_approval().config_path()

    def _load_coder_config(self):
        """Load persistent auto-approval settings. Delegates to ApprovalGate."""
        gate = self._get_approval()
        gate.load_config()
        # Sync state back to legacy attributes
        self.always_writes = gate.always_writes
        self.always_runs = gate.always_runs

    def _save_coder_config(self):
        """Save persistent auto-approval settings. Delegates to ApprovalGate."""
        gate = self._get_approval()
        gate.always_writes = self.always_writes
        gate.always_runs = self.always_runs
        gate.save_config()

    # ── File executor delegation ────────────────────────────────────────

    _file_executor = None  # lazily initialized per-instance

    def _get_file_executor(self):
        """Get or create the FileExecutor for this instance."""
        if self._file_executor is None:
            self._file_executor = FileExecutor(
                workdir=self.workdir,
                ctx_size=self.ctx_size,
                cache=FileCache(self.workdir, enabled=self.cache_files),
                rollback=RollbackManager(self.workdir),
                confirm_fn=self._confirm_or_auto,
                show_diff=self.show_diff,
                log_fn=self._log,
            )
        return self._file_executor

    def _cache_file(self, path, content):
        """Delegate to FileCache."""
        return self._get_file_executor().cache.cache(path, content)

    def _save_pre_edit(self, path, pre_edit_content):
        """Delegate to RollbackManager."""
        self._get_file_executor().rollback.save(path, pre_edit_content)

    def _rollback_edits(self, modified, created):
        """Delegate to RollbackManager."""
        self._get_file_executor().rollback.rollback(modified, created)

    def execute_write(self, action):
        """Execute a WRITE action. Delegates to FileExecutor."""
        return self._get_file_executor().execute_write(action)

    def execute_edit(self, action):
        """Execute an EDIT action. Delegates to FileExecutor."""
        return self._get_file_executor().execute_edit(action)

    def execute_read(self, action):
        """Execute a FILE: read action. Delegates to FileExecutor."""
        return self._get_file_executor().execute_read(action)

    def execute_run(self, action):
        """Execute a shell command. Delegates to CommandRunner."""
        runner = CommandRunner(self.workdir, safety=self._safety)
        return runner.run(
            cmd=action["code"],
            run_lang=action.get("lang", ""),
            workdir=self.workdir,
            confirm_fn=self._confirm_or_auto,
        )

    def execute_tool(self, action):
        """Execute a tool invocation action."""
        from .tools import get as get_tool, all_tools
        tool_name = action["name"]
        params = action.get("params", {})
        json_error = action.get("json_error")
        if json_error:
            msg = (
                f"[TOOL FAILED: {tool_name} — malformed JSON in parameters: {json_error}. "
                f"Please fix the JSON syntax and retry. "
                f"Use: **TOOL:`{tool_name}`** then a ```json block with valid JSON, then **EOF:`{tool_name}`**]"
            )
            agent_print(msg + "\n")
            return msg
        all_tool_names = [t.name for t in all_tools()]
        tool, corrected_name, error_msg = resolve_tool_name(tool_name, all_tool_names, get_tool, self.workdir)
        if not tool:
            agent_print(error_msg + "\n")
            return error_msg
        if corrected_name != tool_name:
            agent_print(f"[Auto-corrected tool name: '{tool_name}' → '{corrected_name}']")
            tool_name = corrected_name
        params_preview = json.dumps(params, ensure_ascii=False)
        if len(params_preview) > 60:
            params_preview = params_preview[:57] + "..."
        # Safety check for run_command tool — block/warn on dangerous commands
        safety_confirmed = False
        if tool_name == "run_command":
            cmd = params.get("command", "")
            safety_level, safety_msg = self._check_command_safety(cmd)
            if safety_level == 'blocked':
                agent_print(f"⛔ {safety_msg}\n")
                return None
            safety_confirmed = False
            if safety_level == 'warning':
                agent_print(f"{safety_msg}")
                params_details = f"[Tool details]\n  name: {tool_name}\n  params:\n{json.dumps(params, indent=4, ensure_ascii=False)}"
                if not self._confirm_or_auto(f"[CONFIRM DESTRUCTIVE] {tool_name}({params_preview})", cmd=cmd, diff_text=params_details, force_confirm=True):
                    agent_print("[Skipped]\n")
                    return None
                safety_confirmed = True
            elif safety_level == 'chain':
                agent_print(f"{safety_msg}")
                params_details = f"[Tool details]\n  name: {tool_name}\n  params:\n{json.dumps(params, indent=4, ensure_ascii=False)}"
                if not self._confirm_or_auto(f"[TOOL] {tool_name}({params_preview})", cmd=cmd, diff_text=params_details):
                    agent_print("[Skipped]\n")
                    return None
                safety_confirmed = True

        # Auto-approve safe tools (read-only, no side effects)
        # py_compile is auto-safe only for syntax/import actions (not 'run', which executes code)
        # Skip general confirmation if already confirmed by safety check above
        if safety_confirmed:
            pass
        elif tool_name in SAFE_TOOLS or (tool_name == "py_compile" and params.get("action") in ("syntax", "import")):
            agent_print(f"[auto-safe: {tool_name}] [TOOL] {tool_name}({params_preview})")
        else:
            params_details = f"[Tool details]\n  name: {tool_name}\n  params:\n{json.dumps(params, indent=4, ensure_ascii=False)}"
            if not self._confirm_or_auto(f"[TOOL] {tool_name}({params_preview})", cmd=tool_name, diff_text=params_details):
                agent_print("[Skipped]\n")
                return None
        # Check for missing required parameters
        if not params:
            required = [k for k, v in tool.parameters.items() if v.get("required", False)]
            if required:
                param_hint = ", ".join(f'"{r}": ...' for r in required)
                msg = (
                    f"[TOOL FAILED: {tool_name} — missing required parameters: {', '.join(required)}. "
                    f"Use: **TOOL:`{tool_name}`** then a ```json block with "
                    f"{{{param_hint}}}, then **EOF:`{tool_name}`**]"
                )
                agent_print(msg + "\n")
                return msg
        try:
            result = tool.execute(params, workdir=self.workdir)
            msg = f"[TOOL {tool_name}]: {result}"
            tool_print(self._truncate_for_console(msg) + "\n")
            return msg
        except Exception as e:
            msg = f"[TOOL FAILED: {tool_name}: {e}]"
            agent_print(msg + "\n")
            return msg

    def execute_skill(self, action):
        """Execute a skill invocation action."""
        from .skills import get as get_skill
        skill_name = action["name"]
        params = action.get("params", {})
        json_error = action.get("json_error")
        if json_error:
            msg = (
                f"[SKILL FAILED: {skill_name} — malformed JSON in parameters: {json_error}. "
                f"Please fix the JSON syntax and retry. "
                f"Use: **SKILL:`{skill_name}`** then a ```json block with valid JSON, then **EOF:`{skill_name}`**]"
            )
            agent_print(msg + "\n")
            return msg
        skill = get_skill(skill_name)
        if not skill:
            msg = f"[SKILL FAILED: Unknown skill '{skill_name}']"
            agent_print(msg + "\n")
            return msg
        params_preview = json.dumps(params, ensure_ascii=False)
        if len(params_preview) > 60:
            params_preview = params_preview[:57] + "..."
        params_details = f"[Skill details]\n  name: {skill_name}\n  description: {skill.description}\n  params:\n{json.dumps(params, indent=4, ensure_ascii=False)}"
        if hasattr(skill, 'scripts') and skill.scripts:
            script_list = ", ".join(skill.scripts.keys())
            params_details += f"\n  scripts: {script_list}"
            # Validate scripts exist and show resolved paths
            if hasattr(skill, 'validate_scripts'):
                validation = skill.validate_scripts(workdir=self.workdir)
                missing = [(sn, sp) for sn, sp, ex in validation if not ex]
                if missing:
                    missing_desc = ", ".join(f"{sn} ({sp})" for sn, sp in missing)
                    params_details += f"\n  ⚠ MISSING SCRIPTS: {missing_desc}"
        if not self._confirm_or_auto(f"[SKILL] {skill_name}({params_preview})", cmd=skill_name, diff_text=params_details):
            agent_print("[Skipped]\n")
            return None
        # Skill approved — auto-approve subsequent actions in this skill's workflow
        self._skill_auto_approve = True
        self._active_skill = skill
        # Show explicit skill invocation indicator
        skill_type = "prompt-only" if isinstance(skill, PromptOnlySkill) else "markdown"
        desc_preview = skill.description[:80] + "..." if len(skill.description) > 80 else skill.description
        agent_print(f"\n{'='*60}")
        agent_print(f"⚡ SKILL INVOKED: {skill_name} ({skill_type})")
        agent_print(f"  Description: {desc_preview}")
        if params:
            param_items = ", ".join(f"{k}={v!r}" for k, v in params.items())
            agent_print(f"  Params: {param_items}")
        if hasattr(skill, 'scripts') and skill.scripts:
            # Show resolved workdir-relative paths
            resolved_scripts = []
            for sn in skill.scripts:
                if hasattr(skill, 'resolve_script_path'):
                    rp = skill.resolve_script_path(sn, workdir=self.workdir)
                    resolved_scripts.append(f"{sn} → {rp}" if rp else f"{sn} [MISSING]")
                else:
                    resolved_scripts.append(sn)
            agent_print(f"  Scripts: {', '.join(resolved_scripts)}")
        agent_print(f"{'='*60}\n")
        try:
            result = skill.execute(params, workdir=self.workdir, session=self)
            # For built-in (non-Markdown) skills, prepend the system_prompt
            # since it's no longer in the system prompt (lazy loading).
            # MarkdownSkill already includes its instructions in execute().
            if not isinstance(skill, PromptOnlySkill) and not isinstance(skill, MarkdownSkill):
                if hasattr(skill, 'system_prompt') and skill.system_prompt:
                    result = f"{skill.system_prompt}\n\n---\n\n{result}"
            agent_print(f"\n{'─'*60}")
            agent_print(f"⚡ SKILL RESULT: {skill_name} ({skill_type})")
            tool_print(self._truncate_for_console(result))
            agent_print(f"{'─'*60}\n")
            msg = f"⚡ [SKILL {skill_name} ({skill_type})]: {result}"
            return msg
        except Exception as e:
            agent_print(f"\n{'─'*60}")
            agent_print(f"⚡ SKILL FAILED: {skill_name}: {e}")
            agent_print(f"{'─'*60}\n")
            msg = f"[SKILL FAILED: {skill_name}: {e}]"
            return msg

    def process_actions(self, response_text):
        if not self.agent and not self.tools and not self.skills:
            if _PATH_SIGNAL.search(response_text) or _BASH_BLOCK.search(response_text):
                agent_print("[hint: response contains **WRITE:**/**EDIT:**/**TOOL:**/**SKILL:** blocks -- add --agent, --tools, and/or --skills to execute them]\n")
            return (None, False, False, False)
        actions = parse_actions(response_text)
        if not actions:
            # Check if the model wrote signal lines but with incomplete format
            if _PATH_SIGNAL.search(response_text):
                return ("[SYSTEM WARNING: Tool/action signal detected but block format is incomplete. "
                        "For TOOL blocks, use: **TOOL:`tool_name`** then a ```json block with params, then **EOF:`tool_name`**. "
                        "For RUN blocks, use **RUN:** then a ```cmd (or bash/powershell) block with the command. "
                        "Do NOT write bare signal lines without content blocks.]", False, False, False)
            return (None, False, False, False)
        modified = set()
        created = set()
        observations = []
        missing_eof_paths = []
        user_cancelled_run = False
        has_executed_non_read = False
        has_executed_skill = False
        total_read_chars = 0
        max_total_read_chars = min(self.ctx_size, 200000)
        placeholder_warnings = []
        write_count = 0
        for action in actions:
            action_path = action.get("path") or action.get("name")
            if action_path and action_path.lower().strip() in self._PLACEHOLDER_NAMES:
                placeholder_warnings.append(
                    f"[SYSTEM WARNING: {action['type'].upper()} block uses placeholder '{action_path}' "
                    f"instead of a real file path or tool name. "
                    f"Use actual values like **{action['type'].upper()}:`src/app.py`**]"
                )
                continue
            if action["type"] == "write":
                if not self.agent:
                    observations.append(f"[Skipped: WRITE {action['path']} — add --agent to execute]")
                    continue
                path = action["path"]
                if path not in modified and path not in created:
                    full_path = os.path.join(self.workdir, path) if not os.path.isabs(path) else path
                    if os.path.isfile(full_path):
                        try:
                            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                                self._save_pre_edit(path, f.read())
                            modified.add(path)
                        except Exception:
                            modified.add(path)
                    else:
                        created.add(path)
                obs = self.execute_write(action)
                if obs is None:
                    observations.append(f"[Skipped: WRITE {action['path']}]")
                else:
                    has_executed_non_read = True
                    write_count += 1
                if not action.get("closed"):
                    missing_eof_paths.append(action["path"])
            elif action["type"] == "edit":
                if not self.agent:
                    observations.append(f"[Skipped: EDIT {action['path']} — add --agent to execute]")
                    continue
                path = action["path"]
                if path not in modified and path not in created:
                    full_path = os.path.join(self.workdir, path) if not os.path.isabs(path) else path
                    if os.path.isfile(full_path):
                        try:
                            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                                self._save_pre_edit(path, f.read())
                            modified.add(path)
                        except Exception:
                            modified.add(path)
                obs = self.execute_edit(action)
                if obs is None:
                    observations.append(f"[Skipped: EDIT {action['path']}]")
                else:
                    has_executed_non_read = True
                    write_count += 1
                if not action.get("closed"):
                    missing_eof_paths.append(action["path"])
            elif action["type"] == "read":
                if total_read_chars >= max_total_read_chars:
                    observations.append(f"[Skipped: READ {action['path']} — total read size limit ({max_total_read_chars} chars) reached]")
                    if not action.get("closed"):
                        missing_eof_paths.append(action["path"])
                    continue
                if not self.agent:
                    observations.append(f"[Skipped: READ {action['path']} — add --agent to execute]")
                    if not action.get("closed"):
                        missing_eof_paths.append(action["path"])
                    continue
                obs = self.execute_read(action)
                if obs:
                    total_read_chars += len(obs)
                    if total_read_chars > max_total_read_chars:
                        excess = total_read_chars - max_total_read_chars
                        obs = obs[:-excess] + "\n[... truncated to fit read size limit]"
                        total_read_chars = max_total_read_chars
                if not action.get("closed"):
                    missing_eof_paths.append(action["path"])
            elif action["type"] == "tool":
                if not self.tools:
                    observations.append(f"[Skipped: TOOL {action['name']} — add --tools to execute]")
                    continue
                obs = self.execute_tool(action)
                if obs is None:
                    observations.append(f"[Skipped: TOOL {action['name']}]")
                else:
                    has_executed_non_read = True
                if not action.get("closed"):
                    missing_eof_paths.append(action["name"])
            elif action["type"] == "skill":
                if not self.skills:
                    observations.append(f"[Skipped: SKILL {action['name']} — add --skills to execute]")
                    continue
                obs = self.execute_skill(action)
                if obs is None:
                    observations.append(f"[Skipped: SKILL {action['name']}]")
                else:
                    has_executed_skill = True
                if not action.get("closed"):
                    missing_eof_paths.append(action["name"])
            else:
                if not self.agent:
                    cmd_preview = action["code"][:60]
                    observations.append(f"[Skipped: RUN {cmd_preview} — add --agent to execute]")
                    continue
                obs = self.execute_run(action)
                if obs is None:
                    user_cancelled_run = True
                    cmd_preview = action["code"][:60]
                    observations.append(f"[Skipped: RUN {cmd_preview}]")
                else:
                    has_executed_non_read = True
                    # Suggest FILE: for failed file-reading commands
                    cmd = action["code"].strip()
                    cmd_base = self._get_base_command(cmd).lower()
                    if cmd_base in ('type', 'cat', 'less', 'more', 'head', 'tail'):
                        run_failed = (
                            obs.startswith('[Run failed:') or
                            obs.startswith('[Run killed]') or
                            (obs.startswith('[Run rc=') and not obs.startswith('[Run rc=0]'))
                        )
                        if run_failed:
                            parts = cmd.split(None, 1)
                            if len(parts) > 1:
                                file_path = parts[1].strip().strip('"').strip("'")
                                # Remove trailing arguments (e.g., "type file.txt | more")
                                if ' ' in file_path and os.path.sep not in file_path and not file_path.startswith('-'):
                                    first_token = file_path.split()[0]
                                    if '.' in first_token or os.path.sep in first_token:
                                        file_path = first_token
                                obs += (
                                    f"\n[Tip: Use **FILE:**`{file_path}` with **EOF:**`{file_path}` "
                                    f"to read files directly — more reliable than RUN: {cmd_base}]"
                                )
            if obs:
                observations.append(obs)
                if action["type"] in ("write", "edit") and ("FAILED" in obs or "failed" in obs):
                    if modified or created:
                        n_modified = len(modified)
                        n_created = len(created)
                        self._rollback_edits(modified, created)
                        msg = f"[Rolled back {n_modified} modified, {n_created} created file(s) after {action['type']} failure]"
                        agent_print(msg + "\n")
                        observations.append(msg)
                    break
        if missing_eof_paths:
            observations.append(
                f"[SYSTEM WARNING: Missing **EOF:** markers for: {', '.join(missing_eof_paths)}. "
                f"Always conclude file blocks with **EOF:`filename`** (using the same path as the opening marker) to prevent truncation or merging.]"
            )
        if write_count > MAX_BATCH_WRITES:
            note = f"[Note: {write_count} file changes in this round. Prefer {MAX_BATCH_WRITES} or fewer per round for reviewability.]"
            agent_print(note + "\n")
            observations.append(note)
            agent_print(note + "\n")
            observations.append(note)
        if placeholder_warnings:
            for w in placeholder_warnings:
                agent_print(w + "\n")
            observations.extend(placeholder_warnings)
        result = truncate_observations(observations)
        return (result, user_cancelled_run, has_executed_non_read, has_executed_skill)
