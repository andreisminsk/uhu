"""llm_chat tool — bounded multi-round consultation with another LLM.

The consultant is non-agentic (text only, no tools). Session state is kept
inside the tool so only each response enters the main model's context.
"""

import json
import time
import uuid
import urllib.request
import urllib.error

from ._config import get_config

# ── Session store ─────────────────────────────────────────────────────

_sessions = {}
_MAX_SESSIONS = 3
_SESSION_TTL = 600  # 10 minutes
_HARD_ROUND_CAP = 10
_DEFAULT_MAX_ROUNDS = 5
_MAX_RESPONSE_CHARS = 2000


def _prune_expired():
    """Remove sessions older than TTL."""
    now = time.time()
    expired = [sid for sid, s in _sessions.items() if now - s["created_at"] > _SESSION_TTL]
    for sid in expired:
        del _sessions[sid]


def _truncate(text, limit=_MAX_RESPONSE_CHARS):
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... {len(text)} chars total, truncated]"


def _call_ollama(messages, model, temperature, timeout, ollama_url):
    """Send messages to Ollama /api/chat and return the response text."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
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


class LlmChatTool:
    name = "llm_chat"
    description = "Consult another LLM in a bounded multi-round conversation"
    system_prompt = """## llm_chat

Consult another LLM in a bounded multi-round conversation. The consultant
is NOT agentic — it can only think and respond, not invoke tools.

Use this when you are stuck after multiple failed attempts and need a
fresh perspective from a more capable model. Distill the problem into a
clean description — don't dump your full context.

Actions:
- start: Begin a consultation. Provide a system prompt defining the
  consultant's role, and a curated problem description.
  Params: action, system, message, model (optional), max_rounds (optional, default 5)
- send: Continue the conversation. Use extend=N to add rounds when
  you hit the limit.
  Params: action, session_id, message, extend (optional)
- end: End the consultation and get a final synthesis.
  Params: action, session_id

Default limit: 5 rounds. Max extension: 10 total rounds.
Sessions auto-expire after 10 minutes. Max 3 concurrent sessions.

Examples:
- {"action": "start", "system": "You are a senior software architect...", "message": "The problem is: ..."}
- {"action": "send", "session_id": "abc123", "message": "What about edge case X?"}
- {"action": "send", "session_id": "abc123", "message": "One more thing...", "extend": 2}
- {"action": "end", "session_id": "abc123"}"""
    parameters = {
        "action": {"type": "string", "required": True, "description": "start, send, or end"},
        "session_id": {"type": "string", "required": False, "description": "Session ID (for send/end)"},
        "system": {"type": "string", "required": False, "description": "System prompt defining the consultant's role (for start)"},
        "message": {"type": "string", "required": False, "description": "Message to send (for start/send)"},
        "model": {"type": "string", "required": False, "description": "Ollama model name (default from config)"},
        "max_rounds": {"type": "integer", "required": False, "description": "Max rounds (default 5, hard cap 10)"},
        "extend": {"type": "integer", "required": False, "description": "Add N rounds to the limit (for send)"},
    }

    def execute(self, params, workdir=None):
        action = params.get("action", "").strip().lower()
        if action == "start":
            return self._start(params, workdir)
        elif action == "send":
            return self._send(params, workdir)
        elif action == "end":
            return self._end(params, workdir)
        else:
            return {"error": f"Unknown action '{action}'. Use 'start', 'send', or 'end'."}

    def _start(self, params, workdir):
        _prune_expired()
        if len(_sessions) >= _MAX_SESSIONS:
            # Evict oldest
            oldest = min(_sessions, key=lambda s: _sessions[s]["created_at"])
            del _sessions[oldest]

        system = params.get("system", "")
        message = params.get("message", "")
        if not message:
            return {"error": "'message' is required for start action."}

        config = get_config()
        llm_cfg = config.get("llm_query", {})
        model = params.get("model") or llm_cfg.get("model", "glm-5.3:cloud")
        temperature = llm_cfg.get("temperature", 0.3)
        timeout = llm_cfg.get("timeout", 300)
        ollama_url = llm_cfg.get("api_url", "http://localhost:11434")

        max_rounds = params.get("max_rounds", _DEFAULT_MAX_ROUNDS)
        try:
            max_rounds = int(max_rounds)
        except (ValueError, TypeError):
            max_rounds = _DEFAULT_MAX_ROUNDS
        max_rounds = min(max_rounds, _HARD_ROUND_CAP)

        session_id = uuid.uuid4().hex[:8]
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": message})

        try:
            response = _call_ollama(messages, model, temperature, timeout, ollama_url)
        except Exception as e:
            return {"error": str(e)}

        messages.append({"role": "assistant", "content": response})
        _sessions[session_id] = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "timeout": timeout,
            "ollama_url": ollama_url,
            "max_rounds": max_rounds,
            "round": 1,
            "created_at": time.time(),
        }

        return {
            "session_id": session_id,
            "response": _truncate(response),
            "round": f"1/{max_rounds}",
        }

    def _send(self, params, workdir=None):
        _prune_expired()
        session_id = params.get("session_id", "").strip()
        if not session_id or session_id not in _sessions:
            return {"error": f"Session not found: {session_id}. Use 'start' to begin a consultation."}

        session = _sessions[session_id]
        message = params.get("message", "")
        if not message:
            return {"error": "'message' is required for send action."}

        # Handle round extension
        extend = params.get("extend", 0)
        try:
            extend = int(extend)
        except (ValueError, TypeError):
            extend = 0
        if extend > 0:
            session["max_rounds"] = min(session["max_rounds"] + extend, _HARD_ROUND_CAP)

        # Check round limit
        if session["round"] >= session["max_rounds"]:
            return {
                "session_id": session_id,
                "error": "Round limit reached. Use extend=N to add rounds, or action=end to finish.",
                "round": f"{session['round']}/{session['max_rounds']}",
                "limit_reached": True,
            }

        session["messages"].append({"role": "user", "content": message})

        try:
            response = _call_ollama(
                session["messages"], session["model"],
                session["temperature"], session["timeout"],
                session["ollama_url"],
            )
        except Exception as e:
            # Remove the message we just added since the call failed
            session["messages"].pop()
            return {"error": str(e), "session_id": session_id}

        session["messages"].append({"role": "assistant", "content": response})
        session["round"] += 1

        result = {
            "session_id": session_id,
            "response": _truncate(response),
            "round": f"{session['round']}/{session['max_rounds']}",
        }
        if session["round"] >= session["max_rounds"]:
            result["limit_reached"] = True
            result["note"] = "Round limit reached. Use extend=N to add rounds, or action=end to finish."
        return result

    def _end(self, params, workdir=None):
        _prune_expired()
        session_id = params.get("session_id", "").strip()
        if not session_id or session_id not in _sessions:
            return {"error": f"Session not found: {session_id}."}

        session = _sessions[session_id]

        # Ask consultant for a synthesis
        synthesis_prompt = (
            "Please provide a concise summary of the key takeaways and actionable "
            "recommendations from this consultation. Focus on what the main agent "
            "should do next."
        )
        session["messages"].append({"role": "user", "content": synthesis_prompt})

        try:
            summary = _call_ollama(
                session["messages"], session["model"],
                session["temperature"], session["timeout"],
                session["ollama_url"],
            )
        except Exception as e:
            summary = f"[Synthesis failed: {e}]"

        rounds = session["round"]
        del _sessions[session_id]

        return {
            "session_id": session_id,
            "summary": _truncate(summary, 3000),
            "rounds": rounds,
        }