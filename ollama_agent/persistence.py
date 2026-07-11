"""Session save/restore logic for ChatSession."""

import json
import os
from datetime import datetime

from .constants import AGENT_SYSTEM_PROMPT, get_platform_shell_guidance
from .input_utils import read_full_input
from .utils import relative_time
from .actions import agent_print
from .constants import ANSI_AGENT


class PersistenceMixin:
    """Session persistence methods for ChatSession: save, restore, list sessions."""

    def _session_path(self, name):
        safe = name.replace(" ", "_")
        if not safe.endswith(".json"):
            safe += ".json"
        return os.path.join(self.sessions_dir, safe)

    def _auto_name(self):
        project_name = os.path.basename(self.workdir) or "session"
        return f"{project_name}_{datetime.now().strftime('%Y%m%d_%H%M')}"

    def _do_autosave(self):
        msgs = [m for m in self.history if m["role"] != "system"]
        if not msgs:
            return
        path = self._session_path(self.autosave_name)
        data = {"saved": datetime.now().isoformat(), "model": self.model, "ctx_size": self.ctx_size,
                "messages": len(msgs), "history": self.history}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._log("system", f"[Autosave failed: {e}]")

    def do_save(self, name):
        name = name.strip() or self._auto_name()
        msgs = [m for m in self.history if m["role"] != "system"]
        if not msgs:
            agent_print("[Nothing to save]\n")
            return
        path = self._session_path(name)
        data = {"saved": datetime.now().isoformat(), "model": self.model, "ctx_size": self.ctx_size,
                "messages": len(msgs), "history": self.history}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            agent_print(f"[Saved: {path} ({len(msgs)} messages)]\n")
            self._log("system", f"[/save {name}]")
        except Exception as e:
            self._log("system", f"[Save failed: {e}]")
            agent_print(f"[Save failed: {e}]\n")

    def do_restore(self, name):
        name = name.strip()
        # If name is a number, resolve it to the Nth session (1-based, newest first)
        if name and name.isdigit():
            sessions = self._list_sessions()
            idx = int(name) - 1
            if 0 <= idx < len(sessions):
                name = sessions[idx]["name"]
            else:
                agent_print(f"[Invalid session number: {name}. {len(sessions)} session(s) available.]\n")
                return
        if not name:
            sessions = self._list_sessions()
            if not sessions:
                agent_print("[No saved sessions]\n")
                return
            agent_print("Saved sessions:")
            for i, s in enumerate(sessions, 1):
                rel = relative_time(s["saved"])
                agent_print(f"  {i}. {s['name']}  —  {s['saved_display']}  —  {rel}  —  {s['messages']} messages  —  model: {s['model']}")
            agent_print()
            try:
                choice = read_full_input("Restore which? (number or name, Enter to cancel): ", color=ANSI_AGENT).strip()
            except (KeyboardInterrupt, EOFError):
                agent_print("\n[Cancelled]\n")
                return
            if not choice:
                agent_print("[Cancelled]\n")
                return
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(sessions):
                    name = sessions[idx]["name"]
                else:
                    agent_print("[Invalid number]\n")
                    return
            else:
                name = choice
        path = self._session_path(name)
        if not os.path.isfile(path):
            self._log("system", f"[Session not found: {path}]")
            agent_print(f"[Session not found: {path}]\n")
            return
        non_sys = [m for m in self.history if m["role"] != "system"]
        if non_sys:
            try:
                confirm = read_full_input(f"[Current history has {len(non_sys)} messages. Replace? (y/N)]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                agent_print("\n[Cancelled]\n")
                return
            if confirm != "y":
                agent_print("[Cancelled]\n")
                return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.history.clear()
            from .system_prompt import build_system_prompt, get_memory_warnings
            system_prompt = build_system_prompt(
                self.workdir, agent=self.agent, tools=self.tools, skills=self.skills
            )
            if system_prompt:
                self.history.append({"role": "system", "content": system_prompt})
            for w in get_memory_warnings(self.workdir):
                agent_print(f"[⚠ {w}]")
            loaded = [m for m in data["history"] if m["role"] != "system"]
            # Only load messages that fit within 80% of context, keeping most recent
            # Token estimate: tokens ≈ len(content) / 4
            def _est_tokens(msgs):
                return sum(len(m["content"]) / 4 for m in msgs)
            max_tokens = self.ctx_size * 0.8
            total_tokens = _est_tokens(loaded)
            if total_tokens > max_tokens:
                kept = []
                used_tokens = 0
                for m in reversed(loaded):
                    m_tokens = len(m["content"]) / 4
                    if used_tokens + m_tokens > max_tokens:
                        break
                    kept.insert(0, m)
                    used_tokens += m_tokens
                dropped = len(loaded) - len(kept)
                self.history.extend(kept)
                agent_print(f"[⚠ {dropped} older message(s) dropped to fit context — use /compact to compress further]")
            else:
                self.history.extend(loaded)
            saved_model = data.get("model", "unknown")
            agent_print(f"[Restored: {name} ({len(self.history) - len([m for m in self.history if m['role'] == 'system'])} of {len(loaded)} messages, model: {saved_model})]")
            if saved_model != self.model:
                agent_print(f"[⚠ Saved with '{saved_model}', currently '{self.model}']")
            # Keep autosave name from restored session so derivatives inherit it
            # Strip any existing timestamp suffix (e.g. MyProj1_20260710_2245 → MyProj1)
            import re as _re
            base_name = _re.sub(r'_\d{8}_\d{4}$', '', name)
            self.autosave_name = f"{base_name}_{datetime.now().strftime('%Y%m%d_%H%M')}"
            agent_print(f"[Autosave name set to: {self.autosave_name}]")
            agent_print()
            self.show_ctx()
            agent_print("[⚠️ Note: Context usage above is estimated. It will adjust to actual after your next message.]\n")
            # Show last AI message for context
            last_ai = None
            for m in reversed(self.history):
                if m["role"] == "assistant":
                    last_ai = m["content"]
                    break
            if last_ai:
                agent_print("[Last AI message:]\n")
                print(last_ai)
                agent_print("\n")
            self._log("system", f"[/restore {name}]")
        except Exception as e:
            self._log("system", f"[Restore failed: {e}]")
            agent_print(f"[Restore failed: {e}]\n")

    def _list_sessions(self):
        sessions = []
        try:
            for fname in os.listdir(self.sessions_dir):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(self.sessions_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    saved_iso = data.get("saved", "?")
                    try:
                        saved_dt = datetime.fromisoformat(saved_iso)
                        saved_display = saved_dt.strftime("%Y-%m-%d %H:%M")
                    except (ValueError, TypeError):
                        saved_display = str(saved_iso)
                    sessions.append({"name": fname[:-5], "saved": saved_iso, "saved_display": saved_display,
                                     "model": data.get("model", "?"), "messages": data.get("messages", len(data.get("history", [])))})
                except Exception:
                    pass
        except Exception:
            pass
        sessions.sort(key=lambda s: s["saved"], reverse=True)
        return sessions

    def do_sessions(self):
        sessions = self._list_sessions()
        if not sessions:
            agent_print(f"[No saved sessions in {self.sessions_dir}]\n")
            return
        agent_print(f"Saved sessions in {self.sessions_dir}:")
        for s in sessions:
            rel = relative_time(s["saved"])
            agent_print(f"  {s['name']:<30} {s['saved_display']}   {rel:<18} {s['messages']:>3} messages   model: {s['model']}")
        agent_print()
