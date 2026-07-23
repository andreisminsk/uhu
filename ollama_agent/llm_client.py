"""LLM client — extracted from session.py _call_model.

Encapsulates model communication (streaming and non-streaming) with
proper timeout, Ctrl+C handling, and encoding fallback.
"""

import json as _json
import logging
import queue as _queue
import sys
import threading
import time

from .constants import MODEL_TEMPERATURE
from .display import agent_print
from .spinner import Spinner

logger = logging.getLogger(__name__)


class LLMClient:
    """Wraps Ollama client for model communication.

    Handles:
    - Streaming responses with chunk queue + reader thread
    - Non-streaming responses with timeout thread
    - Ctrl+C cancellation (closes HTTP response on stream, raises on both)
    - Thinking token extraction (kept separate from content)
    - Timeout detection (180s stream idle, 600s non-stream total)

    Args:
        client: Ollama Client instance.
        model: Model name string.
        ctx_size: Context window size in tokens.
        thinking: Whether to display thinking tokens.
        log_fn: Optional callback for logging (role, message).
    """

    STREAM_CHUNK_TIMEOUT = 180  # seconds with no chunks before giving up
    NON_STREAM_TIMEOUT = 600  # 10 minutes for non-streaming calls

    def __init__(self, client, model, ctx_size, thinking=True, log_fn=None):
        self.client = client
        self.model = model
        self.ctx_size = ctx_size
        self.thinking = thinking
        self._log = log_fn or (lambda role, msg: None)

    @staticmethod
    def _sanitize_messages(messages):
        """Strip lone surrogates from message content to prevent UTF-8 encode errors."""
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

    def _build_options(self):
        return {"num_ctx": self.ctx_size, "temperature": MODEL_TEMPERATURE}

    def call(self, messages, stream=True):
        """Call the model and return (content, eval_count).

        Args:
            messages: List of message dicts to send to the model.
            stream: Whether to use streaming mode.

        Returns:
            Tuple of (content_string, eval_count_or_None).

        Raises:
            KeyboardInterrupt: If user interrupts with Ctrl+C.
            TimeoutError: If non-streaming call exceeds NON_STREAM_TIMEOUT.
            Exception: On model errors.
        """
        # Sanitize lone surrogates that can't be encoded as UTF-8 by httpx
        messages = self._sanitize_messages(messages)
        if stream:
            return self._call_streaming(messages)
        else:
            return self._call_blocking(messages)

    def _call_streaming(self, messages):
        """Stream model response with chunk queue + reader thread."""
        spinner = Spinner(prefix="AI: ")
        spinner.start()
        msg = ""
        eval_count = None
        first = True
        chunk_queue = _queue.Queue()
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
                chunk_queue.put(None)

        reader_thread = threading.Thread(target=_stream_reader, daemon=True)
        reader_thread.start()

        last_chunk_time = time.time()

        try:
            while True:
                try:
                    chunk = chunk_queue.get_nowait()
                except _queue.Empty:
                    if stream_error[0]:
                        spinner.stop()
                        raise stream_error[0]
                    if time.time() - last_chunk_time > self.STREAM_CHUNK_TIMEOUT:
                        spinner.stop()
                        self._log("system", f"[Model streaming timeout — no response for {self.STREAM_CHUNK_TIMEOUT}s]")
                        logger.warning("Model streaming timeout — no response for %ds", self.STREAM_CHUNK_TIMEOUT)
                        agent_print(f"\n[Model streaming timeout — no response for {self.STREAM_CHUNK_TIMEOUT}s]\n")
                        break
                    time.sleep(0.05)
                    continue

                if chunk is None:
                    if stream_error[0]:
                        spinner.stop()
                        raise stream_error[0]
                    break

                last_chunk_time = time.time()
                thinking_token = chunk.get("message", {}).get("thinking", "")
                token = chunk.get("message", {}).get("content", "")
                if thinking_token:
                    if self.thinking and spinner.is_running:
                        spinner.append_thinking(thinking_token)
                    logger.debug("Thinking token (%d chars)", len(thinking_token))
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

    def _call_blocking(self, messages):
        """Non-streaming model call with timeout thread."""
        spinner = Spinner(prefix="AI: ")
        spinner.start()
        result_holder = [None]
        error_holder = [None]
        done_event = threading.Event()

        def _blocking_call():
            try:
                result_holder[0] = self.client.chat(
                    model=self.model, messages=messages,
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
                        f"Model call timed out after {self.NON_STREAM_TIMEOUT}s — "
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
        thinking_content = response["message"].get("thinking", "")
        msg = response["message"]["content"]
        if thinking_content:
            logger.debug("Thinking content skipped (%d chars)", len(thinking_content))
        eval_count = response.get("prompt_eval_count")
        logger.debug("Non-streaming response received | eval_count=%s | len=%d", eval_count, len(msg))
        sys.stdout.write("AI: ")
        sys.stdout.flush()
        print(f"{msg}\n")
        return msg, eval_count
