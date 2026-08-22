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

from .constants import MODEL_TEMPERATURE
from .display import agent_print
from .spinner import Spinner

logger = logging.getLogger(__name__)


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
                    f"\n[TPM limit: {current}/{self.tpm_limit} tokens used. "
                    f"Waiting {wait_seconds:.0f}s for budget to clear...]\n"
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
    
    def __init__(self, host: str, model: str, ctx_size: int, thinking: bool = True):
        super().__init__()
        from ollama import Client
        self.client = Client(host=host)
        self.model = model
        self.ctx_size = ctx_size
        self.thinking = thinking
    
    def _build_options(self) -> Dict[str, Any]:
        return {"num_ctx": self.ctx_size, "temperature": MODEL_TEMPERATURE}
    
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
            cleaned.append(nm)
        return cleaned
    
    def supports_thinking(self) -> bool:
        return True
    
    def _call(self, messages: List[Dict], stream: bool = True) -> Tuple[str, Optional[int]]:
        messages = self._sanitize_messages(messages)
        if stream:
            return self._call_streaming(messages)
        else:
            return self._call_blocking(messages)

    def _call_streaming(self, messages: List[Dict]) -> Tuple[str, Optional[int]]:
        """Stream model response with chunk queue + reader thread."""
        spinner = Spinner(prefix="AI: ")
        spinner.start()
        msg = ""
        eval_count = None
        first = True
        chunk_queue = _queue.Queue(maxsize=100)  # Bounded queue for backpressure
        stream_error = [None]
        active_response = [None]

        def _stream_reader():
            try:
                with self.client._client.stream(
                    "POST",
                    "/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True,
                        "options": self._build_options(),
                    },
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
                        raise stream_error[0]
                    if time.time() - last_chunk_time > self.STREAM_CHUNK_TIMEOUT:
                        spinner.stop()
                        agent_print(f"\n[Model streaming timeout — no response for {self.STREAM_CHUNK_TIMEOUT}s]\n")
                        break
                    continue

                if chunk is None:
                    if stream_error[0]:
                        spinner.stop()
                        raise stream_error[0]
                    break

                last_chunk_time = time.time()
                thinking_token = chunk.get("message", {}).get("thinking", "")
                token = chunk.get("message", {}).get("content", "")
                
                if thinking_token and self.thinking:
                    if spinner.is_running:
                        spinner.append_thinking(thinking_token)
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

    def _call_blocking(self, messages: List[Dict]) -> Tuple[str, Optional[int]]:
        """Non-streaming model call with timeout thread."""
        spinner = Spinner(prefix="AI: ")
        spinner.start()
        result_holder = [None]
        error_holder = [None]
        done_event = threading.Event()

        def _blocking_call():
            try:
                result_holder[0] = self.client.chat(
                    model=self.model,
                    messages=messages,
                    options=self._build_options()
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
                if time.time() - start_time > self.NON_STREAM_TIMEOUT:
                    spinner.stop()
                    raise TimeoutError(
                        f"Model call timed out after {self.NON_STREAM_TIMEOUT}s"
                    )
        except KeyboardInterrupt:
            spinner.stop()
            raise

        if error_holder[0]:
            spinner.stop()
            raise error_holder[0]

        response = result_holder[0]
        spinner.stop()
        msg = response["message"]["content"]
        eval_count = response.get("prompt_eval_count")
        sys.stdout.write("AI: ")
        sys.stdout.flush()
        print(f"{msg}\n")
        return msg, eval_count


class OpenAIBackend(LLMBackend):
    """OpenAI-compatible API backend using openai.Client."""
    
    STREAM_CHUNK_TIMEOUT = 180
    NON_STREAM_TIMEOUT = 600
    
    def __init__(self, base_url: str, api_key: str, model: str, ctx_size: int,
                 thinking: bool = True, tpm_limit: Optional[int] = None,
                 max_context: Optional[int] = None, quiet: bool = False):
        super().__init__()
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package required for OpenAI backend. Run: pip install openai")
        
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.ctx_size = ctx_size  # Used for context management, not passed to API
        self.thinking = thinking
        self._last_usage = None
        self._quiet = quiet

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
    
    def _sanitize_messages(self, messages: List[Dict]) -> List[Dict]:
        """Convert messages to OpenAI format and sanitize."""
        sanitized = []
        for m in messages:
            # OpenAI format is compatible, just ensure content is string
            content = m.get("content", "")
            if isinstance(content, list):
                # Already in multimodal format (vision)
                sanitized.append(m)
            else:
                sanitized.append({
                    "role": m.get("role", "user"),
                    "content": content
                })
        return sanitized
    
    def _call(self, messages: List[Dict], stream: bool = True) -> Tuple[str, Optional[int]]:
        messages = self._sanitize_messages(messages)
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
            # Fall back to max_tokens if max_completion_tokens not supported
            if "max_completion_tokens" in err_str or "unrecognized" in err_str:
                kwargs.pop("max_completion_tokens", None)
                kwargs["max_tokens"] = min(self.ctx_size, 8192)
                try:
                    return self.client.chat.completions.create(**kwargs)
                except Exception as e2:
                    err_str2 = str(e2).lower()
                    # Some models reject max_tokens too — retry without any max param
                    if "max_tokens" in err_str2 or "unsupported" in err_str2:
                        kwargs.pop("max_tokens", None)
                        return self.client.chat.completions.create(**kwargs)
                    raise
            # Some models reject max_completion_tokens with "unsupported" — try max_tokens
            if "unsupported" in err_str and "max" in err_str:
                kwargs.pop("max_completion_tokens", None)
                kwargs["max_tokens"] = min(self.ctx_size, 8192)
                try:
                    return self.client.chat.completions.create(**kwargs)
                except Exception as e2:
                    if "max_tokens" in str(e2).lower() or "unsupported" in str(e2).lower():
                        kwargs.pop("max_tokens", None)
                        return self.client.chat.completions.create(**kwargs)
                    raise
            raise
    
    def _call_streaming(self, messages: List[Dict]) -> Tuple[str, Optional[int]]:
        """Stream response using OpenAI SDK."""
        spinner = Spinner(prefix="AI: ")
        spinner.start()
        msg = ""
        eval_count = None
        first = True
        
        try:
            response = self._call_create(messages, stream=True)
            
            for chunk in response:
                if not chunk.choices:
                    continue
                    
                delta = chunk.choices[0].delta
                token = delta.content or ""
                
                if token:
                    if first:
                        spinner.stop()
                        sys.stdout.write("AI: ")
                        sys.stdout.flush()
                        first = False
                    print(token, end="", flush=True)
                    msg += token
            
            # Get usage from final chunk if available
            if hasattr(response, 'usage') and response.usage:
                self._last_usage = response.usage
                eval_count = response.usage.prompt_tokens
            
        except KeyboardInterrupt:
            spinner.stop()
            raise
        except Exception as e:
            spinner.stop()
            raise
        
        if first:
            spinner.stop()
            sys.stdout.write("AI: ")
            sys.stdout.flush()
        print("\n")
        return msg, eval_count
    
    def _call_blocking(self, messages: List[Dict]) -> Tuple[str, Optional[int]]:
        """Non-streaming call using OpenAI SDK."""
        spinner = Spinner(prefix="AI: ")
        spinner.start()
        
        try:
            response = self._call_create(messages, stream=False)
            
            content = response.choices[0].message.content or ""
            self._last_usage = response.usage
            eval_count = response.usage.prompt_tokens if response.usage else None
            
            spinner.stop()
            sys.stdout.write("AI: ")
            sys.stdout.flush()
            print(f"{content}\n")
            return content, eval_count
            
        except KeyboardInterrupt:
            spinner.stop()
            raise
        except Exception as e:
            spinner.stop()
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
    quiet: bool = False
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
            quiet=quiet
        )
    else:
        # Native Ollama
        return OllamaNativeBackend(
            host=host,
            model=model,
            ctx_size=ctx_size,
            thinking=thinking
        )
