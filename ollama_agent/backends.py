"""LLM Backend Abstraction Layer.

Provides unified interface for different LLM APIs:
- OllamaNativeBackend: Uses ollama.Client with /api/chat endpoint
- OpenAIBackend: Uses openai.Client with /v1/chat/completions endpoint

Optional components (OpenAI-compatible only, None for Ollama):
- TokenCounter: tiktoken-based token counting with char/4 fallback
- HistoryTrimmer: client-side context trimming with summarization
- RetryHandler: jittered exponential backoff for transient errors
- TPMTracker: proactive tokens-per-minute throttling (--tpm only)
"""

import os
import sys
import json
import logging
import queue as _queue
import random
import threading
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional, Any

from .constants import MODEL_TEMPERATURE, ANSI_AI, ANSI_AI_DIM, ANSI_RESET
from .display import agent_print
from .spinner import Spinner
from .tool_calls import merge_tool_call_fragments, normalize_tool_calls

logger = logging.getLogger(__name__)


def _ai_color_on():
    """Start AI response color (#00FF00) when stdout is a TTY."""
    if sys.stdout.isatty():
        sys.stdout.write(ANSI_AI)


def _ai_color_off():
    """Reset AI response color when stdout is a TTY."""
    if sys.stdout.isatty():
        sys.stdout.write(ANSI_RESET)


# ── Token Counter ─────────────────────────────────────────────────────

class TokenCounter:
    """Counts tokens using tiktoken, with graceful fallback to char/4 heuristic."""

    def __init__(self, model: str, per_message_overhead: int = 4):
        self._encoder = None
        self.per_message_overhead = per_message_overhead
        try:
            import tiktoken
            self._encoder = tiktoken.encoding_for_model(model)
        except Exception:
            try:
                import tiktoken
                self._encoder = tiktoken.get_encoding("cl100k_base")
            except Exception:
                pass  # Fallback to heuristic

    def count(self, messages: List[Dict]) -> int:
        """Count tokens in message list. Falls back to char/4 heuristic."""
        if self._encoder:
            total = 0
            for msg in messages:
                content = msg.get("content", "")
                if isinstance(content, str):
                    total += len(self._encoder.encode(content))
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and "text" in part:
                            total += len(self._encoder.encode(part["text"]))
                total += self.per_message_overhead
            return total
        return sum(len(str(m.get("content", ""))) for m in messages) // 4

    def count_message(self, msg: Dict) -> int:
        """Count tokens in a single message."""
        return self.count([msg])


# ── TPM Tracker ───────────────────────────────────────────────────────

class TPMTracker:
    """Tracks tokens-per-minute usage to proactively throttle requests.

    Maintains a rolling 60-second window of token usage. Before sending,
    checks if the request would exceed the TPM budget. If so, waits until
    the window clears — transforming 429 errors into planned waits.
    """

    def __init__(self, tpm_limit: int, quiet: bool = False):
        self.tpm_limit = tpm_limit
        self.quiet = quiet
        self._usage_log: List[Tuple[float, int]] = []

    def _prune(self, now: float):
        """Remove entries older than 60 seconds."""
        cutoff = now - 60.0
        self._usage_log = [(t, c) for t, c in self._usage_log if t > cutoff]

    def _current_usage(self) -> int:
        """Return total tokens used in the last 60 seconds."""
        now = time.time()
        self._prune(now)
        return sum(c for _, c in self._usage_log)

    def wait_if_needed(self, estimated_tokens: int):
        """Block until sending estimated_tokens won't exceed TPM limit.

        If a single request exceeds the TPM limit, waiting is pointless —
        just send it and let the retry handler deal with any 429.
        """
        # Single request bigger than entire TPM budget — don't wait forever
        if estimated_tokens >= self.tpm_limit:
            return
        while True:
            current = self._current_usage()
            if current + estimated_tokens <= self.tpm_limit:
                return
            now = time.time()
            if self._usage_log:
                oldest_time = self._usage_log[0][0]
                wait_seconds = max(1, oldest_time + 60.0 - now)
            else:
                wait_seconds = 1
            if not self.quiet:
                agent_print(
                    f"\n[TPM limit: {current}/{self.tpm_limit} tokens used in the last 60s. "
                    f"Sending the next prompt (~{estimated_tokens} tokens) would exceed the limit — "
                    f"waiting {wait_seconds:.0f}s for budget to clear...]\n"
                )
            time.sleep(min(wait_seconds, 60))

    def record_usage(self, tokens: int):
        """Record actual token usage after a successful request."""
        self._usage_log.append((time.time(), tokens))


# ── History Trimmer ───────────────────────────────────────────────────

