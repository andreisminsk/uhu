"""LLM Backend Abstraction Layer.

Provides unified interface for different LLM APIs:
- OllamaNativeBackend: Uses ollama.Client with /api/chat endpoint
- OpenAIBackend: Uses openai.Client with /v1/chat/completions endpoint
"""

import os
import sys
import json
import queue as _queue
import threading
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional, Any

from .constants import MODEL_TEMPERATURE
from .display import agent_print
from .spinner import Spinner


class LLMBackend(ABC):
    """Abstract base class for LLM API backends."""
    
    @abstractmethod
    def call(self, messages: List[Dict], stream: bool = True) -> Tuple[str, Optional[int]]:
        """Call the model and return (content, eval_count_or_None).
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            stream: Whether to use streaming mode
            
        Returns:
            Tuple of (content_string, eval_count_or_None)
        """
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
    
    def call(self, messages: List[Dict], stream: bool = True) -> Tuple[str, Optional[int]]:
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
    
    def __init__(self, base_url: str, api_key: str, model: str, ctx_size: int, thinking: bool = True):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package required for OpenAI backend. Run: pip install openai")
        
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.ctx_size = ctx_size  # Used for context management, not passed to API
        self.thinking = thinking
        self._last_usage = None
    
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
    
    def call(self, messages: List[Dict], stream: bool = True) -> Tuple[str, Optional[int]]:
        messages = self._sanitize_messages(messages)
        if stream:
            return self._call_streaming(messages)
        else:
            return self._call_blocking(messages)
    
    def _call_streaming(self, messages: List[Dict]) -> Tuple[str, Optional[int]]:
        """Stream response using OpenAI SDK."""
        spinner = Spinner(prefix="AI: ")
        spinner.start()
        msg = ""
        eval_count = None
        first = True
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=MODEL_TEMPERATURE,
                stream=True,
                max_tokens=min(self.ctx_size, 8192)  # Reasonable limit
            )
            
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=MODEL_TEMPERATURE,
                max_tokens=min(self.ctx_size, 8192)
            )
            
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
    api_key: Optional[str] = None
) -> LLMBackend:
    """Factory function to create appropriate backend.
    
    Args:
        api_type: 'ollama' or 'openai'
        host: Base URL for the API
        model: Model name
        ctx_size: Context window size
        thinking: Whether to show thinking tokens
        api_key: API key (required for OpenAI, optional for Ollama)
    
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
            thinking=thinking
        )
    else:
        # Native Ollama
        return OllamaNativeBackend(
            host=host,
            model=model,
            ctx_size=ctx_size,
            thinking=thinking
        )
