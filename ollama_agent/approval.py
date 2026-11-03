"""Approval gate and config store — extracted from actions.py for testability.

Handles:
- User confirmation flow (y/N/auto/all/always/d)
- Auto-approval state (session + persistent)
- Config persistence (.uhu/coderconfig.json)
"""

import json
import os

from .constants import ANSI_AGENT
from .display import agent_print, show_diff_colored
from .input_utils import read_full_input
from . import sound





def _llm_explain_from_gate(gate, title, diff_text):
    """Explain action details via the Parser LLM, with independent judgement.

    Called AFTER the raw diff/details are already displayed — this only adds
    the LLM's analysis on top. Returns True if an explanation was shown,
    False if the explainer is not configured.
    """
    cfg = getattr(gate, "_explain_cfg", None)
    if not cfg or not cfg.get("enabled"):
        return False
    from .llm_parser import _llm_explain
    model = cfg.get("model", "")
    base_url = cfg.get("base_url", "")
    timeout = cfg.get("timeout", 60)
    api_type = cfg.get("api_type", "ollama")
    api_key = cfg.get("api_key", "ollama")
    agent_print(f"[LLM explainer: asking {model or 'main model'} for independent analysis...]")
    explanation, error = _llm_explain(base_url, model, title + "\n\n" + diff_text, timeout=timeout, api_type=api_type, api_key=api_key)
    if error:
        agent_print(f"[LLM explainer unavailable: {error}]\n")
        return True
    agent_print("\n" + explanation + "\n")
    return True