class HistoryTrimmer:
    """Trims conversation history to fit within a token budget.

    Uses summarization for dropped messages to preserve context anchors.
    Preserves tool-call/result pairs to avoid API rejection.
    """

    def __init__(self, token_counter: TokenCounter, max_tokens: int,
                 reserve_output: int = 2048):
        self.counter = token_counter
        self.max_tokens = max_tokens
        self.reserve_output = reserve_output

    @property
    def input_budget(self) -> int:
        return self.max_tokens - self.reserve_output

    def trim(self, messages: List[Dict]) -> List[Dict]:
        """Trim messages to fit within input_budget."""
        if not messages:
            return messages
        total = self.counter.count(messages)
        if total <= self.input_budget:
            return messages
        if len(messages) <= 2:
            return messages

        system_msg = messages[0]
        last_msg = messages[-1]
        middle = messages[1:-1]
        groups = self._group_tool_pairs(middle)

        dropped_summaries: List[str] = []
        while groups and self.counter.count(
            [system_msg] + self._flatten(groups) + [last_msg]
        ) > self.input_budget:
            group = groups.pop(0)
            dropped_summaries.append(self._summarize_group(group))

        result = [system_msg]
        if dropped_summaries:
            result.append({
                "role": "system",
                "content": f"[Earlier conversation trimmed — {len(dropped_summaries)} message(s) dropped: "
                           + "; ".join(dropped_summaries) + "]"
            })
        result += self._flatten(groups)
        result.append(last_msg)

        final_count = self.counter.count(result)
        if final_count > self.input_budget:
            overflow = final_count - self.input_budget
            if isinstance(last_msg.get("content"), str):
                content = last_msg["content"]
                keep_chars = max(100, len(content) - overflow * 4)
                result[-1] = dict(last_msg)
                result[-1]["content"] = content[:keep_chars] + "\n[... truncated to fit context limit ...]"

        return result

    def _group_tool_pairs(self, messages: List[Dict]) -> List[List[Dict]]:
        """Group tool-call and tool-result messages for atomic trimming."""
        groups = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            role = msg.get("role", "")
            if role == "assistant" and msg.get("tool_calls"):
                group = [msg]
                i += 1
                while i < len(messages) and messages[i].get("role") == "tool":
                    group.append(messages[i])
                    i += 1
                groups.append(group)
            else:
                groups.append([msg])
                i += 1
        return groups

    def _flatten(self, groups: List[List[Dict]]) -> List[Dict]:
        return [msg for group in groups for msg in group]

    def _summarize_group(self, group: List[Dict]) -> str:
        parts = []
        for msg in group:
            role = msg.get("role", "?")
            content = str(msg.get("content", ""))
            parts.append(f"{role}: {content[:80]}")
        return " | ".join(parts)


# ── Retry Handler ─────────────────────────────────────────────────────

