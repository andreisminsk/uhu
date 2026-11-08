#!/usr/bin/env python3
"""PoC: motivate native tool_calls on /api/chat (NATIVE-TOOLS-SWITCH-ARCH.md).

Investigates what it takes to make a text-protocol-respecting model
(default target: glm-5.3-flash:cloud) emit native `message.tool_calls`
instead of text action blocks — groundwork for a future --no-text-tools CLI option.

Three conditions, same task prompt:
  A baseline — full uhu text-protocol system prompt, NO tools param (today's behavior)
  B tools    — full uhu text-protocol system prompt, tools param sent
  C stripped — minimal system prompt (no text-protocol docs), tools param sent

Classification per response:
  native — message.tool_calls non-empty
  text   — content contains text action markers (TOOL/SKILL/WRITE/EDIT/RUN/FILE)
  none   — neither

--rounds 2 adds a history-consistency check: when a condition goes native,
a synthetic tool result is fed back (assistant tool_calls + role:"tool"
messages, the _wire_tool_results shape) and the model is re-asked — does it
STAY on the native channel?

Usage:
  python tests/poc_native_tools_switch.py --model glm-5.3-flash:cloud --rounds 2
"""

import argparse
import json
import re
import urllib.error
import urllib.request

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "glm-5.3-flash:cloud"
DEFAULT_TASK = "List the files in the current directory."

# Text action markers, matched via regex so this file never contains the
# literal marker syntax (avoids tripping uhu's own action parser when this
# PoC is written or read back through the agent).
_TEXT_MARKER_RE = re.compile(r"\*\*(?:TOOL|SKILL|WRITE|EDIT|RUN|FILE)\s*:")

# Minimal JSON schemas for 3 real uhu tools (names/descriptions mirror the registry).
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories. Cross-platform replacement for dir/ls/tree.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default '.')"},
                    "recursive": {"type": "boolean", "description": "List recursively"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents. Cross-platform replacement for cat/type/head/tail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "offset": {"type": "integer", "description": "Line number to start from (1-based)"},
                    "limit": {"type": "integer", "description": "Maximum number of lines to read"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_in_files",
            "description": "Search for a regex pattern across files. Cross-platform replacement for grep/findstr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "path": {"type": "string", "description": "File or directory to search in"},
                },
                "required": ["pattern"],
            },
        },
    },
]

STRIPPED_SYSTEM_PROMPT = (
    "You are a concise coding assistant with file access.\n"
    "Use the provided tools for file operations (listing, reading, searching).\n"
    "Call a tool by emitting a tool call, then stop and wait for its result."
)


