"""Shared normalizer for native LLM tool_calls (Phase 1, NATIVE-TOOL-CALLS-ARCH).

Native function-calling models respond via the API's structured tool_calls
channel instead of (or in addition to) text action blocks. Both backends and
model_test normalize raw payloads through this module into a uniform contract:

    [{"name": str, "params": dict}]

Handles:
- native Ollama format: {"function": {"name": ..., "arguments": dict}}
- OpenAI-compatible /v1 format: {"function": {"name": ..., "arguments": "<json str>"}}
- flat formats: {"name": ..., "arguments": ...}
- pydantic objects (attribute access)
- malformed payloads degrade to {"_raw": ...} instead of raising
"""

import json
import re

__all__ = ["normalize_tool_calls", "merge_tool_call_fragments"]

# Native names longer than this are almost certainly channel-mixing blobs
# (field, 2026-11-08, glm-5.3-flash:cloud: a text RUN block + prose poured
# into the name slot during a failed-call recovery). Real tool names are
# short; degrade instead of passing the blob to the registry.
_MAX_NATIVE_NAME_LEN = 64

# Marker-wrapped native tool names (field, 2026-11-08, mistral-large-4:cloud):
# the model emitted "TOOL:`py_compile`" — uhu's TEXT action syntax glued
# around the real name — as the native tool name. Strip the text-marker
# wrapper so the call resolves instead of failing as "Unknown tool".
_MARKER_NAME_RE = re.compile(r"^(?:TOOL|SKILL)\s*:\s*`?([^`]+?)`?\s*$")


def _clean_native_name(name):
    """Strip text-marker syntax from a native tool name (see _MARKER_NAME_RE)."""
    m = _MARKER_NAME_RE.match(name.strip())
    if m:
        return m.group(1).strip()
    return name.strip()


# Text-action markers in the native name slot (NATIVE-TOOLS-SWITCH-ARCH,
# session 2 — hybrid-with-backup): a name like "WRITE:`hello.py`" means the
# model tried to issue a text action on the native channel. Detected (not
# auto-executed — the name slot may be truncated) and surfaced as a steering
# entry so the pipeline can tell the model to re-emit as a text block or call
# the backup tool.
_TEXT_ACTION_MARKER_RE = re.compile(r"^(?:WRITE|EDIT|FILE|RUN)\s*[:`]", re.IGNORECASE)


def looks_like_text_action(name):
    """True when a native tool name starts with a text-action marker
    (WRITE:/EDIT:/FILE:/RUN:) — channel-mixing, needs steering (see
    _TEXT_ACTION_MARKER_RE)."""
    return bool(_TEXT_ACTION_MARKER_RE.match(name.strip()))

# Param keys that are structurally list/dict. Some native-calling models
# JSON-encode these nested values as strings (observed live on beam:cloud:
# replace_in_file with "replacements": "[{\"search\": ..., \"replace\": ...}]").
# Coercion is key-scoped and conservative — free-form strings (e.g. file
# content passed to write_file) must keep their string type even if they
# happen to parse as JSON.
_STRUCTURED_PARAM_KEYS = {"replacements"}


