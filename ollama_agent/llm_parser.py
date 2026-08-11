"""LLM-based fallback parser for suspicious regex parse results.

When the regex parser detects potential truncation (risky markers in fences,
empty params, JSON errors, unclosed blocks), this module can invoke a
configurable "Parser LLM" to verify or correct the parse.

The Parser LLM is asked simple questions:
1. How many action invocations are in the response?
2. For each invocation: what type? what name? what params?

Results are compared with the regex parser's output. If they match,
the regex result is trusted. If they differ, the LLM result is used
and a warning is logged.
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

# System prompt aligned with the app's markup syntax
PARSER_SYSTEM_PROMPT = """You are a precise parser. You extract structured information from another AI assistant's output.

The output uses a custom markup syntax for action blocks. Here are the exact rules:

## WRITE blocks
Format:
**WRITE:`hello.py`**
```python
print('hello')
```
**EOF:`hello.py`**
The path in WRITE and EOF must match exactly.

## EDIT blocks
Format:
**EDIT:`hello.py`**
```search-replace
<<<<<<< SEARCH
old code to find
=======
new code to replace with
>>>>>>> REPLACE
```
**EOF:`hello.py`**

## FILE blocks (read)
Format:
**FILE:`README.md`**
```markdown
# Title
```
**EOF:`README.md`**

## RUN blocks
Format:
**RUN:**
```cmd
python hello.py
```
No EOF marker for RUN.

## TOOL blocks
Format:
**TOOL:`read_file`**
```json
{"path": "src/app.py"}
```
**EOF:`read_file`**
The EOF path is the TOOL NAME. JSON params are required.

## SKILL blocks
Format:
**SKILL:`architect`**
```json
{"task": "design a system"}
```
**EOF:`architect`**