def post_chat(host, payload, timeout=180):
    """POST to /api/chat, non-streaming. Returns parsed JSON."""
    req = urllib.request.Request(
        host.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_capability(host, model):
    """Report the model's capability flags from /api/tags (tools flag)."""
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for m in data.get("models", []):
            if m.get("name") == model or m.get("model") == model:
                return m.get("capabilities") or []
    except Exception as e:
        return f"error: {e}"
    return "model not listed in /api/tags"


def full_system_prompt():
    """The real uhu system prompt (agent + tools), as sent today."""
    from ollama_agent.system_prompt import build_system_prompt
    return build_system_prompt(workdir=".", agent=True, tools=True, skills=False)


def classify(resp):
    """Classify a /api/chat response by channel: native / text / none."""
    msg = resp.get("message") or {}
    tool_calls = msg.get("tool_calls") or []
    content = msg.get("content") or ""
    channels = []
    if tool_calls:
        channels.append("native")
    if _TEXT_MARKER_RE.search(content):
        channels.append("text")
    return (channels or ["none"]), tool_calls, content


def preview(s, n=160):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s[:n] + ("..." if len(s) > n else "")


def run_round(host, model, system_prompt, task, tools_param, label):
    """Send one condition; print classification. Returns the raw response."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]
    payload = {"model": model, "messages": messages, "stream": False}
    if tools_param:
        payload["tools"] = TOOL_SCHEMAS

    print(f"\n--- {label} " + "-" * max(0, 56 - len(label)))
    print(f"    system prompt: {len(system_prompt)} chars | tools param: {tools_param}")
    try:
        resp = post_chat(host, payload)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        print(f"    HTTP {e.code}: {body}")
        return None
    except Exception as e:
        print(f"    ERROR: {e}")
        return None

    channels, tool_calls, content = classify(resp)
    thinking = (resp.get("message") or {}).get("thinking") or ""
    print(f"    channel(s): {', '.join(channels)}")
    print(f"    tokens: prompt={resp.get('prompt_eval_count')} output={resp.get('eval_count')}")
    for tc in tool_calls:
        fn = tc.get("function") or {}
        print(f"    native call: {fn.get('name')}({json.dumps(fn.get('arguments'))})")
    if content:
        print(f"    content: {preview(content)}")
    if thinking:
        print(f"    thinking: {preview(thinking, 100)}")
    return resp


def run_round2_followup(host, model, system_prompt, task, resp1):
    """History-consistency check: feed a synthetic tool result for round-1
    native calls (the _wire_tool_results wire shape), then re-ask."""
    msg1 = resp1.get("message") or {}
    calls = msg1.get("tool_calls") or []
    if not calls:
        return
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
        {"role": "assistant", "content": msg1.get("content") or "", "tool_calls": calls},
    ]
    for tc in calls:  # one tool result per call
        fn = tc.get("function") or {}
        name = fn.get("name", "")
        if name == "list_files":
            result = "README.md\nollama_agent/\ntests/\npyproject.toml"
        elif name == "read_file":
            result = "# uhu\nMinimalistic agentic coder for Ollama."
        else:
            result = "ok"
        messages.append({"role": "tool", "content": result})
    messages.append({"role": "user", "content": "Now read the file README.md."})

    payload = {"model": model, "messages": messages, "stream": False, "tools": TOOL_SCHEMAS}
    print(f"\n--- round 2 (native follow-up: tool result fed back, re-ask) " + "-" * 10)
    try:
        resp = post_chat(host, payload)
    except Exception as e:
        print(f"    ERROR: {e}")
        return
    channels, tool_calls, content = classify(resp)
    print(f"    channel(s): {', '.join(channels)}")
    for tc in tool_calls:
        fn = tc.get("function") or {}
        print(f"    native call: {fn.get('name')}({json.dumps(fn.get('arguments'))})")
    if content:
        print(f"    content: {preview(content)}")


def main():
    ap = argparse.ArgumentParser(description="PoC: native tool_calls switch probe")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--task", default=DEFAULT_TASK)
    ap.add_argument("--rounds", type=int, default=1, choices=[1, 2],
                    help="2 = also run the native follow-up round (history consistency)")
    args = ap.parse_args()

    print(f"PoC: native tool_calls switch | model={args.model} host={args.host}")
    print(f"capabilities from /api/tags: {check_capability(args.host, args.model)}")
    print(f"task: {args.task!r}")

    full = full_system_prompt()
    conditions = [
        ("A baseline: text prompt, no tools param", full, False),
        ("B: tools param + text prompt", full, True),
        ("C: tools param + stripped prompt", STRIPPED_SYSTEM_PROMPT, True),
    ]

    results = {}
    for label, prompt, tools_param in conditions:
        resp = run_round(args.host, args.model, prompt, args.task, tools_param, label)
        results[label[0]] = (resp, label, prompt)

    if args.rounds == 2:
        # Follow up on the first condition that went native (B before C).
        for key in ("B", "C"):
            resp, label, prompt = results.get(key, (None, None, None))
            if resp and "native" in classify(resp)[0]:
                run_round2_followup(args.host, args.model, prompt, args.task, resp)
                break

    print("\n" + "=" * 64)
    print("SUMMARY")
    for key in ("A", "B", "C"):
        entry = results.get(key)
        if not entry or entry[0] is None:
            print(f"  {key}: FAILED")
            continue
        channels, _, _ = classify(entry[0])
        print(f"  {entry[1]}: -> {', '.join(channels)}")
    print("Interpretation: C -> native (while A stays text) validates the switch")
    print("levers (tools param + stripped prompt) for a --no-text-tools option.")


if __name__ == "__main__":
    main()
