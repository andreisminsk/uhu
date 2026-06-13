#!/usr/bin/env python3
"""Test that models understand tool system prompts and produce correct block format.

Uses llm_query to send prompts to a model and checks the output for:
- Correct TOOL block format (signal + json + EOF)
- EOF uses tool name, not file path
- No bare signal lines without content
- Correct JSON params structure
"""

import json
import os
import re
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Tool block pattern components
TOOL_SIGNAL = re.compile(r'\*\*TOOL:\*\*\s*`([^`]+)`|\*\*TOOL:\s*`([^`]+)`\s*\*\*')
EOF_SIGNAL = re.compile(
    r'\*\*EOF:\*\*\s*`([^`]+)`'
    r'|\*\*EOF:\s*`([^`]+)`\s*\*\*'
    r'|\*\*EOF:\*\*\s*([^\s`*]+)'
    r'|\*\*EOF:\s*`([^`]+)`'
)
JSON_FENCE = re.compile(r'```json\s*\n(.*?)\n```', re.DOTALL)
BARE_TOOL = re.compile(r'\*\*TOOL:\*\*\s*`([^`]+)`\s*$|\*\*TOOL:\s*`([^`]+)`\s*\*\*\s*$', re.MULTILINE)


def extract_tool_blocks(text):
    """Extract all tool blocks from model output. Returns list of {name, params, eof_name, raw}."""
    blocks = []
    # Find all TOOL signals
    for m in TOOL_SIGNAL.finditer(text):
        tool_name = m.group(1) or m.group(2)
        start = m.end()
        # Find the corresponding EOF
        eof_match = None
        for em in EOF_SIGNAL.finditer(text, start):
            eof_name = em.group(1) or em.group(2) or em.group(3) or em.group(4)
            if eof_name:
                eof_match = (em, eof_name)
                break
        if not eof_match:
            blocks.append({"name": tool_name, "params": None, "eof_name": None, "raw": text[start:start+200]})
            continue
        # Extract content between TOOL signal and EOF
        between = text[start:eof_match[0].start()]
        # Try to find JSON params
        json_match = JSON_FENCE.search(between)
        params = None
        if json_match:
            try:
                params = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                params = f"INVALID_JSON: {json_match.group(1)[:100]}"
        blocks.append({
            "name": tool_name,
            "params": params,
            "eof_name": eof_match[1],
            "raw": between[:200],
        })
    return blocks


def check_bare_signals(text):
    """Check for bare TOOL signals without JSON content blocks."""
    bare = []
    for m in TOOL_SIGNAL.finditer(text):
        tool_name = m.group(1) or m.group(2)
        start = m.end()
        # Check if there's a json fence within next 500 chars
        after = text[start:start+500]
        if not JSON_FENCE.search(after):
            bare.append(tool_name)
    return bare


# ── Test definitions ──────────────────────────────────────────────────

TESTS = [
    {
        "name": "basic_read_file",
        "prompt": "Read the file README.md using the read_file tool.",
        "expect_tool": "read_file",
        "expect_params": {"path": "README.md"},
        "check": lambda b: (
            b["name"] == "read_file"
            and b["params"] is not None
            and isinstance(b["params"], dict)
            and b["params"].get("path", "").lower() in ("readme.md", "./readme.md")
            and b["eof_name"] == "read_file"
        ),
    },
    {
        "name": "eof_uses_tool_name",
        "prompt": "Use the search_in_files tool to find 'def execute' in Python files.",
        "expect_tool": "search_in_files",
        "check": lambda b: (
            b["name"] == "search_in_files"
            and b["eof_name"] == "search_in_files"
            and b["params"] is not None
        ),
    },
    {
        "name": "list_files_tool",
        "prompt": "List files in the current directory using the list_files tool.",
        "expect_tool": "list_files",
        "check": lambda b: (
            b["name"] == "list_files"
            and b["eof_name"] == "list_files"
            and b["params"] is not None
        ),
    },
    {
        "name": "git_status_tool",
        "prompt": "Show git status using the git tool.",
        "expect_tool": "git",
        "check": lambda b: (
            b["name"] == "git"
            and b["eof_name"] == "git"
            and b["params"] is not None
            and b["params"].get("action") == "status"
        ),
    },
    {
        "name": "write_file_tool",
        "prompt": "Create a file called test.txt with content 'hello world' using the write_file tool.",
        "expect_tool": "write_file",
        "check": lambda b: (
            b["name"] == "write_file"
            and b["eof_name"] == "write_file"
            and b["params"] is not None
            and b["params"].get("path") is not None
            and b["params"].get("content") is not None
        ),
    },
    {
        "name": "multiple_tools",
        "prompt": "First list files in the src directory, then read the file src/main.py.",
        "expect_tools": ["list_files", "read_file"],
        "check": lambda blocks: (
            len(blocks) >= 2
            and blocks[0]["name"] == "list_files"
            and blocks[1]["name"] == "read_file"
            and all(b["params"] is not None for b in blocks[:2])
            and all(b["eof_name"] == b["name"] for b in blocks[:2])
        ),
    },
    {
        "name": "no_bare_signals",
        "prompt": "Read the file constants.py using the read_file tool.",
        "check_bare": True,
    },
    {
        "name": "env_info_tool",
        "prompt": "Check if the 'requests' package is installed using the env_info tool.",
        "expect_tool": "env_info",
        "check": lambda b: (
            b["name"] == "env_info"
            and b["eof_name"] == "env_info"
            and b["params"] is not None
            and b["params"].get("check") is not None
        ),
    },
    {
        "name": "run_command_tool",
        "prompt": "Run 'echo hello' using the run_command tool.",
        "expect_tool": "run_command",
        "check": lambda b: (
            b["name"] == "run_command"
            and b["eof_name"] == "run_command"
            and b["params"] is not None
            and b["params"].get("command") is not None
        ),
    },
    {
        "name": "replace_in_file_tool",
        "prompt": "Replace 'old_text' with 'new_text' in config.py using the replace_in_file tool.",
        "expect_tool": "replace_in_file",
        "check": lambda b: (
            b["name"] == "replace_in_file"
            and b["eof_name"] == "replace_in_file"
            and b["params"] is not None
            and b["params"].get("path") is not None
            and b["params"].get("replacements") is not None
        ),
    },
]