class ApprovalGate:
    """Manages auto-approval state and user confirmation prompts.

    Attributes:
        auto_all: If True, all actions are auto-approved this session.
        auto_writes: Set of paths auto-approved for writing this session.
        always_writes: Set of paths always auto-approved (persisted).
        auto_run_prefixes: Set of command prefixes auto-approved this session.
        always_runs: Set of command prefixes always auto-approved (persisted).
        _skill_auto_approve: If True, auto-approve actions in skill workflow.
    """

    def __init__(self, workdir, quiet=False):
        self.workdir = workdir
        self.quiet = quiet
        self.auto_all = False
        self.auto_writes = set()
        self.always_writes = set()
        self.auto_run_prefixes = set()
        self.always_runs = set()
        self._skill_auto_approve = False
        self._config_loaded = False
        # Config for the optional 'd' → LLM explainer (independent action analysis).
        # Populated by ChatSession.__init__ from the llm_parser section of
        # .ollama_agent.json; 'explain' key enables it (see README).
        self._explain_cfg = None

    # ── Config persistence ────────────────────────────────────────────────

    def config_path(self):
        """Return the path to the project's persistent auto-approval config."""
        return os.path.join(self.workdir, ".uhu", "coderconfig.json")

    def load_config(self):
        """Load persistent auto-approval settings from .uhu/coderconfig.json."""
        config_path = self.config_path()
        if not os.path.isfile(config_path):
            return
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            for path in config.get("always_writes", []):
                self.always_writes.add(path)
            for prefix in config.get("always_runs", []):
                self.always_runs.add(prefix)
            n_writes = len(self.always_writes)
            n_runs = len(self.always_runs)
            if n_writes or n_runs:
                parts = []
                if n_writes:
                    parts.append(f"{n_writes} always-write path(s)")
                if n_runs:
                    parts.append(f"{n_runs} always-run command(s)")
                if not self.quiet:
                    agent_print(f"[Loaded {config_path}: {', '.join(parts)}]")
        except Exception:
            pass
        self._config_loaded = True

    def save_config(self):
        """Save persistent auto-approval settings to .uhu/coderconfig.json."""
        config_path = self.config_path()
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            config = {
                "always_writes": sorted(self.always_writes),
                "always_runs": sorted(self.always_runs),
            }
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ── Confirmation flow ────────────────────────────────────────────────

    def confirm(self, prompt, path=None, cmd=None, diff_text=None, force_confirm=False):
        """Confirm an action with y/N/auto/all/d options.

        Press 'd' to see a diff or details before confirming.
        The prompt loops back after showing the diff.

        If force_confirm=True, skip auto-approve mechanisms (auto_all, skill, etc.)
        and require explicit user confirmation. Used for destructive commands.
        """
        while True:
            if not force_confirm and self.auto_all:
                agent_print(f"[auto-all] {prompt}")
                return True
            if not force_confirm and self._skill_auto_approve:
                skill_hint = ""
                if cmd and ".skills/" in cmd:
                    import re as _re
                    m = _re.search(r'\.skills/(?:[^/]+/)?([^/]+)/', cmd)
                    if m:
                        skill_hint = f" (skill: {m.group(1)})"
                agent_print(f"[auto-skill{skill_hint}] {prompt}")
                return True
            if path and (path in self.auto_writes or path in self.always_writes):
                source = "always" if path in self.always_writes else "auto"
                agent_print(f"[{source}-write: {path}] {prompt}")
                return True
            if cmd:
                for prefix in self.auto_run_prefixes | self.always_runs:
                    if cmd.strip() == prefix or cmd.strip().startswith(prefix + " "):
                        source = "always" if prefix in self.always_runs else "auto"
                        agent_print(f"[{source}-run: {prefix}] {prompt}")
                        return True
            try:
                sound.play("question")
                ans = read_full_input(f"{prompt} (y/N/auto/all/always/d): ", color=ANSI_AGENT).strip().lower()
            except EOFError:
                return False
            # KeyboardInterrupt propagates up to _feedback_loop which handles
            # it gracefully — printing "[Feedback interrupted]" and returning
            # to the prompt. Catching it here would silently treat Ctrl+C as
            # "No" instead of interrupting.
            if ans in ("y", "yes"):
                return True
            elif ans in ("n", "no"):
                return False
            elif ans == "auto":
                if path:
                    self.auto_writes.add(path)
                    agent_print(f"[Auto-write: {path} — auto-approved this session]\n")
                elif cmd:
                    self.auto_run_prefixes.add(cmd.strip())
                    agent_print(f"[Auto-run: {cmd.strip()} — auto-approved this session]\n")
                return True
            elif ans == "always":
                if path:
                    self.always_writes.add(path)
                    self.auto_writes.add(path)
                    self.save_config()
                    agent_print(f"[Always-write: {path} — auto-approved in all future sessions]\n")
                elif cmd:
                    self.always_runs.add(cmd.strip())
                    self.auto_run_prefixes.add(cmd.strip())
                    self.save_config()
                    agent_print(f"[Always-run: {cmd.strip()} — auto-approved in all future sessions]\n")
                return True
            elif ans == "all":
                self.auto_all = True
                agent_print("[Auto-all enabled — all actions auto-approved this session]\n")
                return True
            elif ans in ("d", "diff"):
                # Always show the raw details/diff first; then, when enabled
                # via llm_parser.explain in .ollama_agent.json, append the
                # LLM explainer's independent (context-free) analysis.
                if diff_text:
                    show_diff_colored(diff_text)
                    # Pass the FULL details (cwd + complete command) and a
                    # neutral title. Two bugs made the explainer useless on
                    # multi-line commands: (1) _extract_run_code returned only
                    # the single "cmd: " line — for heredocs that's just
                    # `python3 - <<'PY'`, the entire payload was dropped; and
                    # (2) the prompt title embeds cmd[:80] + '…', so the LLM
                    # received a fragment cut mid-line and answered
                    # "NOT ANALYZABLE — truncated" instead of a verdict.
                    _llm_explain_from_gate(
                        self,
                        "Command details" if cmd else prompt,
                        diff_text,
                    )
                else:
                    agent_print("[No details available for this action]\n")
                continue
            return False