class RetryHandler:
    """Retry on rate limits and connection errors with jittered backoff."""

    def __init__(self, triggers=None, initial_wait=20, max_wait=60,
                 max_retries=3, quiet=False):
        self.triggers = triggers or ["429", "rate_limit", "connection"]
        self.initial_wait = initial_wait
        self.max_wait = max_wait
        self.max_retries = max_retries
        self.quiet = quiet

    def _is_retryable(self, error: Exception) -> bool:
        err_str = str(error).lower()
        return any(t in err_str for t in self.triggers)

    def _extract_retry_after(self, error: Exception) -> Optional[float]:
        """Try to extract Retry-After header value from error."""
        try:
            if hasattr(error, 'response') and hasattr(error.response, 'headers'):
                retry_after = error.response.headers.get('retry-after')
                if retry_after:
                    try:
                        return float(retry_after)
                    except ValueError:
                        from email.utils import parsedate_to_datetime
                        from datetime import datetime, timezone
                        dt = parsedate_to_datetime(retry_after)
                        if dt:
                            return max(0, (dt - datetime.now(timezone.utc)).total_seconds())
        except Exception:
            pass
        return None

    def _cancellable_sleep(self, seconds: float):
        """Sleep with periodic status updates and Ctrl+C responsiveness."""
        for elapsed in range(int(seconds)):
            time.sleep(1)
            if not self.quiet and elapsed > 0 and elapsed % 5 == 0:
                agent_print(f"  Waiting... {int(seconds) - elapsed}s remaining\n")

    def execute(self, func, *args, **kwargs):
        """Execute func with retry. Returns result or raises."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if not self._is_retryable(e) or attempt == self.max_retries:
                    raise
                wait = min(self.initial_wait * (2 ** attempt), self.max_wait)
                wait += random.uniform(0, 2)
                retry_after = self._extract_retry_after(e)
                if retry_after is not None:
                    wait = max(wait, retry_after)
                if not self.quiet:
                    agent_print(
                        f"\n[Retryable error. Waiting {wait:.0f}s before retry "
                        f"({attempt + 1}/{self.max_retries})...]\n"
                    )
                self._cancellable_sleep(wait)
                last_error = e
        raise last_error


class LLMBackend(ABC):
    """Abstract base class for LLM API backends.

    All rate-limiting and context-management components are Optional and
    default to None. Backends opt in only to the components they need.
    Ollama leaves all as None — zero overhead, existing behavior preserved.
    """

    def __init__(self):
        self._token_counter: Optional[TokenCounter] = None
        self._trimmer: Optional[HistoryTrimmer] = None
        self._retry: Optional[RetryHandler] = None
        self._tpm_tracker: Optional[TPMTracker] = None
        # Cached-token (KV-cache) stats from the last call, if reported by the API
        self.last_cached_tokens: Optional[int] = None
        # Output tokens generated by the last call, if reported by the API
        # (Ollama: eval_count; OpenAI: usage.completion_tokens)
        self.last_output_tokens: Optional[int] = None
        # Reasoning tokens within the last call's output, if reported by the API
        # (OpenAI: usage.completion_tokens_details.reasoning_tokens; Ollama: not exposed)
        self.last_reasoning_tokens: Optional[int] = None
        # Native tool_calls from the last call, normalized to [{"name", "params"}]
        # (Phase 2, NATIVE-TOOL-CALLS-ARCH). Empty list when the model didn't
        # use the structured tool_calls channel. Content contract unchanged.
        self.last_tool_calls: List[Dict] = []
        # Chars of thinking actually surfaced by this backend in the last call
        # (display or structured capture). Session uses it to distinguish
        # "tokens went to shown thinking" from "tokens vanished invisibly".
        self.last_thinking_chars: int = 0
        # Instance-level timeout overrides (shadow the class constants).
        # The /timeout command can adjust these for the current session only;
        # the class constants remain the defaults for /timeout reset.
        self.STREAM_CHUNK_TIMEOUT = self.STREAM_CHUNK_TIMEOUT
        self.NON_STREAM_TIMEOUT = self.NON_STREAM_TIMEOUT

    def call(self, messages: List[Dict], stream: bool = True) -> Tuple[str, Optional[int]]:
        """Common call flow. Components activate only if configured.

        For Ollama (all components None), this is a direct passthrough
        to _call() with zero overhead.
        """
        # Reset cached-token and output-token stats from any previous call
        self.last_cached_tokens = None
        self.last_output_tokens = None
        self.last_reasoning_tokens = None
        self.last_tool_calls = []
        self.last_thinking_chars = 0
        # 1. TPM check (only if --tpm is set)
        if self._tpm_tracker and self._token_counter:
            estimated = self._token_counter.count(messages)
            self._tpm_tracker.wait_if_needed(estimated)

        # 2. Trim history (all OpenAI-compatible backends)
        trimmed = self._trimmer.trim(messages) if self._trimmer else messages

        # Log token usage if counter is configured
        final = None
        if self._token_counter and self._trimmer:
            original = self._token_counter.count(messages)
            final = self._token_counter.count(trimmed)
            if original != final:
                logger.info("History trimmed: %d → %d tokens", original, final)

        # 3. Execute with retry or direct call
        if self._retry:
            result = self._retry.execute(self._call, trimmed, stream=stream)
        else:
            result = self._call(trimmed, stream=stream)

        # 4. Record TPM usage (only if --tpm is set)
        if self._tpm_tracker and final is not None:
            self._tpm_tracker.record_usage(final)

        return result

    @abstractmethod
    def _call(self, messages: List[Dict], stream: bool = True) -> Tuple[str, Optional[int]]:
        """Backend-specific API call (streaming or blocking)."""
        pass

    @abstractmethod
    def supports_thinking(self) -> bool:
        """Return True if this backend supports thinking/reasoning tokens."""
        pass


class OllamaNativeBackend(LLMBackend):
    """Native Ollama API backend using ollama.Client."""
    
    STREAM_CHUNK_TIMEOUT = 180
    NON_STREAM_TIMEOUT = 600
    
    def __init__(self, host: str, model: str, ctx_size: int, thinking: bool = True,
                 temperature: Optional[float] = None, think_level: Optional[str] = None,
                 top_p: Optional[float] = None):
        super().__init__()
        from ollama import Client
        self.client = Client(host=host)
        self.model = model
        self.ctx_size = ctx_size
        self.thinking = thinking
        # Sampling temperature — None → MODEL_TEMPERATURE (0.0, greedy decoding default)
        self.temperature = temperature if temperature is not None else MODEL_TEMPERATURE
        # Top-p (nucleus) sampling — None = don't send the option (model default)
        self.top_p = top_p
        # Thinking effort — None = omit the param (model default). "off" →
        # think: False; otherwise sent as-is ("low"/"high"/"max" for models
        # with levels). Unsupported names resolve to the model default server-side.
        self.think_level = think_level
        self._apply_cache_stats_patch()
    
    @staticmethod
    def _apply_cache_stats_patch():
        """Make ollama's pydantic ChatResponse/Message keep unknown fields.

        The ollama library declares ChatResponse with extra='ignore', which
        silently drops prompt_eval_cached_count (KV-cache hits) returned by
        /api/chat. Switching to extra='allow' preserves it in model_extra.
        Message is patched the same way so native message.tool_calls survive
        ollama versions where the typed model would drop them.
        See dev-docs/CACHE-STATS.md, dev-docs/NATIVE-TOOL-CALLS-ARCH.md.
        """
        try:
            from ollama._types import ChatResponse, Message
            if ChatResponse.model_config.get("extra") != "allow":
                ChatResponse.model_config["extra"] = "allow"
                ChatResponse.model_rebuild(force=True)
            if Message.model_config.get("extra") != "allow":
                Message.model_config["extra"] = "allow"
                Message.model_rebuild(force=True)
        except Exception as e:
            logger.debug("Cache-stats patch not applied: %s", e)
    
    def _build_options(self) -> Dict[str, Any]:
        opts = {"num_ctx": self.ctx_size, "temperature": self.temperature}
        if self.top_p is not None:
            opts["top_p"] = self.top_p
        return opts

    def _think_param(self):
        """Top-level think param for /api/chat. None = omit → model default."""
        if self.think_level is None:
            return None
        return False if self.think_level.lower() == "off" else self.think_level.lower()
    
    @staticmethod
    def _wire_tool_results(messages: List[Dict]) -> List[Dict]:
        """Wire-boundary fix for the native function-calling protocol (400).

        Field-found (2026-11-08, mistral-large-4:cloud): after an assistant
        message with tool_calls, the server requires tool-role results
        IMMEDIATELY — one per call, no other role in between ("Expected last
        role User or Tool", "Not the same number of function calls and
        responses", "Unexpected role 'tool' after role 'system'"). uhu
        stores the round's observation as a single user message; convert it
        at the wire boundary so stored history stays as-is.

        Rules (probed live):
        - user obs directly after a tool_calls assistant → per-call tool
          results (full obs text each — the blob covers all of the round's
          actions and can't be split reliably; count matches protocol).
        - system messages between the assistant and its results are
          deferred until after the results (job notifications).
        - tool_name included when known (server accepts without, but it
          aids attribution).
        """
        out: List[Dict] = []
        pending_system: List[Dict] = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                if out and out[-1].get("tool_calls"):
                    pending_system.append(m)  # defer past the tool results
                    continue
                if pending_system:
                    # system after tool results — flush earlier deferrals too
                    out.extend(pending_system)
                    pending_system = []
                out.append(m)
                continue
            if role == "user" and out and out[-1].get("tool_calls"):
                # The observation for the round's tool_calls — convert.
                # native_tool_calls was already popped into tool_calls by
                # _sanitize_messages; recover the names from there.
                calls = out[-1].get("tool_calls") or []
                for tc in calls:
                    fn = tc.get("function") or {}
                    entry = {"role": "tool", "content": m.get("content") or ""}
                    if fn.get("name"):
                        entry["tool_name"] = fn["name"]
                    out.append(entry)
                continue
            if pending_system:
                out.extend(pending_system)
                pending_system = []
            out.append(m)
        if pending_system:
            out.extend(pending_system)
        return out

    @staticmethod
    def _sanitize_messages(messages: List[Dict]) -> List[Dict]:
        """Strip lone surrogates from message content."""
        def _clean(s):
            if not isinstance(s, str):
                return s
            try:
                s.encode('utf-8')
                return s
            except UnicodeEncodeError:
                return s.encode('utf-8', 'surrogatepass').decode('utf-8', 'replace')
        
        cleaned = []
        for m in messages:
            nm = dict(m)
            if 'content' in nm:
                nm['content'] = _clean(nm['content'])
            # As-is history (AS-IS-HISTORY-ARCH): stored entries carry
            # native_tool_calls (normalized name/params). The /api/chat wire
            # expects the assistant tool_calls shape — convert without
            # mutating the stored history entry.
            ntc = nm.pop("native_tool_calls", None)
            if ntc:
                nm["tool_calls"] = [
                    {"function": {"name": tc.get("name", ""),
                                  "arguments": tc.get("params") or {}}}
                    for tc in ntc if tc.get("name")
                ]
            cleaned.append(nm)
        return cleaned
    
    def supports_thinking(self) -> bool:
        return True
    
    def _call(self, messages: List[Dict], stream: bool = True) -> Tuple[str, Optional[int]]:
        messages = self._wire_tool_results(self._sanitize_messages(messages))
        if stream:
            return self._call_streaming(messages)
        else:
            return self._call_blocking(messages)

    def _call_streaming(self, messages: List[Dict]) -> Tuple[str, Optional[int]]:
        """Stream model response with chunk queue + reader thread."""
        spinner = Spinner(prefix="AI: ", color=ANSI_AI, thinking_color=ANSI_AI_DIM)
        spinner.start()
        msg = ""
        eval_count = None
        cached_count = None
        first = True
        thinking_shown = 0  # chars of thinking surfaced (last_thinking_chars)
        tool_call_frags: List[Dict] = []  # native tool_call fragments (Phase 2)
        chunk_queue = _queue.Queue(maxsize=100)  # Bounded queue for backpressure
        stream_error = [None]
        active_response = [None]

        def _stream_reader():
            try:
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "options": self._build_options(),
                }
                think = self._think_param()
                if think is not None:
                    payload["think"] = think
                with self.client._client.stream(
                    "POST",
                    "/api/chat",
                    json=payload,
                ) as response:
                    active_response[0] = response
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:
                            continue
                        part = json.loads(line)
                        if err := part.get("error"):
                            from ollama import ResponseError
                            raise ResponseError(err)
                        chunk_queue.put(part)
            except Exception as e:
                stream_error[0] = e
            finally:
                active_response[0] = None
                chunk_queue.put(None)

        reader_thread = threading.Thread(target=_stream_reader, daemon=True)
        reader_thread.start()
        last_chunk_time = time.time()

        try:
            while True:
                try:
                    chunk = chunk_queue.get(timeout=0.1)
                except _queue.Empty:
                    if stream_error[0]:
                        spinner.stop()
                        _ai_color_off()
                        raise stream_error[0]
                    if time.time() - last_chunk_time > self.STREAM_CHUNK_TIMEOUT:
                        spinner.stop()
                        _ai_color_off()
                        agent_print(f"\n[Model streaming timeout — no response for {self.STREAM_CHUNK_TIMEOUT}s]\n")
                        break
                    continue

                if chunk is None:
                    if stream_error[0]:
                        spinner.stop()
                        _ai_color_off()
                        raise stream_error[0]
                    break

                last_chunk_time = time.time()
                thinking_token = chunk.get("message", {}).get("thinking", "")
                token = chunk.get("message", {}).get("content", "")
                
                if thinking_token and self.thinking:
                    if spinner.is_running:
                        spinner.append_thinking(thinking_token)
                    thinking_shown += len(thinking_token)
                if token:
                    if first:
                        spinner.stop()
                        _ai_color_on()
                        sys.stdout.write("AI: ")
                        sys.stdout.flush()
                        first = False
                    print(token, end="", flush=True)
                msg += token
                if chunk.get("done"):
                    eval_count = chunk.get("prompt_eval_count")
                    cached_count = chunk.get("prompt_eval_cached_count")
                    self.last_cached_tokens = cached_count
                    self.last_output_tokens = chunk.get("eval_count")
                # Native tool_calls (Phase 2): fragments may arrive spread across
                # chunks or complete in the final chunk — collect, merge at end.
                msg_tool_calls = (chunk.get("message") or {}).get("tool_calls") or []
                if msg_tool_calls:
                    tool_call_frags.extend(msg_tool_calls)
        except KeyboardInterrupt:
            resp = active_response[0]
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass
            spinner.stop()
            _ai_color_off()
            raise

        if first:
            spinner.stop()
            _ai_color_on()
            sys.stdout.write("AI: ")
            sys.stdout.flush()
        _ai_color_off()
        print("\n")
        # Native tool_calls (Phase 2): surface what the model emitted; content
        # contract unchanged (empty stays empty).
        self.last_tool_calls = normalize_tool_calls(merge_tool_call_fragments(tool_call_frags))
        self.last_thinking_chars = thinking_shown
        return msg, eval_count

    def _call_blocking(self, messages: List[Dict]) -> Tuple[str, Optional[int]]:
        """Non-streaming model call with timeout thread."""
        spinner = Spinner(prefix="AI: ", color=ANSI_AI, thinking_color=ANSI_AI_DIM)
        spinner.start()
        result_holder = [None]
        error_holder = [None]
        done_event = threading.Event()

        def _blocking_call():
            kwargs = dict(
                model=self.model,
                messages=messages,
                options=self._build_options()
            )
            think = self._think_param()
            if think is not None:
                kwargs["think"] = think
            try:
                result_holder[0] = self.client.chat(**kwargs)
            except Exception as e:
                error_holder[0] = e
            finally:
                done_event.set()

        call_thread = threading.Thread(target=_blocking_call, daemon=True)
        call_thread.start()
        start_time = time.time()

        try:
            while not done_event.wait(timeout=0.5):
                if time.time() - start_time > self.NON_STREAM_TIMEOUT:
                    spinner.stop()
                    raise TimeoutError(
                        f"Model call timed out after {self.NON_STREAM_TIMEOUT}s"
                    )
        except KeyboardInterrupt:
            spinner.stop()
            _ai_color_off()
            raise

        if error_holder[0]:
            spinner.stop()
            _ai_color_off()
            raise error_holder[0]

        response = result_holder[0]
        spinner.stop()
        msg = response["message"]["content"]
        eval_count = response.get("prompt_eval_count")
        cached_count = None
        try:
            extra = getattr(response, "model_extra", None) or {}
            cached_count = extra.get("prompt_eval_cached_count")
            if cached_count is None:
                cached_count = response.get("prompt_eval_cached_count")
        except Exception:
            pass
        self.last_cached_tokens = cached_count
        self.last_output_tokens = response.get("eval_count")
        # Native tool_calls (Phase 2): blocking path delivers them complete.
        try:
            self.last_tool_calls = normalize_tool_calls(response["message"].get("tool_calls"))
        except Exception:
            self.last_tool_calls = []
        # Blocking path surfaces content only — count thinking as "not shown"
        # unless the model embedded it visibly. Ollama returns thinking in
        # message.thinking; recorded so the session can distinguish channels
        # when auditing invisible token spend.
        try:
            self.last_thinking_chars = len(response["message"].get("thinking") or "")
        except Exception:
            self.last_thinking_chars = 0
        _ai_color_on()
        sys.stdout.write("AI: ")
        sys.stdout.flush()
        print(f"{msg}\n")
        _ai_color_off()
        return msg, eval_count


class OpenAIBackend(LLMBackend):
    """OpenAI-compatible API backend using openai.Client."""
    
    STREAM_CHUNK_TIMEOUT = 180
    NON_STREAM_TIMEOUT = 600
    
    def __init__(self, base_url: str, api_key: str, model: str, ctx_size: int,
                 thinking: bool = True, tpm_limit: Optional[int] = None,
                 max_context: Optional[int] = None, quiet: bool = False,
                 extra_body_path: Optional[str] = None,
                 temperature: Optional[float] = None,
                 think_level: Optional[str] = None,
                 top_p: Optional[float] = None):
        super().__init__()
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package required for OpenAI backend. Run: pip install openai")
        
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.ctx_size = ctx_size  # Used for context management, not passed to API
        self.thinking = thinking
        # Sampling temperature — None = don't send the param (provider default;
        # o1/o3-style reasoning models reject it). Set via --temperature / /temperature.
        self.temperature = temperature
        # Top-p (nucleus) sampling — None = don't send the param (provider default).
        self.top_p = top_p
        # Thinking effort — None = don't send reasoning_effort (model default);
        # "off" → reasoning_effort "none"; otherwise sent as the level name.
        self.think_level = think_level
        self._last_usage = None
        self._quiet = quiet
        # Provider-specific request body params from JSON file (--openai-extra-body)
        self._extra_body = self._load_extra_body(extra_body_path)

        # Token counter — always on for OpenAI-compatible backends
        self._token_counter = TokenCounter(model, per_message_overhead=4)

        # History trimmer — always on (OpenAI protocol doesn't guarantee server-side eviction)
        # Without --tpm: use full ctx_size. With --tpm: cap at max_context (default 16384).
        trim_budget = ctx_size
        if tpm_limit is not None:
            trim_budget = min(ctx_size, max_context or 16384)
        self._trimmer = HistoryTrimmer(
            token_counter=self._token_counter,
            max_tokens=trim_budget,
            reserve_output=2048
        )

        # Retry handler — always on, but configuration depends on --tpm
        if tpm_limit is not None:
            # Aggressive: 429 + rate limits, 20s backoff
            self._retry = RetryHandler(
                triggers=["429", "rate_limit", "connection"],
                initial_wait=20,
                max_wait=60,
                max_retries=3,
                quiet=quiet
            )
            self._tpm_tracker = TPMTracker(tpm_limit=tpm_limit, quiet=quiet)
        else:
            # Light: connection/500 only, 5s backoff, no 429 logic
            self._retry = RetryHandler(
                triggers=["connection", "500", "internal server error"],
                initial_wait=5,
                max_wait=30,
                max_retries=3,
                quiet=quiet
            )
            self._tpm_tracker = None
    
    def supports_thinking(self) -> bool:
        # OpenAI API doesn't expose thinking tokens in standard format
        # Some models put reasoning in separate field which we capture
        return False
    
    @staticmethod
    def _load_extra_body(path: Optional[str]) -> Dict[str, Any]:
        """Load extra request body params from a JSON file (--openai-extra-body).

        Supports ~ and environment variable expansion. Fails fast with a
        clear error if the file is missing, unreadable, or not a JSON object.
        """
        if not path:
            return {}
        expanded = os.path.expandvars(os.path.expanduser(path))
        if not os.path.isfile(expanded):
            raise FileNotFoundError(f"--openai-extra-body file not found: {expanded}")
        try:
            with open(expanded, "r", encoding="utf-8") as f:
                data = json.load(f)
        except ValueError as e:
            raise ValueError(f"--openai-extra-body file is not valid JSON: {expanded}: {e}")
        if not isinstance(data, dict):
            raise ValueError(f"--openai-extra-body file must contain a JSON object: {expanded}")
        return data

    def _sanitize_messages(self, messages: List[Dict]) -> List[Dict]:
        """Convert messages to OpenAI format and sanitize."""
        sanitized = []
        for m in messages:
            # OpenAI format is compatible, just ensure content is string
            content = m.get("content", "")
            if isinstance(content, list):
                # Already in multimodal format (vision)
                sanitized.append(m)
                continue
            entry = {
                "role": m.get("role", "user"),
                "content": content
            }
            # As-is history (AS-IS-HISTORY-ARCH): convert stored native calls
            # to the /v1 wire shape — arguments as a JSON string per OpenAI
            # spec (the same format these models emit on the wire).
            ntc = m.get("native_tool_calls")
            if ntc:
                entry["tool_calls"] = [
                    {"function": {"name": tc.get("name", ""),
                                  "arguments": json.dumps(tc.get("params") or {},
                                                          ensure_ascii=False,
                                                          default=str)}}
                    for tc in ntc if tc.get("name")
                ]
            sanitized.append(entry)
        return sanitized

    @staticmethod
    def _wire_tool_results(messages: List[Dict]) -> List[Dict]:
        """Wire-boundary fix for the native function-calling protocol.

        Same protocol as the native backend (see the OllamaNativeBackend
        version): after an assistant tool_calls message, tool-role results
        must follow immediately — one per call. /v1 additionally matches
        results to calls by tool_call_id (probed: Ollama's /v1 accepts
        missing ids, but ids are the OpenAI spec and other providers
        require them). uhu's stored history has no ids (native Ollama
        channel doesn't provide them), so synthesize stable ones from the
        call index and attach them to both sides at the wire boundary.
        """
        out: List[Dict] = []
        pending_system: List[Dict] = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                if out and out[-1].get("tool_calls"):
                    pending_system.append(m)  # defer past the tool results
                    continue
                if pending_system:
                    out.extend(pending_system)
                    pending_system = []
                out.append(m)
                continue
            if role == "user" and out and out[-1].get("tool_calls"):
                calls = out[-1].get("tool_calls") or []
                for idx, tc in enumerate(calls):
                    fn = tc.get("function") or {}
                    call_id = fn.get("call_id") or f"uhu_{len(out) - 1}_{idx}"
                    tc.setdefault("id", call_id)
                    out.append({"role": "tool", "tool_call_id": call_id,
                                "content": m.get("content") or ""})
                continue
            if pending_system:
                out.extend(pending_system)
                pending_system = []
            out.append(m)
        if pending_system:
            out.extend(pending_system)
        return out

    def _call(self, messages: List[Dict], stream: bool = True) -> Tuple[str, Optional[int]]:
        messages = self._wire_tool_results(self._sanitize_messages(messages))
        if stream:
            return self._call_streaming(messages)
        else:
            return self._call_blocking(messages)

    def _build_create_kwargs(self, messages: List[Dict], stream: bool) -> Dict[str, Any]:
        """Build kwargs for chat.completions.create, handling max_tokens vs max_completion_tokens."""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        if stream:
            # Ask the provider to include usage in the final stream chunk
            # (needed for prompt_tokens / cached_tokens stats). Providers
            # that reject stream_options are handled in _call_create.
            kwargs["stream_options"] = {"include_usage": True}
        # Provider-specific params from --openai-extra-body JSON file
        if self._extra_body:
            kwargs["extra_body"] = dict(self._extra_body)
        # Sampling temperature — sent only when explicitly set; extra_body
        # fields still override it per SDK merge order.
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        # Top-p (nucleus) sampling — sent only when explicitly set; extra_body
        # fields still override it per SDK merge order.
        if self.top_p is not None:
            kwargs["top_p"] = self.top_p
        # Thinking effort — Ollama's OpenAI-compatible endpoint maps
        # reasoning_effort (and reasoning.effort) to model thinking levels.
        if self.think_level is not None:
            level = self.think_level.lower()
            kwargs["reasoning_effort"] = "none" if level == "off" else level
        # Some models (e.g. o1/o3 series) don't support temperature or max_tokens.
        # We try max_completion_tokens first (newer API), fall back to max_tokens,
        # and if both fail, retry without any max parameter.
        max_val = min(self.ctx_size, 8192)
        kwargs["max_completion_tokens"] = max_val
        return kwargs
    
    def _call_create(self, messages: List[Dict], stream: bool):
        """Call create with fallback for max_tokens parameter incompatibility."""
        kwargs = self._build_create_kwargs(messages, stream)
        try:
            return self.client.chat.completions.create(**kwargs)
        except Exception as e:
            err_str = str(e).lower()
            # Some models reject temperature (e.g. o1/o3 series) — retry without it
            if self.temperature is not None and "temperature" in err_str:
                logger.warning("OpenAI fallback: retrying without temperature (%s)", e)
                kwargs.pop("temperature", None)
                # Some models reject both temperature and top_p together
                if self.top_p is not None and "top_p" in err_str:
                    kwargs.pop("top_p", None)
                return self.client.chat.completions.create(**kwargs)
            # Some models reject top_p (e.g. o1/o3 series) — retry without it
            if self.top_p is not None and "top_p" in err_str:
                logger.warning("OpenAI fallback: retrying without top_p (%s)", e)
                kwargs.pop("top_p", None)
                return self.client.chat.completions.create(**kwargs)
            # Some providers don't support reasoning_effort — retry without it
            if "reasoning_effort" in err_str or "reasoning effort" in err_str:
                logger.warning("OpenAI fallback: retrying without reasoning_effort (%s)", e)
                kwargs.pop("reasoning_effort", None)
                return self.client.chat.completions.create(**kwargs)
            # Some providers reject stream_options — retry without it
            if "stream_options" in err_str or "include_usage" in err_str:
                logger.warning("OpenAI fallback: retrying without stream_options (%s)", e)
                kwargs.pop("stream_options", None)
                return self.client.chat.completions.create(**kwargs)
            # Fall back to max_tokens if max_completion_tokens not supported
            if "max_completion_tokens" in err_str or "unrecognized" in err_str:
                logger.warning("OpenAI fallback: switching max_completion_tokens → max_tokens (%s)", e)
                kwargs.pop("max_completion_tokens", None)
                kwargs["max_tokens"] = min(self.ctx_size, 8192)
                try:
                    return self.client.chat.completions.create(**kwargs)
                except Exception as e2:
                    err_str2 = str(e2).lower()
                    # Some models reject max_tokens too — retry without any max param
                    if "max_tokens" in err_str2 or "unsupported" in err_str2:
                        logger.warning("OpenAI fallback: removing ALL output caps (%s) — provider default applies", e2)
                        kwargs.pop("max_tokens", None)
                        return self.client.chat.completions.create(**kwargs)
                    raise
            # Some models reject max_completion_tokens with "unsupported" — try max_tokens
            if "unsupported" in err_str and "max" in err_str:
                logger.warning("OpenAI fallback: unsupported-max path, switching to max_tokens (%s)", e)
                kwargs.pop("max_completion_tokens", None)
                kwargs["max_tokens"] = min(self.ctx_size, 8192)
                try:
                    return self.client.chat.completions.create(**kwargs)
                except Exception as e2:
                    if "max_tokens" in str(e2).lower() or "unsupported" in str(e2).lower():
                        logger.warning("OpenAI fallback: removing ALL output caps (%s) — provider default applies", e2)
                        kwargs.pop("max_tokens", None)
                        return self.client.chat.completions.create(**kwargs)
                    raise
            raise
    
    def _call_streaming(self, messages: List[Dict]) -> Tuple[str, Optional[int]]:
        """Stream response using OpenAI SDK."""
        spinner = Spinner(prefix="AI: ", color=ANSI_AI, thinking_color=ANSI_AI_DIM)
        spinner.start()
        msg = ""
        eval_count = None
        cached_count = None
        first = True
        
        tool_call_frags: List[Dict] = []  # /v1 tool_call delta fragments (Phase 3)
        finish_reason = None
        try:
            response = self._call_create(messages, stream=True)
            
            for chunk in response:
                # Usage arrives in the final chunk (stream_options.include_usage)
                if getattr(chunk, "usage", None):
                    self._last_usage = chunk.usage
                    eval_count = chunk.usage.prompt_tokens
                    self.last_output_tokens = getattr(chunk.usage, "completion_tokens", None)
                    details = getattr(chunk.usage, "prompt_tokens_details", None)
                    if details is not None:
                        cached_count = getattr(details, "cached_tokens", None)
                    cdetails = getattr(chunk.usage, "completion_tokens_details", None)
                    if cdetails is not None:
                        self.last_reasoning_tokens = getattr(cdetails, "reasoning_tokens", None)
                if not chunk.choices:
                    continue
                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason
                # Native tool_calls (Phase 3): collect delta fragments for merge
                # (read whenever present — some providers report non-tool finish_reasons)
                for frag in (getattr(chunk.choices[0].delta, "tool_calls", None) or []):
                    tool_call_frags.append(frag)
                    
                delta = chunk.choices[0].delta
                token = delta.content or ""
                
                if token:
                    if first:
                        spinner.stop()
                        _ai_color_on()
                        sys.stdout.write("AI: ")
                        sys.stdout.flush()
                        first = False
                    print(token, end="", flush=True)
                    msg += token
            
            # Native tool_calls (Phase 3): merge delta fragments and normalize
            # to the shared contract. Content contract unchanged.
            self.last_tool_calls = normalize_tool_calls(merge_tool_call_fragments(tool_call_frags))
            # OpenAI reasoning arrives via usage details (last_reasoning_tokens);
            # mark thinking as reported so the session's invisible-token hint
            # doesn't fire for reasoning models.
            cdetails = getattr(getattr(self._last_usage, "completion_tokens_details", None), "reasoning_tokens", None) if self._last_usage else None
            if cdetails:
                self.last_thinking_chars = 1  # truthy sentinel; count unknown
            # Get usage from final chunk if available
            if hasattr(response, 'usage') and response.usage:
                self._last_usage = response.usage
                eval_count = response.usage.prompt_tokens
                self.last_output_tokens = getattr(response.usage, "completion_tokens", None)
            self.last_cached_tokens = cached_count
            # Diagnostics: raw usage to the log; explicit note when the whole
            # output budget went to hidden reasoning with no visible content.
            if self._last_usage is not None:
                try:
                    logger.info("OpenAI usage: %s", json.dumps(self._last_usage.model_dump()))
                except Exception:
                    pass
            if not msg and finish_reason == "length":
                spinner.stop()
                agent_print("[⚠ Output cap hit during hidden reasoning — no visible content was produced.]\n")
            
        except KeyboardInterrupt:
            spinner.stop()
            _ai_color_off()
            raise
        except Exception as e:
            spinner.stop()
            _ai_color_off()
            raise
        
        if first:
            spinner.stop()
            _ai_color_on()
            sys.stdout.write("AI: ")
            sys.stdout.flush()
        _ai_color_off()
        print("\n")
        return msg, eval_count
    
    def _call_blocking(self, messages: List[Dict]) -> Tuple[str, Optional[int]]:
        """Non-blocking call using OpenAI SDK."""
        spinner = Spinner(prefix="AI: ", color=ANSI_AI, thinking_color=ANSI_AI_DIM)
        spinner.start()
        
        try:
            response = self._call_create(messages, stream=False)
            
            content = response.choices[0].message.content or ""
            # Native tool_calls (Phase 3): /v1 blocking delivers complete calls
            # with JSON-string arguments; normalize with degradation to _raw.
            self.last_tool_calls = normalize_tool_calls(
                getattr(response.choices[0].message, "tool_calls", None)
            )
            self._last_usage = response.usage
            eval_count = response.usage.prompt_tokens if response.usage else None
            cached_count = None
            if response.usage:
                self.last_output_tokens = getattr(response.usage, "completion_tokens", None)
                details = getattr(response.usage, "prompt_tokens_details", None)
                if details is not None:
                    cached_count = getattr(details, "cached_tokens", None)
                cdetails = getattr(response.usage, "completion_tokens_details", None)
                if cdetails is not None:
                    self.last_reasoning_tokens = getattr(cdetails, "reasoning_tokens", None)
            self.last_cached_tokens = cached_count
            
            spinner.stop()
            _ai_color_on()
            sys.stdout.write("AI: ")
            sys.stdout.flush()
            print(f"{content}\n")
            _ai_color_off()
            return content, eval_count
            
        except KeyboardInterrupt:
            spinner.stop()
            _ai_color_off()
            raise
        except Exception as e:
            spinner.stop()
            _ai_color_off()
            raise


def create_backend(
    api_type: str,
    host: str,
    model: str,
    ctx_size: int,
    thinking: bool = True,
    api_key: Optional[str] = None,
    tpm_limit: Optional[int] = None,
    max_context: Optional[int] = None,
    quiet: bool = False,
    extra_body_path: Optional[str] = None,
    temperature: Optional[float] = None,
    think_level: Optional[str] = None,
    top_p: Optional[float] = None
) -> LLMBackend:
    """Factory function to create appropriate backend.
    
    Args:
        api_type: 'ollama' or 'openai'
        host: Base URL for the API
        model: Model name
        ctx_size: Context window size
        thinking: Whether to show thinking tokens
        api_key: API key (required for OpenAI, optional for Ollama)
        tpm_limit: Tokens-per-minute limit (OpenAI-compatible only, enables TPM tracking)
        max_context: Max context cap for trimming (OpenAI-compatible + --tpm only)
        extra_body_path: Path to JSON file with extra request body params (OpenAI-compatible only)
        temperature: Sampling temperature 0.0-2.0 (None = backend default: 0.0 for Ollama, not sent for OpenAI)
        top_p: Top-p (nucleus) sampling 0.0-1.0 (None = model/provider default, not sent)
        think_level: Thinking effort (None = model default; "off" disables thinking;
            "low"/"high"/"max" sent as Ollama 'think' level or OpenAI 'reasoning_effort')
        quiet: Suppress non-essential output
    
    Returns:
        Configured LLMBackend instance
    """
    if api_type == "openai":
        # Ensure /v1 suffix for OpenAI endpoint
        base_url = host
        if not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
        
        key = api_key or os.environ.get("OLLAMA_API_KEY", "ollama")
        return OpenAIBackend(
            base_url=base_url,
            api_key=key,
            model=model,
            ctx_size=ctx_size,
            thinking=thinking,
            tpm_limit=tpm_limit,
            max_context=max_context,
            extra_body_path=extra_body_path,
            temperature=temperature,
            top_p=top_p,
            think_level=think_level,
            quiet=quiet
        )
    else:
        # Native Ollama
        return OllamaNativeBackend(
            host=host,
            model=model,
            ctx_size=ctx_size,
            thinking=thinking,
            temperature=temperature,
            top_p=top_p,
            think_level=think_level
        )
