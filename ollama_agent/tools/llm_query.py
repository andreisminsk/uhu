"""llm_query tool — send a prompt to a local LLM and return the response.

Useful for out-of-context tasks like summarization, classification,
extraction, or any secondary LLM call that shouldn't consume main context.
"""

import json
import urllib.request
import urllib.error

from ._config import get_config


class LlmQueryTool:
    name = "llm_query"
    description = "Query a local LLM via Ollama for out-of-context analysis"
    system_prompt = (
        "## llm_query\n"
        "Sends a prompt to a local LLM (via Ollama) and returns the response.\n"
        "Use this for out-of-context tasks like summarization, classification, "
        "extraction, or any secondary analysis that shouldn't consume main context.\n"
        "Parameters (JSON object):\n"
        "- prompt (string, required): The prompt to send\n"
        "- model (string, optional): Ollama model name (default from config)\n"
        "- system (string, optional): System prompt for the LLM\n"
        "- temperature (float, optional, default 0.3): Sampling temperature\n"
        "- max_tokens (integer, optional): Max tokens to generate\n"
        "- json_mode (boolean, optional): Force JSON output\n"
    )

    def execute(self, params, workdir=None):
        config = get_config()
        prompt = params.get("prompt")
        if not prompt:
            return "[Error: 'prompt' parameter is required]"
        model = params.get("model", config.get("llm_query", {}).get("model", "kimi-k2.5:cloud"))
        system = params.get("system")
        temperature = params.get("temperature", config.get("llm_query", {}).get("temperature", 0.3))
        max_tokens = params.get("max_tokens")
        json_mode = params.get("json_mode", False)

        try:
            result = llm_query(
                prompt=prompt,
                model=model,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            return result
        except Exception as e:
            return f"[LLM query error: {e}]"


def llm_query(
    prompt: str,
    model: str = None,
    system: str = None,
    temperature: float = None,
    max_tokens: int = None,
    timeout: int = None,
    json_mode: bool = False,
    ollama_url: str = None,
) -> str:
    """Send a prompt to a local Ollama model and return the response text.

    This is the core function that can also be used as a library by other tools.
    """
    config = get_config()
    llm_cfg = config.get("llm_query", {})
    model = model or llm_cfg.get("model", "kimi-k2.5:cloud")
    temperature = temperature if temperature is not None else llm_cfg.get("temperature", 0.3)
    timeout = timeout or llm_cfg.get("timeout", 120)
    ollama_url = ollama_url or llm_cfg.get("api_url", "http://localhost:11434")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }

    if json_mode:
        payload["format"] = "json"
    if max_tokens:
        payload["options"]["num_predict"] = max_tokens

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result.get("message", {}).get("content", "").strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise RuntimeError(f"Ollama HTTP {e.code}: {e.reason} — {body[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama connection error: {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")