def run_tests(model="minimax-m3:cloud"):
    """Run all tests against the specified model."""
    from ollama_agent.tools.llm_query import LlmQueryTool

    # Build the tools system prompt
    from ollama_agent.tools import tools_system_prompt
    tool_prompt = tools_system_prompt()

    system_prompt = (
        "You are a concise coding assistant with file access.\n\n"
        + tool_prompt
    )

    tool = LlmQueryTool()
    results = []
    passed = 0
    failed = 0

    print(f"Testing model: {model}")
    print(f"System prompt length: {len(system_prompt)} chars")
    print(f"Running {len(TESTS)} tests...\n")
    print("=" * 70)

    for test in TESTS:
        name = test["name"]
        prompt = test["prompt"]
        print(f"\n--- {name} ---")
        print(f"Prompt: {prompt}")

        try:
            result = tool.execute({
                "prompt": prompt,
                "system": system_prompt,
                "model": model,
                "temperature": 0.1,
                "max_tokens": 500,
            })
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"name": name, "status": "ERROR", "detail": str(e)})
            failed += 1
            continue

        # Truncate display
        display = result[:300] + ("..." if len(result) > 300 else "")
        print(f"Output: {display}")

        # Check for bare signals
        if test.get("check_bare"):
            bare = check_bare_signals(result)
            if bare:
                print(f"FAIL: Bare TOOL signals without JSON: {bare}")
                results.append({"name": name, "status": "FAIL", "detail": f"Bare signals: {bare}"})
                failed += 1
            else:
                print("PASS: No bare signals")
                results.append({"name": name, "status": "PASS", "detail": ""})
                passed += 1
            continue

        # Extract tool blocks
        blocks = extract_tool_blocks(result)

        if not blocks:
            print(f"FAIL: No tool blocks found in output")
            results.append({"name": name, "status": "FAIL", "detail": "No tool blocks found"})
            failed += 1
            continue

        # Check multiple-tools test
        if "expect_tools" in test:
            check_fn = test["check"]
            if check_fn(blocks):
                print(f"PASS: Found {len(blocks)} tool blocks, all correct")
                results.append({"name": name, "status": "PASS", "detail": ""})
                passed += 1
            else:
                details = []
                for b in blocks:
                    details.append(f"name={b['name']}, eof={b['eof_name']}, params={'ok' if b['params'] else 'MISSING'}")
                print(f"FAIL: {details}")
                results.append({"name": name, "status": "FAIL", "detail": str(details)})
                failed += 1
            continue

        # Single tool check
        block = blocks[0]
        check_fn = test.get("check")
        if check_fn and check_fn(block):
            eof_ok = block["eof_name"] == block["name"]
            params_ok = block["params"] is not None and not isinstance(block["params"], str)
            print(f"PASS: name={block['name']}, eof={block['eof_name']}, params={'ok' if params_ok else 'ISSUE'}")
            if not eof_ok:
                print(f"  WARNING: EOF name '{block['eof_name']}' != tool name '{block['name']}'")
            results.append({"name": name, "status": "PASS", "detail": ""})
            passed += 1
        else:
            details = f"name={block['name']}, eof={block['eof_name']}, params={block['params']}"
            if block["params"] is None:
                details += " [NO JSON PARAMS]"
            if block["eof_name"] != block["name"]:
                details += f" [EOF MISMATCH: expected {block['name']}, got {block['eof_name']}]"
            print(f"FAIL: {details}")
            results.append({"name": name, "status": "FAIL", "detail": details})
            failed += 1

        # Rate limit
        time.sleep(1)

    # Summary
    print("\n" + "=" * 70)
    print(f"\nResults: {passed} passed, {failed} failed out of {len(TESTS)} tests")
    print()

    # Group by status
    fails = [r for r in results if r["status"] != "PASS"]
    if fails:
        print("Failures:")
        for r in fails:
            print(f"  {r['name']}: {r['detail']}")
        print()

    return results


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "minimax-m3:cloud"
    run_tests(model)