def normalize_tool_calls(raw):
    """Normalize raw tool_calls (dicts or pydantic objects) to
    [{"name": str, "params": dict}]. Handles both native-Ollama format
    (arguments as dict) and OpenAI-compat format (arguments as JSON string).
    Malformed entries are skipped; string payloads that fail to parse are
    wrapped in {"_raw": ...} so callers can still match on name."""
    out = []
    for tc in raw or []:
        if isinstance(tc, dict):
            fn = tc.get("function") or {}
            name = fn.get("name") or tc.get("name")
            args = fn.get("arguments")
            if args is None:
                args = tc.get("arguments")
        else:
            fn = getattr(tc, "function", None)
            name = getattr(fn, "name", None) or getattr(tc, "name", None)
            args = getattr(fn, "arguments", None)
            if args is None:
                args = getattr(tc, "arguments", None)
        if not name:
            continue
        # Text-action marker in the native name slot (hybrid mode): the model
        # tried to emit FILE:/WRITE:/EDIT:/RUN: as a function/tool call instead
        # of plain assistant text. Detect this BEFORE the long-name guard so a
        # full text block like "EDIT:`file`\n```search-replace..." is reported
        # as channel mixing, not a generic malformed native call.
        if looks_like_text_action(name):
            out.append({"name": "_text_action_mixing",
                        "params": {"_raw": name[:512]}})
            continue
        # Channel-mixing / corruption blob in the name slot (see
        # _MAX_NATIVE_NAME_LEN): degrade to a _raw-style entry so the pipeline
        # reports a clear, actionable failure instead of "Unknown tool
        # '<500-char blob>'".
        if len(name) > _MAX_NATIVE_NAME_LEN:
            out.append({"name": "_malformed_native_call",
                        "params": {"_raw": name[:512]}})
            continue
        name = _clean_native_name(str(name))
        if not name:
            continue
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {"_raw": args}
        if args is None:
            args = {}
        if not isinstance(args, dict):
            try:
                args = dict(args)
            except Exception:
                args = {"_raw": args}
        for key in _STRUCTURED_PARAM_KEYS.intersection(args):
            val = args[key]
            if isinstance(val, str) and val[:1] in ("[", "{"):
                try:
                    parsed = json.loads(val)
                except ValueError:
                    parsed = None
                if isinstance(parsed, (list, dict)):
                    args[key] = parsed
        out.append({"name": name, "params": args})
    return out


def merge_tool_call_fragments(fragments):
    """Merge streamed tool_call fragments into complete raw calls.

    Streaming /v1 delivers tool_calls as delta fragments: {"index": N,
    "function": {"name": partial, "arguments": partial_str}}. Native Ollama
    chunks may carry complete calls (final-chunk delivery, observed) or
    fragments — this merge is required on /v1, defensive on native.
    Keyed by index when present (OpenAI format). No-index entries (native
    format): a named fragment starts a new call; a nameless fragment is a
    continuation of the previous call (dict arguments extend field-by-field —
    native format delivers dict args, possibly spread across chunks).

    Returns raw merged calls — run normalize_tool_calls() on the result.
    """
    merged = {}
    order = []
    for tc in fragments or []:
        if isinstance(tc, dict):
            index = tc.get("index")
            fn = tc.get("function") or {}
            name = fn.get("name")
            args = fn.get("arguments")
            tc_id = tc.get("id")
        else:
            index = getattr(tc, "index", None)
            fn = getattr(tc, "function", None)
            name = getattr(fn, "name", None)
            args = getattr(fn, "arguments", None)
            tc_id = getattr(tc, "id", None)
        if index is not None:
            key = index
        elif not name and order:
            key = order[-1]  # nameless no-index fragment continues previous call
        else:
            key = len(order)  # named no-index fragment starts a new call
        if key not in merged:
            merged[key] = {"id": tc_id, "name": "", "args_str": "", "args_dict": {}}
            order.append(key)
        acc = merged[key]
        if isinstance(name, str):
            acc["name"] += name
        elif name and not acc["name"]:
            acc["name"] = name
        if isinstance(args, str):
            acc["args_str"] += args
        elif isinstance(args, dict):
            acc["args_dict"].update(args)
        elif args is not None:
            acc["args_dict"] = args
    result = []
    for key in order:
        acc = merged[key]
        if acc["args_str"]:
            args = acc["args_str"]  # OpenAI format: JSON string
        else:
            args = acc["args_dict"]  # native format: dict ({} when no args)
        call = {"function": {"name": acc["name"], "arguments": args}}
        if acc["id"]:
            call["id"] = acc["id"]
        call["index"] = key
        result.append(call)
    return result