## Critical parsing rules
- Markers must start on a NEW LINE.
- EOF markers close the current block.
- Content inside ``` fenced code blocks is opaque — markers inside fences are CONTENT, not real markers.
- A response may contain multiple action blocks.

Rules for your output:
- Return ONLY what is asked. No explanations.
- When asked for content, return the EXACT text, character for character.
- When asked for a count, return a single number.
- When asked for JSON, return valid JSON only.
- When asked for a type, return one word: WRITE, EDIT, FILE, TOOL, SKILL, or RUN.
"""


def _call_llm(base_url, model, system_prompt, user_prompt, timeout=60, api_type="ollama", api_key="ollama"):
    """Call LLM API (Ollama native or OpenAI-compatible)."""
    import urllib.request
    import urllib.error

    if api_type == "openai":
        # OpenAI-compatible endpoint
        url = f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "temperature": 0.1,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
    else:
        # Ollama native API
        url = f"{base_url.rstrip('/')}/api/chat"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.1},
        }
        headers = {"Content-Type": "application/json"}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if api_type == "openai":
                return result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return result.get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.warning("LLM parser call failed: %s", e)
        return None


def _llm_count_actions(base_url, model, text, timeout=60, api_type="ollama", api_key="ollama"):
    """Ask LLM how many action invocations are in the text."""
    prompt = (
        f"Here is an AI assistant's response to parse:\n\n"
        f"<response>\n{text}\n</response>\n\n"
        f"How many action invocations (WRITE, EDIT, FILE, TOOL, SKILL, or RUN blocks) "
        f"are in this response? Return ONLY a single number."
    )
    resp = _call_llm(base_url, model, PARSER_SYSTEM_PROMPT, prompt, timeout=timeout, api_type=api_type, api_key=api_key)
    if resp is None:
        return None
    try:
        return int(resp.strip())
    except ValueError:
        m = re.search(r'\d+', resp)
        return int(m.group()) if m else None


def _llm_action_type(base_url, model, text, index, timeout=60, api_type="ollama", api_key="ollama"):
    """Ask LLM the type of the Nth invocation."""
    prompt = (
        f"Here is an AI assistant's response to parse:\n\n"
        f"<response>\n{text}\n</response>\n\n"
        f"What type is invocation #{index}? "
        f"Return ONLY one word: WRITE, EDIT, FILE, TOOL, SKILL, or RUN."
    )
    resp = _call_llm(base_url, model, PARSER_SYSTEM_PROMPT, prompt, timeout=timeout, api_type=api_type, api_key=api_key)
    return resp.strip().upper() if resp else None


def _llm_tool_name(base_url, model, text, index, timeout=60, api_type="ollama", api_key="ollama"):
    """Ask LLM the tool name for the Nth TOOL invocation."""
    prompt = (
        f"Here is an AI assistant's response to parse:\n\n"
        f"<response>\n{text}\n</response>\n\n"
        f"What is the tool name for TOOL invocation #{index}? "
        f"Return ONLY the name, nothing else."
    )
    resp = _call_llm(base_url, model, PARSER_SYSTEM_PROMPT, prompt, timeout=timeout, api_type=api_type, api_key=api_key)
    return resp.strip() if resp else None


def _llm_tool_params(base_url, model, text, index, timeout=60, api_type="ollama", api_key="ollama"):
    """Ask LLM to extract JSON params for the Nth TOOL invocation."""
    prompt = (
        f"Here is an AI assistant's response to parse:\n\n"
        f"<response>\n{text}\n</response>\n\n"
        f"Extract the JSON parameters for TOOL invocation #{index}. "
        f"Return ONLY the raw JSON object, exactly as it appeared. "
        f"Do not modify the JSON in any way."
    )
    resp = _call_llm(base_url, model, PARSER_SYSTEM_PROMPT, prompt, timeout=timeout, api_type=api_type, api_key=api_key)
    if resp is None:
        return None
    try:
        return json.loads(resp)
    except json.JSONDecodeError:
        return None


def should_trigger_fallback(actions, risky_markers, missing_eof_paths):
    """Determine if LLM fallback parsing should be triggered.

    Returns True if any suspicious signal is detected.
    """
    # Risky markers inside fenced content
    if risky_markers:
        return True

    # Unclosed blocks
    if missing_eof_paths:
        return True

    # Empty params or JSON errors on tool/skill actions
    for action in actions:
        if action.get("type") in ("tool", "skill"):
            if action.get("json_error"):
                return True
            if not action.get("params"):
                return True

    return False


def llm_parse_actions(base_url, model, text, timeout=60, api_type="ollama", api_key="ollama"):
    """Use LLM to parse actions from text.

    Returns a list of parsed action dicts, or None on failure.
    """
    count = _llm_count_actions(base_url, model, text, timeout=timeout, api_type=api_type, api_key=api_key)
    if count is None:
        return None

    if count > 20:
        logger.warning("LLM parser reported %d actions — capping at 20", count)
        count = 20

    results = []
    for idx in range(1, count + 1):
        action_type = _llm_action_type(base_url, model, text, idx, timeout=timeout, api_type=api_type, api_key=api_key)
        if action_type is None:
            results.append({"type": "unknown", "index": idx})
            continue

        action = {"type": action_type.lower(), "index": idx}

        if action_type == "TOOL":
            action["name"] = _llm_tool_name(base_url, model, text, idx, timeout=timeout, api_type=api_type, api_key=api_key)
            action["params"] = _llm_tool_params(base_url, model, text, idx, timeout=timeout, api_type=api_type, api_key=api_key)
        elif action_type == "WRITE":
            # For WRITE, we only extract the path — code content is too large
            # and risks mutation. The regex parser handles code content fine
            # once the block boundaries are correct.
            prompt = (
                f"Here is an AI assistant's response to parse:\n\n"
                f"<response>\n{text}\n</response>\n\n"
                f"What is the file path for WRITE invocation #{idx}? "
                f"Return ONLY the path, nothing else."
            )
            resp = _call_llm(base_url, model, PARSER_SYSTEM_PROMPT, prompt, timeout=timeout, api_type=api_type, api_key=api_key)
            action["path"] = resp.strip() if resp else None
        elif action_type == "EDIT":
            prompt = (
                f"Here is an AI assistant's response to parse:\n\n"
                f"<response>\n{text}\n</response>\n\n"
                f"What is the file path for EDIT invocation #{idx}? "
                f"Return ONLY the path, nothing else."
            )
            resp = _call_llm(base_url, model, PARSER_SYSTEM_PROMPT, prompt, timeout=timeout, api_type=api_type, api_key=api_key)
            action["path"] = resp.strip() if resp else None

        results.append(action)

    return results


def compare_and_merge(regex_actions, llm_actions):
    """Compare regex and LLM parse results.

    Returns (corrected_actions, warnings_list).
    If LLM result is trustworthy, uses it for tool params.
    Otherwise, keeps regex result.
    """
    warnings = []

    if llm_actions is None:
        return regex_actions, ["[LLM parser unavailable — using regex result]"]

    if len(regex_actions) != len(llm_actions):
        warnings.append(
            f"[LLM parser count mismatch: regex={len(regex_actions)}, "
            f"llm={len(llm_actions)} — using regex result]"
        )
        return regex_actions, warnings

    corrected = []
    for i, (r_act, l_act) in enumerate(zip(regex_actions, llm_actions)):
        r_type = r_act.get("type", "").lower()
        l_type = l_act.get("type", "").lower()

        if r_type != l_type:
            warnings.append(
                f"[Action {i+1}: type mismatch regex={r_type} llm={l_type} — using regex]"
            )
            corrected.append(r_act)
            continue

        if r_type == "tool":
            r_params = r_act.get("params", {})
            l_params = l_act.get("params")

            if not r_params and l_params:
                # Regex produced empty params, LLM has real params — use LLM
                warnings.append(
                    f"[Action {i+1}: regex params empty, LLM recovered params "
                    f"for tool '{r_act.get('name')}' — using LLM result]"
                )
                r_act["params"] = l_params
                r_act.pop("json_error", None)
            elif r_params and l_params and r_params != l_params:
                warnings.append(
                    f"[Action {i+1}: params differ between regex and LLM — using regex]"
                )

        corrected.append(r_act)

    return corrected, warnings
