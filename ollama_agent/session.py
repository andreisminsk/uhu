"""ChatSession: the main interactive chat loop with agentic capabilities."""

import hashlib
import logging
import os
import queue as _queue
import sys
import threading
import time
from collections import Counter
from datetime import datetime

logger = logging.getLogger(__name__)

from ollama import Client

from .constants import AGENT_SYSTEM_PROMPT, MODEL_TEMPERATURE, get_platform_shell_guidance, get_platform_info, ANSI_LIGHT_GRAY, ANSI_AGENT, ANSI_RESET, MAX_IDENTICAL_ACTION_REPEATS, LOOP_NUDGE_THRESHOLD, RUN_COMMAND_CATEGORIES, MAX_CONSECUTIVE_EMPTY_RUN, MAX_FEEDBACK_ROUNDS
from .actions import agent_print, tool_print
from .parser import parse_actions
from .input_utils import read_full_input, _reconfigure_stdout
from . import input_utils as _iu
from .spinner import Spinner
from .commands import CommandMixin
from .actions import ActionMixin
from .persistence import PersistenceMixin


class ChatSession(CommandMixin, ActionMixin, PersistenceMixin):
    """Encapsulates all state and logic for an interactive Ollama chat session."""
    def __init__(self, host, model, ctx_size, stream=True, log_path=None,
                sessions_dir=None, agent=True, workdir=".", autosave=True,
                tools=True, skills=False, skills_dir="./.skills", cache_files=True,
                thinking=True, quiet=False, mcp=False):
        _reconfigure_stdout()
        self.quiet = quiet
        self.client = Client(host=host)
        self.model = model
        self.ctx_size = ctx_size
        self.stream = stream
        self.agent = agent
        self.tools = tools
        self.mcp = mcp
        self.skills = skills
        self.skills_dir = skills_dir
        self.workdir = os.path.abspath(workdir)
        self.autosave = autosave
        self.sessions_dir = sessions_dir or os.path.join(os.path.abspath(self.workdir), ".uhu", ".sessions")

        self.history = []
        self.pending_content = []
        self.pending_binaries = []
        self.auto_all = False
        self.auto_writes = set()
        self.auto_run_prefixes = set()
        self.always_writes = set()
        self.always_runs = set()
        self._skill_auto_approve = False
        self._active_skill = None
        self.show_diff = False
        self.cache_files = cache_files
        self.thinking = thinking
        self.autosave_name = None

        os.makedirs(self.sessions_dir, exist_ok=True)

        # Load persistent auto-approval settings from project config
        self._load_coder_config()

        if self.autosave:
            project_name = os.path.basename(self.workdir) or "session"
            self.autosave_name = f"{project_name}_{datetime.now().strftime('%Y%m%d_%H%M')}"

        if self.agent:
            system_prompt = AGENT_SYSTEM_PROMPT
            # Replace {shell_lang} placeholder with platform-appropriate shell
            info = get_platform_info()
            system_prompt = system_prompt.replace("{shell_lang}", info["shell_lang"])
            self.history.append({"role": "system", "content": system_prompt + get_platform_shell_guidance()})

        # Connect MCP servers and register their tools BEFORE building tools prompt
        if self.mcp:
            from .tools.mcp import MCPManager
            self._mcp_manager = MCPManager(workdir=self.workdir, quiet=self.quiet)
            mcp_tools = self._mcp_manager.load_and_connect()
            if mcp_tools:
                from .tools import register
                for tool in mcp_tools:
                    register(tool)
                    # Auto-approve MCP tools only if server is marked auto_approve
                    if getattr(tool, 'auto_approve', False):
                        self.always_runs.add(tool.name)
            agent_print(f"[MCP] {len(mcp_tools)} tool(s) registered from {len(self._mcp_manager.transports)} server(s)")

        if self.tools:
            from .tools import tools_system_prompt
            tool_prompt = tools_system_prompt()
            if self.history and self.history[0]["role"] == "system":
                self.history[0]["content"] += "\n\n" + tool_prompt
            else:
                self.history.insert(0, {"role": "system", "content": tool_prompt})

        if self.skills:
            from .skills import skills_system_prompt, load_skills_from_dir
            # Load user-defined skills from skills_dir
            skills_dir_abs = os.path.join(self.workdir, self.skills_dir) if not os.path.isabs(self.skills_dir) else self.skills_dir
            if os.path.isdir(skills_dir_abs):
                loaded, errors = load_skills_from_dir(skills_dir_abs, workdir=self.workdir)
                if loaded:
                    if not self.quiet:
                        agent_print(f"[Loaded {loaded} custom skill(s) from {self.skills_dir}]")
                if errors:
                    if not self.quiet:
                        for err in errors:
                            agent_print(f"[Skill load warning: {err}]")
                        agent_print()
                elif loaded:
                    if not self.quiet:
                        agent_print()
            skill_prompt = skills_system_prompt()
            if self.history and self.history[0]["role"] == "system":
                self.history[0]["content"] += "\n\n" + skill_prompt
            else:
                self.history.insert(0, {"role": "system", "content": skill_prompt})

    # Load permanent memory (project + agent) — all modes
        from .memory import build_memory_prompt
        mem_prompt, mem_warnings = build_memory_prompt(self.workdir)
        if mem_prompt:
            if self.history and self.history[0]["role"] == "system":
                self.history[0]["content"] += "\n\n" + mem_prompt
            else:
                self.history.insert(0, {"role": "system", "content": mem_prompt})
        if not self.quiet:
            for w in mem_warnings:
                agent_print(f"[⚠ {w}]")

        # Auto-create parent directory for log file
        if log_path:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
        self.log_file = open(log_path, "a", encoding="utf-8") if log_path else None
        if self.log_file:
            self.log_file.write(f"\n{'='*60}\n")
            self.log_file.write(
                f"Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
                f"model: {self.model} | ctx: {self.ctx_size} | agent: {self.agent}\n"
            )
            self.log_file.write(f"{'='*60}\n\n")
            self.log_file.flush()
        logger.info("Session started | model=%s | ctx=%d | agent=%s | stream=%s | tools=%s | skills=%s | thinking=%s",
                     self.model, self.ctx_size, self.agent, self.stream, self.tools, self.skills, self.thinking)

    def _log(self, role, content):
        if self.log_file:
            self.log_file.write(f"[{datetime.now().strftime('%H:%M:%S')}] {role.upper()}:\n{content}\n\n")
            self.log_file.flush()
        if role == "system":
            logger.debug("[%s] %s", role, content[:200])
        elif role in ("user", "assistant"):
            logger.debug("[%s] %s", role, content[:200])

    # Maximum response length in characters before truncating.
    # Prevents runaway repetitive output from consuming all context.
    # The model rarely needs more than ~30k chars; beyond that it's usually
    # stuck in a repetitive loop.
    # ── Model interaction ──────────────────────────────────────────────

    def _call_model(self):
        spinner = Spinner(prefix="AI: ")
        spinner.start()
        try:
            if self.stream:
                msg = ""
                eval_count = None
                first = True
                chunk_queue = _queue.Queue()
                stream_error = [None]
                # Holds the httpx response object so the main thread can call
                # response.close() on Ctrl+C, which immediately unblocks
                # iter_lines() in the reader thread. A threading.Event won't
                # work because the reader is blocked inside a C-level socket
                # read between yields — it never gets a chance to check a flag.
                active_response = [None]

                def _stream_reader():
                    try:
                        # Bypass the high-level client.chat() iterator so we can
                        # hold a reference to the raw httpx response for cancellation.
                        with self.client._client.stream(
                            "POST",
                            "/api/chat",
                            json={
                                "model": self.model,
                                "messages": self.history,
                                "stream": True,
                                "options": {"num_ctx": self.ctx_size, "temperature": MODEL_TEMPERATURE},
                            },
                        ) as response:
                            active_response[0] = response
                            response.raise_for_status()
                            import json as _json
                            for line in response.iter_lines():
                                if not line:
                                    continue
                                part = _json.loads(line)
                                logger.debug("Response chunk: %s", part)
                                if err := part.get("error"):
                                    from ollama import ResponseError
                                    raise ResponseError(err)
                                chunk_queue.put(part)
                    except Exception as e:
                        stream_error[0] = e
                    finally:
                        active_response[0] = None
                        chunk_queue.put(None)  # sentinel

                reader_thread = threading.Thread(target=_stream_reader, daemon=True)
                reader_thread.start()

                last_chunk_time = time.time()
                chunk_timeout = 180  # seconds with no chunks before giving up

                try:
                    while True:
                        try:
                            # Use get_nowait() + time.sleep() instead of get(timeout=...).
                            # On Windows, queue.get(timeout=N) calls Condition.wait() which
                            # uses WaitForSingleObjectEx -- a Win32 blocking wait that does
                            # NOT wake up for SIGINT. time.sleep() on Windows IS interruptible
                            # by SIGINT, so polling with get_nowait() + sleep is the correct
                            # Windows-compatible pattern.
                            chunk = chunk_queue.get_nowait()
                        except _queue.Empty:
                            if stream_error[0]:
                                spinner.stop()
                                raise stream_error[0]
                            if time.time() - last_chunk_time > chunk_timeout:
                                spinner.stop()
                                self._log("system", f"[Model streaming timeout — no response for {chunk_timeout}s]")
                                logger.warning("Model streaming timeout — no response for %ds", chunk_timeout)
                                agent_print(f"\n[Model streaming timeout — no response for {chunk_timeout}s]\n")
                                break
                            time.sleep(0.05)  # interruptible on Windows; yields for Ctrl+C
                            continue

                        if chunk is None:
                            if stream_error[0]:
                                spinner.stop()
                                raise stream_error[0]
                            break

                        last_chunk_time = time.time()
                        # Extract thinking content separately from regular content.
                        # Thinking tokens must NOT be mixed into the response content.
                        thinking_token = chunk.get("message", {}).get("thinking", "")
                        token = chunk.get("message", {}).get("content", "")
                        if thinking_token:
                            if self.thinking and spinner.is_running:
                                spinner.append_thinking(thinking_token)
                            logger.debug("Thinking token (%d chars)", len(thinking_token))
                            # Don't set first=False on thinking — content still needs "AI: " prefix
                        if token:
                            if first:
                                spinner.stop()
                                sys.stdout.write("AI: ")
                                sys.stdout.flush()
                                first = False
                            print(token, end="", flush=True)
                        msg += token
                        if chunk.get("done"):
                            eval_count = chunk.get("prompt_eval_count")
                except KeyboardInterrupt:
                    logger.debug("Streaming interrupted by user (Ctrl+C)")
                    # Close the HTTP response — this is the only reliable way to
                    # unblock iter_lines() in the reader thread immediately.
                    resp = active_response[0]
                    if resp is not None:
                        try:
                            resp.close()
                        except Exception:
                            pass
                    spinner.stop()
                    raise

                if first:
                    spinner.stop()
                    sys.stdout.write("AI: ")
                    sys.stdout.flush()
                print("\n")
                return msg, eval_count
            else:
                result_holder = [None]
                error_holder = [None]
                # Timeout for non-streaming model calls (seconds).
                # Prevents hanging forever if the model never responds.
                model_timeout = 600  # 10 minutes
                # Use an Event instead of thread.join() so Ctrl+C works on Windows.
                # thread.join(timeout) is NOT reliably interruptible by
                # KeyboardInterrupt on Windows, but Event.wait(timeout) is.
                done_event = threading.Event()

                def _blocking_call():
                    try:
                        result_holder[0] = self.client.chat(
                            model=self.model, messages=self.history,
                            options={"num_ctx": self.ctx_size, "temperature": MODEL_TEMPERATURE}
                        )
                    except Exception as e:
                        error_holder[0] = e
                    finally:
                        done_event.set()

                call_thread = threading.Thread(target=_blocking_call, daemon=True)
                call_thread.start()
                start_time = time.time()

                try:
                    while not done_event.wait(timeout=0.5):
                        if time.time() - start_time > model_timeout:
                            spinner.stop()
                            raise TimeoutError(
                                f"Model call timed out after {model_timeout}s — "
                                f"no response received. Try /compact to reduce context, "
                                f"or restart the session."
                            )
                except KeyboardInterrupt:
                    spinner.stop()
                    raise

                if error_holder[0]:
                    spinner.stop()
                    raise error_holder[0]

                response = result_holder[0]
                spinner.stop()
                # Extract thinking content separately from regular content.
                # Thinking must NOT be mixed into the response content.
                thinking_content = response["message"].get("thinking", "")
                msg = response["message"]["content"]
                if thinking_content:
                    # Placeholder: skip thinking content for now
                    logger.debug("Thinking content skipped (%d chars)", len(thinking_content))
                eval_count = response.get("prompt_eval_count")
                logger.debug("Non-streaming response received | eval_count=%s | len=%d", eval_count, len(msg))
                sys.stdout.write("AI: ")
                sys.stdout.flush()
                print(f"{msg}\n")
                return msg, eval_count
        except Exception:
            spinner.stop()
            logger.exception("Model call failed")
            raise

    def _build_message(self, user_input):
        parts = self.pending_content[:]
        self.pending_content.clear()
        self.pending_binaries.clear()
        if user_input:
            parts.append(user_input)
        return "\n\n".join(parts)
    # Phrases that suggest the model intends to act but didn't produce action blocks
    _INTENT_PHRASES = (
        "let me ", "i'll ", "i will ", "i should ", "first, i", "first i",
        "i need to", "i want to", "let's ", "i can ", "going to ",
        "i'm going to", "i would ", "next, i", "now i'll", "now i will",
        "step 1", "step one", "first step",
    )

    def _nudge_if_stuck(self, response_text, had_actions):
        """If the model's response suggests intent to act but produced no actions,
        return a nudge message. Otherwise return None."""
        if had_actions:
            return None
        lower = response_text.lower().strip()
        # Check if the response is short and contains intent phrases
        if len(response_text) < 500:
            for phrase in self._INTENT_PHRASES:
                if phrase in lower:
                    return (
                        "[System: You described what you plan to do but didn't produce any "
                        "action blocks. Use **WRITE:**, **EDIT:**, **FILE:**, **RUN:**, or "
                        "**TOOL:** blocks to actually perform actions. Don't just describe "
                        "your intent — take action now.]"
                    )
        return None

    @staticmethod
    def _classify_run_command(cmd):
        """Classify a RUN command into a category for broader loop detection.

        Returns a category string like 'file_listing', 'file_reading', etc.
        or None if the command doesn't fit any known category.
        """
        base = cmd.split()[0].lower().strip('"').strip("'")
        # Strip common extensions
        for ext in ('.exe', '.cmd', '.bat', '.com'):
            if base.endswith(ext):
                base = base[:-len(ext)]
        for category, commands in RUN_COMMAND_CATEGORIES.items():
            if base in commands:
                return category
        return None

    def _action_signature(self, action):
        """Compute a hashable signature for an action to detect loops.

        Returns a tuple identifying the action type and key content.
        Two actions with the same signature are considered identical for
        loop detection purposes. Returns None for unidentifiable actions.

        For RUN commands, similar commands in the same category (e.g., all
        file-listing commands like 'dir', 'ls', 'Get-ChildItem') are grouped
        together so that running 'dir' then 'dir /b' then 'Get-ChildItem'
        counts as repeating the same category of action.
        """
        atype = action.get("type")
        if atype == "run":
            cmd = action.get("code", "").strip()
            if not cmd:
                return None
            # Normalize whitespace for comparison
            cmd = " ".join(cmd.split())
            # Group similar commands by category for broader loop detection
            category = self._classify_run_command(cmd)
            if category:
                return ("run_category", category)
            return ("run", cmd)
        elif atype in ("write", "edit"):
            path = action.get("path", "").strip()
            if not path:
                return None
            content = action.get("code", "")
            content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
            return (atype, path, content_hash)
        elif atype == "read":
            path = action.get("path", "").strip()
            if not path:
                return None
            return ("read", path)
        elif atype in ("tool", "skill"):
            name = action.get("name", "").strip()
            if not name:
                return None
            return (atype, name)
        return None

    def _check_context_pressure(self):
        """Check context usage and take action if needed.

        - At 85%: print a strong warning suggesting /compact
        - At 95%: auto-compact to prevent context overflow

        Returns True if context is OK, False if auto-compaction was performed.
        """
        total_tokens = int(sum(len(m["content"]) / 4 for m in self.history))
        pct = total_tokens / self.ctx_size * 100

        if pct >= 95:
            logger.warning("Context at %d%% — auto-compacting", int(pct))
            agent_print(f"\n[\u26a0 Context at {pct:.0f}% \u2014 auto-compacting to prevent overflow]\n")
            self.do_compact()
            return False
        elif pct >= 85:
            logger.warning("Context at %d%% — consider /compact", int(pct))
            agent_print(f"\n[\u26a0 Context at {pct:.0f}% \u2014 consider /compact to free up space]\n")
        return True

    def _feedback_loop(self, max_rounds=3):
        """Iteratively process actions and call the model for feedback.

        Starts from the last assistant message in history. Up to max_rounds
        feedback iterations are made.

        Read-only rounds (FILE: blocks) now continue the loop so the model
        can act on what it read — previously the loop stopped immediately,
        forcing the user to re-prompt while the model went in circles
        reading without ever making changes.

        A consecutive read-only limit (3) prevents infinite read loops.
        When the model has been reading but not acting, a nudge is added
        to encourage it to proceed with edits/writes.

        Loop detection tracks action signatures across rounds. If the same
        action is repeated LOOP_NUDGE_THRESHOLD times, a warning nudge is
        added. If repeated MAX_IDENTICAL_ACTION_REPEATS times, execution is
        skipped and a strong nudge forces the model to try a different
        approach. This prevents the model from running the same failed
        command or reading the same file over and over.

        When a skill is approved by the user, subsequent WRITE/EDIT/RUN
        actions in the same _send() call are auto-approved via
        _skill_auto_approve (the user has already consented to the skill's
        workflow). The flag is set in execute_skill and cleared in _send's
        finally block.
        """
        consecutive_read_only = 0
        max_consecutive_read_only = 3
        action_sig_rounds = {}  # sig -> number of rounds this signature appeared in
        for round_num in range(max_rounds):
            assistant_msg = self.history[-1]["content"]
            round_label = f"Round {round_num + 1}/{max_rounds}"

            # Pre-parse actions to detect loops before executing them
            pre_actions = parse_actions(assistant_msg)
            current_sigs = set()
            for a in pre_actions:
                sig = self._action_signature(a)
                if sig is not None:
                    current_sigs.add(sig)

            # Check for loops: how many rounds has each signature been seen?
            loop_nudge = None
            skip_execution = False
            for sig in current_sigs:
                rounds_seen = action_sig_rounds.get(sig, 0) + 1
                if rounds_seen >= MAX_IDENTICAL_ACTION_REPEATS:
                    skip_execution = True
                    loop_nudge = (
                        f"⚠️ LOOP DETECTED: You have repeated the same {sig[0]} action "
                        f"{rounds_seen} times across rounds. The action will NOT be executed. "
                        f"STOP repeating and try a DIFFERENT approach. "
                        f"If a RUN command keeps failing, use FILE: to read files instead. "
                        f"If an EDIT keeps failing, re-read the file with FILE: first."
                    )
                    break
                elif rounds_seen >= LOOP_NUDGE_THRESHOLD:
                    if loop_nudge is None:
                        loop_nudge = (
                            f"⚠️ WARNING: You have repeated the same {sig[0]} action "
                            f"{rounds_seen} times. Consider trying a different approach."
                        )

            # Update round counts for current signatures
            for sig in current_sigs:
                action_sig_rounds[sig] = action_sig_rounds.get(sig, 0) + 1

            if skip_execution:
                logger.warning("Loop detected — skipping execution | sig=%s | rounds=%d", sig, rounds_seen)
                # Don't execute — just add the loop nudge and call model again
                agent_print(loop_nudge + "\n")
                self._log("system", loop_nudge)
                self.history.append({"role": "user", "content": loop_nudge})
                try:
                    agent_print()
                    feedback_msg, fb_eval_count = self._call_model()
                    self._log("assistant", feedback_msg)
                    self.history.append({"role": "assistant", "content": feedback_msg})
                    self.show_ctx(fb_eval_count)
                except KeyboardInterrupt:
                    self._log("system", "[Loop nudge interrupted by user]")
                    agent_print("\n[Loop nudge interrupted]\n")
                    self.history.append({"role": "assistant", "content": "Noted."})
                    return
                except Exception as e:
                    self._log("system", f"[Loop nudge error: {e}]")
                    agent_print(f"\n[Loop nudge error: {e}]\n")
                    self.history.append({"role": "assistant", "content": "Noted."})
                    return
                continue

            # Execute actions normally
            obs, cancelled_run, has_non_read, has_skill = self.process_actions(assistant_msg)

            # Add loop nudge to observation if at warning level
            if loop_nudge and obs:
                obs += "\n" + loop_nudge

            if not obs:
                # No actions produced — check if model seems stuck and nudge
                is_last_round = (round_num == max_rounds - 1)
                nudge = self._nudge_if_stuck(assistant_msg, had_actions=False)
                if nudge and not is_last_round:
                    # Not the last round — nudge the model to act
                    agent_print(nudge + "\n")
                    self._log("system", nudge)
                    self.history.append({"role": "user", "content": nudge})
                    try:
                        agent_print(f"⟳ {round_label} — nudging model...")
                        feedback_msg, fb_eval_count = self._call_model()
                        self._log("assistant", feedback_msg)
                        self.history.append({"role": "assistant", "content": feedback_msg})
                        self.show_ctx(fb_eval_count)
                        # Process the nudged response
                        continue
                    except KeyboardInterrupt:
                        self._log("system", "[Nudge interrupted by user]")
                        agent_print("\n[Nudge interrupted]\n")
                        self.history.append({"role": "assistant", "content": "Noted."})
                        return
                    except Exception as e:
                        self._log("system", f"[Nudge error: {e}]")
                        agent_print(f"\n[Nudge error: {e}]\n")
                        self.history.append({"role": "assistant", "content": "Noted."})
                        return
                if is_last_round and nudge:
                    # Model is stuck on last round — skip to max rounds message
                    continue
                else:
                    agent_print("✓ Done — no more actions\n")
                    return
            self._log("system", obs)
            self.history.append({"role": "user", "content": obs})
            if cancelled_run:
                self.history.append({"role": "assistant", "content": "Noted."})
                agent_print("⊘ Cancelled\n")
                return
            if not has_non_read and not has_skill:
                consecutive_read_only += 1
                if consecutive_read_only >= max_consecutive_read_only:
                    # Too many consecutive read-only rounds — stop and nudge
                    self.history.append({"role": "assistant", "content": "Noted."})
                    agent_print(f"⚠  Stopped after {consecutive_read_only} read-only rounds\n")
                    return
                # Read-only observations — call model again so it can act on what it read
                agent_print(f"⟳ {round_label} (reading) — model is gathering information...\n")
                # Add a nudge if the model has been reading without acting
                if consecutive_read_only >= 2:
                    nudge = (
                        "[System: You have read files but not made any changes yet. "
                        "If you have enough information, proceed with WRITE/EDIT/RUN actions now. "
                        "If you need more files, read them, but aim to act soon.]"
                    )
                    self.history[-1]["content"] += "\n" + nudge
            else:
                consecutive_read_only = 0
                agent_print(f"⟳ {round_label} — model continuing...\n")
            # Call model for feedback (whether read-only or not)
            self._check_context_pressure()
            try:
                agent_print()
                feedback_msg, fb_eval_count = self._call_model()
                self._log("assistant", feedback_msg)
                self.history.append({"role": "assistant", "content": feedback_msg})
                self.show_ctx(fb_eval_count)
            except KeyboardInterrupt:
                self._log("system", "[Feedback interrupted by user]")
                agent_print("\n[Feedback interrupted]\n")
                self.history.append({"role": "assistant", "content": "Noted."})
                return
            except Exception as e:
                self._log("system", f"[Feedback error: {e}]")
                agent_print(f"\n[Feedback error: {e}]\n")
                self.history.append({"role": "assistant", "content": "Noted."})
                return
        # Exhausted max rounds — process any remaining actions but don't call model again
        assistant_msg = self.history[-1]["content"]
        obs, _, _, _ = self.process_actions(assistant_msg)
        if obs:
            self._log("system", obs)
            self.history.append({"role": "user", "content": obs})
        self.history.append({"role": "assistant", "content": "Noted."})
        agent_print(f"⚠  Max feedback rounds ({max_rounds}) reached — send a message to continue\n")

    def _send(self, message, max_rounds=MAX_FEEDBACK_ROUNDS):
        self._log("user", message)
        self.history.append({"role": "user", "content": message})
        history_len_before = len(self.history)
        # When skills mode is active, auto-approve all actions — the user has
        # opted into the skill's workflow by enabling --skills
        try:
            agent_print()
            assistant_msg, prompt_eval_count = self._call_model()
            self._log("assistant", assistant_msg)
            self.history.append({"role": "assistant", "content": assistant_msg})
            self.show_ctx(prompt_eval_count)
            self._check_context_pressure()
            self._feedback_loop(max_rounds=max_rounds)
            if self.autosave and self.autosave_name:
                self._do_autosave()
        except KeyboardInterrupt:
            self._log("system", "[Interrupted by user]")
            logger.info("User interrupted _send (Ctrl+C)")
            agent_print("\n[Interrupted]\n")
            while len(self.history) > history_len_before:
                self.history.pop()
        except Exception as e:
            self._log("system", f"[Error: {e}]")
            logger.exception("Error in _send: %s", e)
            agent_print(f"\n[Error: {e}]\n")
            while len(self.history) > history_len_before:
                self.history.pop()
        finally:
            # _skill_auto_approve persists across continuation messages.
            # It is reset in run() for new substantive user messages.
            pass

    # ── One-shot mode ────────────────────────────────────────────────────

    def run_once(self, prompt):
        """Execute a single prompt with full feedback loop and exit.

        One-shot mode: auto-approves all actions, runs the feedback loop,
        then exits. No interactive input needed.
        """
        # Auto-approve all actions for non-interactive mode
        self.auto_all = True
        self._send(prompt, max_rounds=7)

    # ── Main loop ──────────────────────────────────────────────────────

    def run(self):
        """Main interactive loop."""
        info = get_platform_info()
        agent_print(f"Connected to {self.client._client.base_url} | Model: {self.model} | "
              f"Context: {self.ctx_size} | Stream: {self.stream} | Agent: {self.agent} | "
              f"Tools: {self.tools} | Skills: {self.skills} | Thinking: {self.thinking} | "
              f"Cache: {self.cache_files} | Autosave: {self.autosave}")
        agent_print(f"Platform: {info['platform_label']} | Shell: {info['shell_label']}")
        if self.agent:
            agent_print(f"Workdir: {self.workdir}")
        if self.log_file:
            agent_print(f"Logging to: {self.log_file.name}")
        agent_print("Type /help for available commands.\n")

        try:
            while True:
                try:
                    user_input = read_full_input("You: ", multiline=True, color=ANSI_LIGHT_GRAY).strip()
                    if user_input:
                        logger.debug("User input: %s", user_input[:100])
                except (KeyboardInterrupt, EOFError):
                    if not self.autosave:
                        msgs = [m for m in self.history if m["role"] != "system"]
                        if msgs:
                            agent_print("\n[Session not saved — use /save before exiting]")
                    agent_print("\nBye.")
                    break
                except UnicodeEncodeError as e:
                    agent_print(f"\n[Input encoding error: {e}]")
                    agent_print("[If this involved emoji or special characters, try pasting without them or use /attach]\n")
                    continue
                except Exception as e:
                    agent_print(f"\n[Input error: {type(e).__name__}: {e}]")
                    continue
                if not user_input:
                    if self.pending_content:
                        self._send(self._build_message(""))
                    continue
                if user_input.count("\n") >= 1 and _iu._last_input_was_paste:
                    line_count = user_input.count("\n") + 1
                    if sys.platform != "win32":
                        for _ in range(line_count):
                            sys.stdout.write("\033[A\033[2K")
                        sys.stdout.write("\r")
                        sys.stdout.flush()
                    else:
                        sys.stdout.write("\033[A\033[2K\rYou: ")
                        sys.stdout.flush()
                    # Sanitize pasted text to prevent UnicodeEncodeError
                    # from lone surrogates (can happen with msvcrt.getwch()
                    # on Windows for non-BMP characters like emoji)
                    try:
                        user_input.encode('utf-8')
                    except UnicodeEncodeError:
                        user_input = user_input.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
                        agent_print("[Note: Some characters were replaced due to encoding issues]\n")
                    self.pending_content.append(f"[Pasted text ({line_count} lines)]\n{user_input}")
                    agent_print(f"[Pasted text ({line_count} lines)]\n")
                    continue
                if user_input.lower() in ("exit", "/exit", "/bye", "bye"):
                    logger.info("Session ending (user exit)")
                    if not self.autosave:
                        msgs = [m for m in self.history if m["role"] != "system"]
                        if msgs:
                            try:
                                ans = read_full_input("Exit without saving? (y/N): ").strip().lower()
                            except (KeyboardInterrupt, EOFError):
                                ans = "y"
                            if ans != "y":
                                agent_print("[Cancelled — use /save to save first]\n")
                                continue
                    agent_print("Bye.")
                    break
                if user_input.lower() in ("reset", "/reset"):
                    sys_msgs = [m for m in self.history if m["role"] == "system"]
                    self.history.clear()
                    self.history.extend(sys_msgs)
                    self.pending_content.clear()
                    self._log("system", "[reset]")
                    agent_print("[Context cleared]\n")
                    continue
                if user_input.lower() in ("history", "/history"):
                    self.show_ctx()
                    continue
                if user_input.lower() == "/compact" or user_input.lower().startswith("/compact "):
                    self.do_compact(user_input[8:].strip())
                    self.do_sober()
                    continue
                if user_input.lower() in ("/v", "/ver", "/version"):
                    self.do_version()
                    continue
                if user_input.lower() == "/sober":
                    self.do_sober()
                    continue
                if user_input.lower().startswith("/auto"):
                    self.do_auto(user_input[5:])
                    continue
                if user_input.lower() == "/diff":
                    self.show_diff = not self.show_diff
                    agent_print(f"[Diff display: {'ON' if self.show_diff else 'OFF'}]\n")
                    continue
                if user_input.lower().startswith("/memorize"):
                    self.do_memorize(user_input[9:].strip())
                    continue
                if user_input.lower() == "/help":
                    self.do_help()
                    continue
                if user_input.lower() in ("/m", "/multiline"):
                    ml_text = self.do_multiline()
                    if ml_text:
                        self._send(self._build_message(ml_text))
                    continue
                if user_input.lower().startswith("/attach-bin"):
                    self.do_attach_bin(user_input[11:])
                    continue
                if user_input.lower().startswith("/attach"):
                    self.do_attach(user_input[7:])
                    continue
                if user_input.lower().startswith("/search"):
                    self.do_search(user_input[7:])
                    continue
                if user_input.lower().startswith("/peek"):
                    self.do_peek(user_input[5:])
                    continue
                if user_input.lower().startswith("/ls"):
                    self.do_ls(user_input[3:])
                    continue
                if user_input.lower().startswith("/md"):
                    self.do_md(user_input[3:])
                    continue
                if user_input.lower().startswith("/save"):
                    self.do_save(user_input[5:])
                    continue
                if user_input.lower().startswith("/restore"):
                    self.do_restore(user_input[8:])
                    continue
                if user_input.lower() == "/sessions":
                    self.do_sessions()
                    continue
                if user_input.lower() == "/skills":
                    self.do_skills()
                    continue
                # Reset skill auto-approve for new substantive user messages.
                # Short continuations like "?" after max feedback rounds keep the flag.
                if len(user_input.strip()) > 2:
                    self._skill_auto_approve = False
                    self._active_skill = None
                self._send(self._build_message(user_input))
        finally:
            if self.log_file:
                self.log_file.close()
            logger.info("Session ended")
