"""Slash-command handlers for ChatSession."""

import os
import re
import sys

from .constants import MIME_TYPES, IMAGE_MIME_TYPES, SKIP_EXT, MODEL_TEMPERATURE
from .actions import agent_print


class CommandMixin:
    """Slash-command handlers: /help, /attach, /search, /peek, /ls, /md, /auto, /compact, /multiline."""

    def do_skills(self):
        """List available skills."""
        from .skills import all_skills
        skills = all_skills()
        if not skills:
            agent_print("[No skills available]\n")
            return
        agent_print(f"Available skills ({len(skills)}):")
        for s in skills:
            param_str = ""
            if s.parameters:
                param_parts = []
                for pname, pinfo in s.parameters.items():
                    req = "required" if pinfo.get("required") else "optional"
                    ptype = pinfo.get("type", "any")
                    pdesc = pinfo.get("description", "")
                    param_parts.append(f"      {pname} ({ptype}, {req}): {pdesc}")
                param_str = "\n" + "\n".join(param_parts)
            extras = ""
            if s.scripts:
                extras += f" [{len(s.scripts)} script(s)]"
            if s.references:
                extras += f" [{len(s.references)} ref(s)]"
            if s.skill_dir:
                extras += f" (from {os.path.relpath(s.skill_dir, self.workdir)})"
            agent_print(f"  {s.name}: {s.description}{extras}{param_str}")
        agent_print()

    def show_ctx(self, exact_tokens=None):
        if exact_tokens is not None:
            total_tokens = exact_tokens
            source = ""
        else:
            total_tokens = int(sum(len(m["content"]) / 4 for m in self.history))
            source = "~"
        pct = total_tokens / self.ctx_size * 100
        bar_len = 20
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        warning = " ⚠ Consider '/compact'" if pct >= 80 else ""
        ctx_msg = f"[ctx: {bar} {source}{total_tokens}/{self.ctx_size} ({pct:.1f}%){warning}]"
        agent_print(ctx_msg + "\n")
        self._log("system", ctx_msg)

    def do_help(self):
        mode_parts = []
        if self.agent:
            mode_parts.append("agent")
        if self.tools:
            mode_parts.append("tools")
        if self.skills:
            mode_parts.append("skills")
        mode_str = f" | Mode: {'+'.join(mode_parts)}" if mode_parts else ""

        agent_print(
            f"Available commands{mode_str}:\n"
            "\n"
            "  /help                        Show this help message\n"
            "  /reset                       Clear conversation history (keeps system prompt)\n"
            "  /history                     Show context usage bar\n"
            "  /v, /ver, /version           Show version\n"
            "  /sober                       Re-inject system prompt to refocus the model\n"
            "  /compact                     Summarize history into a compact briefing\n"
            "  /auto                        Toggle auto-all mode / show approval settings\n"
            "  /auto reset                  Clear session auto-approvals\n"
            "  /auto reset always           Clear persistent (always) approvals\n"
            "  /auto reset all              Clear both session and persistent approvals\n"
            "  /diff                        Toggle auto-diff for edits (press d at any prompt for on-demand)\n"
            "  /memorize [project|agent] <text>  Add entry to permanent memory\n"
            "  /sober                       Re-inject system prompt to refocus the model\n"
            "  /compact memory [project|agent]   Compact memory file using LLM\n"
            "\n"
            "  /m, /multiline               Enter multiline mode (empty line or /end to submit)\n"
            "  /attach <path|glob|dir> [L<start>-<end>]\n"
            "                               Attach file(s) to next message\n"
            "  /attach-bin <path>           Attach binary file reference (image, audio, PDF, etc.)\n"
            "  /embed-bin <path>            Embed image directly into next message (for vision models)\n"
            "  /search <pattern> <glob>     Grep for pattern across files\n"
            "  /peek <path>                 Show head+tail of a file\n"
            "  /ls [path]                   List directory contents\n"
            "  /md <path>                   Create a directory\n"
            "\n"
            "  /skills                      List available skills\n"
            "  /diff                        Toggle auto-diff for edits\n"
            "\n"
            "  /save [name]                 Save session\n"
            "  /restore [name|number]        Restore a saved session\n"
            "  /sessions                    List all saved sessions\n"
            "\n"
            "  exit, /exit, /bye, bye       Exit the session\n"
        )

        if self.agent:
            agent_print(
                "\n"
            "Agent mode (--agent) is active. The model can:\n"
            "  **WRITE:`path`** ... **EOF:`path`**   Create or overwrite files\n"
            "  **EDIT:`path`** ... **EOF:`path`**   Search/replace edits to existing files\n"
            "  **FILE:`path`** ... **EOF:`path`**   Read files into context\n"
            "  **RUN:** + fenced shell block            Execute shell commands\n"
            "  **TOOL:`name`** + JSON params + **EOF:`name`**  Invoke a tool\n"
            "\n"
            "Confirmation options: y (once), auto (this session), all (everything this session),\n"
            "  always (all sessions, saved to .uhu/coderconfig.json), d (show diff), N (skip)\n"
            )
        if self.tools:
            agent_print(
                "\n"
            "Tools mode (--tools) is active. The model can invoke tools:\n"
            "  **TOOL:`name`** + JSON params + **EOF:`name`**\n"
            "  Available tools: web_search, web_fetch, image-analysis, llm_query, google_calendar\n"
            )
        if self.skills:
            agent_print(
                "\n"
                "Skills mode (--skills) is active. The model can invoke skills:\n"
                "  **SKILL:`name`** + JSON params + **EOF:`name`**\n"
                "  Built-in skills: code-review, test-gen, doc-gen, plan\n"
                "  Use /skills to list all available skills\n"
            )

    def do_multiline(self):
        agent_print("[Multiline mode — type freely, Enter on empty line or /end to submit, Ctrl+C to cancel]")
        lines = []
        while True:
            try:
                if sys.stdin.isatty():
                    prompt_str = "... " if lines else ">>> "
                    line = input(prompt_str)
                else:
                    line = sys.stdin.readline()
                    if not line:
                        break
                    line = line.rstrip('\n\r')
            except KeyboardInterrupt:
                agent_print("\n[Cancelled]\n")
                return None
            except EOFError:
                if not lines:
                    agent_print("\n[Cancelled]\n")
                    return None
                break
            stripped = line.strip()
            if stripped == "/end":
                break
            if stripped == "" and lines:
                break
            lines.append(line)
        if not lines:
            agent_print("[Empty input]\n")
            return None
        text = "\n".join(lines)
        agent_print(f"[Multiline: {len(lines)} line(s)]\n")
        return text

    def do_version(self):
        """Show version from uhu-ver.txt."""
        import os
        ver_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uhu-ver.txt")
        try:
            with open(ver_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
            agent_print(f"uhu v{version}\n")
        except FileNotFoundError:
            agent_print("[Version file not found]\n")

    def do_sober(self):
        """Re-inject the system prompt to refocus the model."""
        sys_msgs = [m for m in self.history if m["role"] == "system"]
        if not sys_msgs:
            agent_print("[No system prompt found in context]\n")
            return
        system_content = sys_msgs[0]["content"]
        self.history.append({"role": "system", "content": system_content})
        self.history.append({"role": "assistant", "content": "Understood. I will follow all instructions above carefully."})
        agent_print(f"[System prompt re-injected ({len(system_content)} chars)]\n")
        self.show_ctx()

    def do_compact(self, args_str=""):
        # Handle memory compaction: /compact memory [project|agent]
        args = (args_str or "").strip().lower()
        if args.startswith("memory"):
            scope = "project"
            remainder = args[len("memory"):].strip()
            if remainder == "agent":
                scope = "agent"
            elif remainder == "project":
                scope = "project"
            from .memory import compact_memory, load_memory
            sections = load_memory(scope, self.workdir)
            if not sections:
                label = "Project" if scope == "project" else "Agent"
                agent_print(f"[{label} memory is empty — nothing to compact]\n")
                return
            agent_print(f"[Compacting {scope} memory...]")
            try:
                new_lines = compact_memory(scope, self.workdir)
                agent_print(f"[Memory compacted: {new_lines} lines]\n")
            except RuntimeError as e:
                agent_print(f"[Error compacting memory: {e}]\n")
            return

        if not self.history:
            agent_print("[Nothing to compact]\n")
            return
        msgs = [m for m in self.history if m["role"] != "system"]
        if not msgs:
            agent_print("[Nothing to compact]\n")
            return
        agent_print("[Compacting context...]\n")

        # Two-tier strategy: keep recent messages verbatim, summarize older ones.
        # Reserve 30% of context for recent messages, try to summarize the rest.
        # Token estimate: tokens ≈ len(content) / 4, so chars = tokens * 4
        total_chars = sum(len(m["content"]) for m in msgs)
        recent_budget = int(self.ctx_size * 0.3 * 4)  # 30% of ctx in chars

        # Collect recent messages (from newest backward) that fit in budget
        recent_msgs = []
        recent_chars = 0
        for m in reversed(msgs):
            if recent_chars + len(m["content"]) > recent_budget:
                break
            recent_msgs.insert(0, m)
            recent_chars += len(m["content"])

        older_msgs = msgs[:len(msgs) - len(recent_msgs)]
        sys_msgs = [m for m in self.history if m["role"] == "system"]

        if not older_msgs:
            # No older messages to summarize — just keep what we have
            agent_print("[Context is already compact — no older messages to compress]\n")
            self.show_ctx()
            return

        # Try to summarize older messages
        summary = None
        if older_msgs:
            # Limit older conversation to 50% of context for summarization input
            max_input_chars = int(self.ctx_size * 0.5 * 4)
            older_parts = []
            older_total = 0
            for m in older_msgs:
                part = f"{m['role'].upper()}: {m['content']}"
                if older_total + len(part) > max_input_chars:
                    older_parts.insert(0, "[... earliest conversation truncated ...]\n")
                    break
                older_parts.insert(0, part)
                older_total += len(part)
            conversation_text = "\n".join(older_parts)
            summary_prompt = (
                "Summarize the following conversation into a concise but complete briefing. "
                "Preserve all key facts, decisions, code, file paths, and conclusions. "
                "Write it as a compact context block, not as a narrative:\n\n" + conversation_text
            )
            try:
                response = self.client.chat(
                    model=self.model,
                    messages=[{"role": "user", "content": summary_prompt}],
                    options={"num_ctx": self.ctx_size, "temperature": MODEL_TEMPERATURE}
                )
                summary = response["message"]["content"]
                # Sanity check: if summary is too short or looks like a chat response, discard it
                if not summary or len(summary) < 100 or summary.strip().endswith("?"):
                    summary = None
            except Exception as e:
                self._log("system", f"[/compact summary failed: {e}]")
                summary = None

        # Rebuild history
        self.history.clear()
        self.history.extend(sys_msgs)
        if summary:
            self.history.append({"role": "user", "content": f"[Conversation summary]\n{summary}"})
            self.history.append({"role": "assistant", "content": "Understood. Ready to continue."})
            self._log("system", f"[/compact summary]\n{summary}")
            agent_print(f"Summary of older messages:\n{summary}\n")
        else:
            # Summarization failed or produced garbage — drop older messages with a note
            self.history.append({"role": "user", "content": "[Earlier conversation was compacted but could not be summarized. Key context may be lost.]"})
            self.history.append({"role": "assistant", "content": "Understood. I'll work with the remaining context."})
            self._log("system", "[/compact: summary failed or too short, older messages dropped]")
            agent_print("[Could not generate a useful summary — older messages dropped, recent context preserved]\n")

        # Always append recent messages verbatim
        self.history.extend(recent_msgs)

        agent_print(f"[Compacted: {len(older_msgs)} older messages {'summarized' if summary else 'dropped'}, {len(recent_msgs)} recent messages kept]\n")
        self.show_ctx()
        agent_print("[\u26a0 Note: Context usage above is estimated. It will adjust to actual after your next message.]\n")
        self._do_autosave()

    def do_attach(self, args_str):
        args_str = args_str.strip()
        if not args_str:
            agent_print("[Usage: /attach <path|glob|dir> [L<start>-<end>]]\n")
            return
        m = re.match(r'''["'](.+?)["']\s*(.*)''', args_str)
        if m:
            path, rest = m.group(1), m.group(2)
        else:
            parts = args_str.split()
            path, rest = parts[0], " ".join(parts[1:])
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(self.workdir, path)
        line_range = rest.strip() or None
        import glob as _glob
        files, is_multi = [], False
        if os.path.isdir(path):
            if line_range:
                agent_print("[Line ranges only work with single files]\n")
                return
            for root, _, fnames in os.walk(path):
                for fn in sorted(fnames):
                    if os.path.splitext(fn)[1].lower() not in SKIP_EXT:
                        files.append(os.path.join(root, fn))
            is_multi = True
        elif "*" in path or "?" in path:
            if line_range:
                agent_print("[Line ranges only work with single files]\n")
                return
            files = sorted(_glob.glob(path, recursive=True))
            is_multi = True
        elif os.path.isfile(path):
            files = [path]
        else:
            expanded = _glob.glob(path, recursive=True)
            if expanded:
                if line_range:
                    agent_print("[Line ranges only work with single files]\n")
                    return
                files = sorted(expanded)
                is_multi = True
            else:
                agent_print(f"[File not found: {path}]\n")
                return
        if not files:
            agent_print(f"[No files found: {path}]\n")
            return
        limit = self.ctx_size * 3
        parts, total_chars, skipped, file_info = [], 0, 0, []
        for fpath in files:
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    all_lines = f.readlines()
            except Exception:
                skipped += 1
                continue
            rel = os.path.relpath(fpath, self.workdir)
            content_raw = "".join(all_lines)
            lines_count = content_raw.count("\n") + (1 if content_raw and not content_raw.endswith("\n") else 0)
            file_info.append((rel, lines_count))
            if not is_multi and line_range:
                rm = re.match(r'[Ll](\d+)-(\d+)', line_range)
                if rm:
                    start, end = int(rm.group(1)) - 1, int(rm.group(2))
                    selected = all_lines[start:end]
                    content = f"[File: {rel} L{start+1}-{end}]\n{''.join(selected)}"
                    agent_print(f"[Attached: {rel} lines {start+1}-{end} ({len(selected)} lines)]\n")
                    self.pending_content.append(content)
                    return
                else:
                    agent_print(f"[Bad range format, use L10-50]\n")
                    return
            if total_chars + len(content_raw) > limit:
                remaining = limit - total_chars
                if remaining > 0:
                    content_raw = content_raw[:remaining]
                    file_info[-1] = (rel + " (truncated)", lines_count)
                else:
                    skipped += 1
                    continue
            total_chars += len(content_raw)
            parts.append(f"[File: {rel}]\n{content_raw}")
        if not parts:
            agent_print(f"[No readable files found in {path}]\n")
            return
        content = "\n".join(parts)
        self.pending_content.append(content)
        if is_multi:
            lines = [f"  {name} ({cnt} lines)" for name, cnt in file_info]
            suffix = f"\n  ... {skipped} file(s) skipped" if skipped else ""
            agent_print(f"[Attached {len(parts)} file(s) from {path}{suffix}]")
            for line in lines:
                agent_print(line)
            agent_print()
        else:
            rel, cnt = file_info[0]
            trunc_note = " (truncated)" if total_chars >= limit else ""
            agent_print(f"[Attached: {rel} ({cnt} lines){trunc_note}]\n")

    def do_search(self, args_str):
        import glob as _glob
        args_str = args_str.strip()
        if not args_str:
            agent_print("[Usage: /search <pattern> <glob_or_path>]\n")
            return
        parts = args_str.split(None, 1)
        if len(parts) < 2:
            agent_print("[Usage: /search <pattern> <glob_or_path>]\n")
            return
        pattern, target = parts[0], parts[1]
        if (target.startswith('"') and target.endswith('"')) or (target.startswith("'") and target.endswith("'")):
            target = target[1:-1]
        target = os.path.expanduser(target)
        if not os.path.isabs(target):
            target = os.path.join(self.workdir, target)
        files = []
        if os.path.isdir(target):
            for root, _, fnames in os.walk(target):
                for fn in fnames:
                    files.append(os.path.join(root, fn))
        elif "*" in target or "?" in target:
            files = _glob.glob(target, recursive=True)
        elif os.path.isfile(target):
            files = [target]
        else:
            files = _glob.glob(os.path.join(".", target), recursive=True)
        if not files:
            agent_print(f"[No files matched: {target}]\n")
            return
        try:
            rx = re.compile(pattern)
        except re.error as e:
            agent_print(f"[Bad pattern: {e}]\n")
            return
        matches = []
        for fpath in sorted(files):
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if rx.search(line):
                            matches.append(f"{fpath}:{lineno}: {line.rstrip()}")
                            if len(matches) >= 200:
                                break
            except Exception:
                pass
            if len(matches) >= 200:
                break
        if not matches:
            agent_print(f"[No matches for '{pattern}' in {target}]\n")
            return
        total = len(matches)
        if total > 50:
            matches = matches[:50]
            suffix = f"\n... ({total - 50} more matches)"
        else:
            suffix = ""
        output = "\n".join(matches) + suffix
        snippet = f"[Search: '{pattern}' in {target}]\n{output}"
        self.pending_content.append(snippet)
        agent_print(f"[{total} match(es){' (showing 50)' if total > 50 else ''} — staged]\n")

    def do_peek(self, args_str):
        raw = args_str.strip()
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            raw = raw[1:-1]
        path = os.path.expanduser(raw)
        if not os.path.isabs(path):
            path = os.path.join(self.workdir, path)
        if not path:
            agent_print("[Usage: /peek <path>]\n")
            return
        if not os.path.isfile(path):
            agent_print(f"[File not found: {path}]\n")
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            n = 20
            if len(lines) <= n * 2:
                content = "".join(lines)
            else:
                content = "".join(lines[:n]) + f"\n... ({len(lines) - n*2} lines) ...\n" + "".join(lines[-n:])
            snippet = f"[Peek: {os.path.basename(path)} ({len(lines)} lines total)]\n{content}"
            self.pending_content.append(snippet)
            agent_print(f"[Peeked: {path} ({len(lines)} lines) — staged]\n")
        except Exception as e:
            agent_print(f"[Peek failed: {e}]\n")

    def do_ls(self, args_str):
        raw = args_str.strip()
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            raw = raw[1:-1]
        path = os.path.expanduser(raw or ".")
        if not os.path.isabs(path):
            path = os.path.join(self.workdir, path)
        if not os.path.isdir(path):
            if os.path.isfile(path):
                agent_print(f"[Not a directory: {path} (use /peek or /attach)]\n")
            else:
                agent_print(f"[Not found: {path}]\n")
            return
        try:
            entries = sorted(os.listdir(path))
        except Exception as e:
            agent_print(f"[List failed: {e}]\n")
            return
        if not entries:
            agent_print(f"[Empty directory: {path}]\n")
            return
        dirs, files = [], []
        for name in entries:
            full = os.path.join(path, name)
            dirs.append(name + "/") if os.path.isdir(full) else files.append(name)
        lines = (dirs or []) + (files or [])
        agent_print(f"[{path}] ({len(dirs)} dirs, {len(files)} files)")
        for line in lines:
            agent_print(f"  {line}")
        agent_print()

    def do_md(self, args_str):
        raw = args_str.strip()
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            raw = raw[1:-1]
        path = os.path.expanduser(raw)
        if not path:
            agent_print("[Usage: /md <path>]\n")
            return
        if not os.path.isabs(path):
            path = os.path.join(self.workdir, path)
        if os.path.isdir(path):
            agent_print(f"[Already exists: {path}]\n")
            return
        try:
            os.makedirs(path, exist_ok=True)
            agent_print(f"[Created: {path}]\n")
        except Exception as e:
            agent_print(f"[mkdir failed: {e}]\n")

    def do_attach_bin(self, args_str):
        """Attach a binary file reference (not content) to the next message."""
        raw = args_str.strip()
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            raw = raw[1:-1]
        if not raw:
            agent_print("[Usage: /attach-bin <path>]\n")
            return
        path = os.path.expanduser(raw)
        if not os.path.isabs(path):
            path = os.path.join(self.workdir, path)
        path = os.path.normpath(path)
        if not os.path.isfile(path):
            agent_print(f"[File not found: {path}]\n")
            return
        ext = os.path.splitext(path)[1].lower()
        mime = MIME_TYPES.get(ext)
        if not mime:
            agent_print(f"[Unknown binary type: {ext} — supported: {', '.join(sorted(set(MIME_TYPES.keys())))}]\n")
            return
        size = os.path.getsize(path)
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        rel = os.path.relpath(path, self.workdir)
        ref = (
            f"[Binary file: {rel}]\n"
            f"  Path: {path}\n"
            f"  Type: {mime}\n"
            f"  Size: {size_str} ({size} bytes)\n"
            f"  Extension: {ext}"
        )
        self.pending_content.append(ref)
        agent_print(f"[Binary reference attached: {rel} ({mime}, {size_str})]\n")

    def do_embed_bin(self, args_str):
        """Embed an image file directly into the next message for vision models."""
        import base64
        raw = args_str.strip()
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            raw = raw[1:-1]
        if not raw:
            agent_print("[Usage: /embed-bin <path>]\n")
            return
        path = os.path.expanduser(raw)
        if not os.path.isabs(path):
            path = os.path.join(self.workdir, path)
        path = os.path.normpath(path)
        if not os.path.isfile(path):
            agent_print(f"[File not found: {path}]\n")
            return
        ext = os.path.splitext(path)[1].lower()
        mime = MIME_TYPES.get(ext)
        if not mime:
            agent_print(f"[Unknown binary type: {ext} — supported: {', '.join(sorted(set(MIME_TYPES.keys())))}]\n")
            return
        if mime not in IMAGE_MIME_TYPES:
            agent_print(f"[Not an image type: {mime} — /embed-bin only supports image types for vision models]\n")
            return
        size = os.path.getsize(path)
        max_size = 20 * 1024 * 1024  # 20 MB
        if size > max_size:
            agent_print(f"[Image too large: {size / (1024*1024):.1f} MB — maximum is 20 MB]\n")
            return
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        try:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            agent_print(f"[Error reading file: {e}]\n")
            return
        filename = os.path.basename(path)
        self.pending_embeds.append({"filename": filename, "mime": mime, "size": size, "base64": b64})
        agent_print(f"[Image embedded: {filename} ({mime}, {size_str}) — type your message or press Enter to send as-is]\n")

    def do_memorize(self, args_str):
        """Add an entry to permanent memory."""
        from .memory import add_memory_entry, check_memory_size, get_memory_config

        args = args_str.strip()
        if not args:
            agent_print("Usage: /memorize [project|agent] <text>")
            agent_print("  /memorize Use pytest for testing        → adds to project memory")
            agent_print("  /memorize project Use pytest for testing → adds to project memory")
            agent_print("  /memorize agent Always respond in Russian → adds to agent memory\n")
            return

        # Determine scope
        scope = "project"
        text = args
        if args.startswith("project "):
            scope = "project"
            text = args[len("project "):].strip()
        elif args.startswith("agent "):
            scope = "agent"
            text = args[len("agent "):].strip()

        if not text:
            agent_print("[Error: no text to memorize]\n")
            return

        path, section, was_new = add_memory_entry(scope, self.workdir, text)
        label = "Project" if scope == "project" else "Agent"
        if was_new:
            agent_print(f"[{label} memory created: {path}]")
        else:
            agent_print(f"[{label} memory updated: {path}]")
        agent_print(f"  Added to ## {section}: {text}")

        # Size warning
        line_count, warn_level = check_memory_size(scope, self.workdir)
        cfg = get_memory_config(self.workdir)
        if warn_level == 1:
            agent_print(f"  ⚠ Memory is getting large ({line_count}/{cfg['max_lines']} lines). Consider /compact memory.")
        elif warn_level == 2:
            agent_print(f"  ⚠ Memory is at capacity ({line_count}/{cfg['max_lines']} lines). Use /compact memory to free space.")
        agent_print()

    def do_auto(self, args_str):
        sub = args_str.strip().lower()
        if sub == "reset":
            self.auto_all = False
            self.auto_writes.clear()
            self.auto_run_prefixes.clear()
            agent_print("[All session auto-approvals cleared]\n")
            return
        if sub == "reset always":
            self.always_writes.clear()
            self.always_runs.clear()
            self._save_coder_config()
            agent_print("[All persistent (always) approvals cleared]\n")
            return
        if sub == "reset all":
            self.auto_all = False
            self.auto_writes.clear()
            self.auto_run_prefixes.clear()
            self.always_writes.clear()
            self.always_runs.clear()
            self._save_coder_config()
            agent_print("[All session and persistent approvals cleared]\n")
            return
        if sub in ("on", "true", "1"):
            self.auto_all = True
        elif sub in ("off", "false", "0"):
            self.auto_all = False
        elif sub == "":
            self.auto_all = not self.auto_all
        else:
            agent_print(f"[Unknown /auto option: {sub} — use: /auto, /auto on, /auto off, /auto reset]\n")
            return
        status = "ON" if self.auto_all else "OFF"
        agent_print(f"[auto-all: {status}]")
        if self.auto_writes:
            agent_print(f"  Auto-writes ({len(self.auto_writes)}):")
            for p in sorted(self.auto_writes):
                tag = " (always)" if p in self.always_writes else ""
                agent_print(f"    {p}{tag}")
        if self.auto_run_prefixes:
            agent_print(f"  Auto-run commands ({len(self.auto_run_prefixes)}):")
            for p in sorted(self.auto_run_prefixes):
                tag = " (always)" if p in self.always_runs else ""
                agent_print(f"    {p}{tag}")
        if self.always_writes and not self.auto_writes:
            agent_print(f"  Always-writes ({len(self.always_writes)}):")
            for p in sorted(self.always_writes):
                agent_print(f"    {p}")
        if self.always_runs and not self.auto_run_prefixes:
            agent_print(f"  Always-run commands ({len(self.always_runs)}):")
            for p in sorted(self.always_runs):
                agent_print(f"    {p}")
        if not self.auto_writes and not self.auto_run_prefixes and not self.always_writes and not self.always_runs:
            agent_print("  (no specific auto-approvals)")
        agent_print(f"  Config: {self._coder_config_path()}")
        agent_print()
