#!/usr/bin/env python3
"""Comprehensive model compatibility test for the ollama-chat-agentic harness.

Tests whether a model can correctly produce all action block formats:
- WRITE, EDIT, FILE, RUN, TOOL blocks
- EOF variants (standard, bare, wrong name)
- Multiple blocks in one response
- Edge cases (empty params, wrong tool names, etc.)

Usage:
    python tests/test_model_compatibility.py <model_name>
    python tests/test_model_compatibility.py minimax-m3:cloud
    python tests/test_model_compatibility.py glm-5.1:cloud
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ollama_agent.parser import parse_actions

# ── Test definitions ───────────────────────────────────────────────────

TESTS = [
    # ═══ File creation (WRITE block or write_file tool) ═══
    {
        "category": "WRITE",
        "name": "write_new_file",
        "prompt": "Create a new file called hello.py with content: print('hello world')",
        "check": lambda actions, text: (
            any(a["type"] == "write" and a["path"] == "hello.py" and "print" in a.get("code", "")
                for a in actions)
            or any(a["type"] == "tool" and a["name"] == "write_file"
                   and a.get("params", {}).get("path") == "hello.py"
                   for a in actions)
        ),
        "description": "Creates hello.py (WRITE block or write_file tool)",
    },
    {
        "category": "WRITE",
        "name": "write_with_eof",
        "prompt": "Create a new file called config.json with content: {\"key\": \"value\"}",
        "check": lambda actions, text: (
            any(a["type"] == "write" and a["path"] == "config.json" and a.get("closed")
                for a in actions)
            or any(a["type"] == "tool" and a["name"] == "write_file"
                   and a.get("params", {}).get("path") == "config.json"
                   for a in actions)
        ),
        "description": "Creates config.json (WRITE block or write_file tool)",
    },

    # ═══ File editing (EDIT block or replace_in_file tool) ═══
    {
        "category": "EDIT",
        "name": "edit_search_replace",
        "prompt": "The file app.py contains 'old_function'. Edit it to replace 'old_function' with 'new_function'.",
        "check": lambda actions, text: (
            any(a["type"] == "edit" and a["path"] == "app.py"
                for a in actions)
            or any(a["type"] == "tool" and a["name"] == "replace_in_file"
                   and a.get("params", {}).get("path") == "app.py"
                   for a in actions)
            or any(a["type"] == "tool" and a["name"] == "read_file"
                   and a.get("params", {}).get("path", "").endswith("app.py")
                   for a in actions)
        ),
        "description": "Edits or reads app.py (EDIT/replace_in_file/read_file first)",
    },
    {
        "category": "EDIT",
        "name": "edit_with_eof",
        "prompt": "The file main.py has port 8080. Edit it to change the port to 3000.",
        "check": lambda actions, text: (
            any(a["type"] == "edit" and a["path"] == "main.py" and a.get("closed")
                for a in actions)
            or any(a["type"] == "tool" and a["name"] == "replace_in_file"
                   and a.get("params", {}).get("path") == "main.py"
                   for a in actions)
            or any(a["type"] == "tool" and a["name"] == "read_file"
                   and a.get("params", {}).get("path", "").endswith("main.py")
                   for a in actions)
        ),
        "description": "Edits or reads main.py (EDIT/replace_in_file/read_file first)",
    },

    # ═══ File reading (FILE block or read_file tool) ═══
    {
        "category": "FILE",
        "name": "file_read",
        "prompt": "Read the file README.md into context",
        "check": lambda actions, text: (
            any(a["type"] == "read" and a["path"] == "README.md"
                for a in actions)
            or any(a["type"] == "tool" and a["name"] == "read_file"
                   and a.get("params", {}).get("path", "").lower() in ("readme.md", "./readme.md")
                   for a in actions)
        ),
        "description": "Reads README.md (FILE block or read_file tool)",
    },

    # ═══ RUN blocks ═══
    {
        "category": "RUN",
        "name": "run_command",
        "prompt": "Run the command 'python --version' to check the Python version",
        "check": lambda actions, text: (
            any(a["type"] == "run" and "python" in a.get("code", "")
                for a in actions)
            or any(a["type"] == "tool" and a["name"] == "run_command"
                   and "python" in a.get("params", {}).get("command", "")
                   for a in actions)
        ),
        "description": "Runs python command (RUN block or run_command tool)",
    },

    # ═══ TOOL blocks — individual tools ═══
    {
        "category": "TOOL",
        "name": "tool_read_file",
        "prompt": "Read the file src/app.py using the read_file tool",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "read_file"
                and isinstance(a.get("params"), dict)
                and "path" in a.get("params", {})
                for a in actions)
        ),
        "description": "TOOL read_file with path param",
    },
    {
        "category": "TOOL",
        "name": "tool_search_in_files",
        "prompt": "Search for 'def main' in Python files using the search_in_files tool",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "search_in_files"
                and isinstance(a.get("params"), dict)
                and "pattern" in a.get("params", {})
                for a in actions)
        ),
        "description": "TOOL search_in_files with pattern param",
    },
    {
        "category": "TOOL",
        "name": "tool_list_files",
        "prompt": "List files in the current directory using the list_files tool",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "list_files"
                and isinstance(a.get("params"), dict)
                for a in actions)
        ),
        "description": "TOOL list_files",
    },
    {
        "category": "TOOL",
        "name": "tool_find_file",
        "prompt": "Find all Python files using the find_file tool",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "find_file"
                and isinstance(a.get("params"), dict)
                and "pattern" in a.get("params", {})
                for a in actions)
        ),
        "description": "TOOL find_file with pattern param",
    },
    {
        "category": "TOOL",
        "name": "tool_peek_file",
        "prompt": "Show the beginning and end of config.yaml using the peek_file tool",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "peek_file"
                and isinstance(a.get("params"), dict)
                and "path" in a.get("params", {})
                for a in actions)
        ),
        "description": "TOOL peek_file with path param",
    },
    {
        "category": "TOOL",
        "name": "tool_git_status",
        "prompt": "Show git status using the git tool",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "git"
                and isinstance(a.get("params"), dict)
                and a.get("params", {}).get("action") == "status"
                for a in actions)
        ),
        "description": "TOOL git with action=status",
    },
    {
        "category": "TOOL",
        "name": "tool_git_log",
        "prompt": "Show the last 5 git commits using the git tool",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "git"
                and isinstance(a.get("params"), dict)
                and a.get("params", {}).get("action") == "log"
                for a in actions)
        ),
        "description": "TOOL git with action=log",
    },
    {
        "category": "TOOL",
        "name": "tool_write_file",
        "prompt": "Create a file called test.txt with content 'hello' using the write_file tool",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "write_file"
                and isinstance(a.get("params"), dict)
                and "path" in a.get("params", {})
                and "content" in a.get("params", {})
                for a in actions)
        ),
        "description": "TOOL write_file with path and content",
    },
    {
        "category": "TOOL",
        "name": "tool_replace_in_file",
        "prompt": "Replace 'old_text' with 'new_text' in app.py using the replace_in_file tool",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "replace_in_file"
                and isinstance(a.get("params"), dict)
                and "path" in a.get("params", {})
                and "replacements" in a.get("params", {})
                for a in actions)
        ),
        "description": "TOOL replace_in_file with replacements array",
    },
    {
        "category": "TOOL",
        "name": "tool_run_command",
        "prompt": "Run 'echo hello' using the run_command tool",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "run_command"
                and isinstance(a.get("params"), dict)
                and "command" in a.get("params", {})
                for a in actions)
        ),
        "description": "TOOL run_command with command param",
    },
    {
        "category": "TOOL",
        "name": "tool_env_info",
        "prompt": "Check if the 'requests' package is installed using the env_info tool",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "env_info"
                and isinstance(a.get("params"), dict)
                for a in actions)
        ),
        "description": "TOOL env_info",
    },
    {
        "category": "TOOL",
        "name": "tool_http_request",
        "prompt": "Make a GET request to http://example.com using the http_request tool",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "http_request"
                and isinstance(a.get("params"), dict)
                and "url" in a.get("params", {})
                for a in actions)
        ),
        "description": "TOOL http_request with url param",
    },
    {
        "category": "TOOL",
        "name": "tool_web_search",
        "prompt": "Search the web for 'Python asyncio tutorial' using the web_search tool",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "web_search"
                and isinstance(a.get("params"), dict)
                and "query" in a.get("params", {})
                for a in actions)
        ),
        "description": "TOOL web_search with query param",
    },

    # ═══ EOF correctness ═══
    {
        "category": "EOF",
        "name": "eof_uses_tool_name",
        "prompt": "Use the read_file tool to read config.py",
        "check": lambda actions, text: (
            any(a["type"] == "tool" and a["name"] == "read_file" and a.get("closed")
                for a in actions)
        ),
        "description": "EOF uses tool name (not file path)",
    },
    {
        "category": "EOF",
        "name": "no_bare_tool_signals",
        "prompt": "Read the file README.md using the read_file tool, then list files in src using list_files.",
        "check": lambda actions, text: (
            all(a.get("params") is not None for a in actions if a["type"] == "tool")
        ),
        "description": "No bare TOOL signals without JSON params",
    },

    # ═══ Multiple blocks ═══
    {
        "category": "MULTI",
        "name": "multiple_tools",
        "prompt": "First list files in the src directory, then read the file src/main.py, then search for 'TODO' in all files.",
        "check": lambda actions, text: (
            len([a for a in actions if a["type"] == "tool"]) >= 2
            and any(a["name"] == "list_files" for a in actions if a["type"] == "tool")
            and any(a["name"] == "read_file" for a in actions if a["type"] == "tool")
        ),
        "description": "Multiple TOOL blocks in one response",
    },
    {
        "category": "MULTI",
        "name": "mixed_actions",
        "prompt": "Read the file app.py, then create a new file called backup.py with content: print('backup')",
        "check": lambda actions, text: (
            (any(a["type"] == "read" for a in actions)
             or any(a["type"] == "tool" and a["name"] == "read_file" for a in actions))
            and (any(a["type"] == "write" for a in actions)
                 or any(a["type"] == "tool" and a["name"] == "write_file" for a in actions))
        ),
        "description": "Mixed read and write actions (any format)",
    },

    # ═══ Edge cases ═══
    {
        "category": "EDGE",
        "name": "full_relative_path",
        "prompt": "Edit the file src/components/App.tsx to change the title from 'Old' to 'New'",
        "check": lambda actions, text: (
            any(a["type"] == "edit" and "App.tsx" in a.get("path", "")
                for a in actions)
            or any(a["type"] == "tool" and a["name"] == "replace_in_file"
                  and "App.tsx" in a.get("params", {}).get("path", "")
                  for a in actions)
            or any(a["type"] == "tool" and a["name"] == "read_file"
                  and "App.tsx" in a.get("params", {}).get("path", "")
                  for a in actions)
        ),
        "description": "References App.tsx with path (edit, replace_in_file, or read_file first)",
    },
    {
        "category": "EDGE",
        "name": "no_prose_instead_of_action",
        "prompt": "Read the file config.yaml",
        "check": lambda actions, text: (
            len(actions) > 0
        ),
        "description": "Produces action blocks, not just prose description",
    },
    {
        "category": "EDGE",
        "name": "concise_output",
        "prompt": "List files in the current directory",
        "check": lambda actions, text: (
            len(text) < 2000
        ),
        "description": "Output is concise (under 2000 chars)",
    },
]


def run_compatibility_test(model):
    """Run all compatibility tests against the specified model."""
    from ollama_agent.tools.llm_query import LlmQueryTool
    from ollama_agent.tools import tools_system_prompt

    tool_prompt = tools_system_prompt()
    system_prompt = (
        "You are a concise coding assistant with file access.\n\n"
        + tool_prompt
    )

    tool = LlmQueryTool()

    categories = {}
    for t in TESTS:
        categories.setdefault(t["category"], []).append(t)

    results = []
    passed = 0
    failed = 0
    errors = 0

    print(f"{'='*70}")
    print(f"Model Compatibility Test: {model}")
    print(f"System prompt: {len(system_prompt)} chars")
    print(f"Tests: {len(TESTS)} ({len(categories)} categories)")
    print(f"{'='*70}\n")

    for category, cat_tests in categories.items():
        print(f"\n{'-'*70}")
        print(f"  {category} ({len(cat_tests)} tests)")
        print(f"{'-'*70}")

        for test in cat_tests:
            name = test["name"]
            prompt = test["prompt"]
            desc = test["description"]

            try:
                result = tool.execute({
                    "prompt": prompt,
                    "system": system_prompt,
                    "model": model,
                    "temperature": 0.1,
                    "max_tokens": 500,
                })
            except Exception as e:
                print(f"  [ERR] {name}: ERROR -- {e}")
                results.append({"name": name, "category": category, "status": "ERROR", "detail": str(e)})
                errors += 1
                continue

            actions = list(parse_actions(result))

            try:
                check_result = test["check"](actions, result)
            except Exception as e:
                check_result = False
                desc += f" (check error: {e})"

            if check_result:
                status = "PASS"
                passed += 1
                icon = "[OK]"
            else:
                status = "FAIL"
                failed += 1
                icon = "[FAIL]"

            print(f"  {icon} {name}: {status}")
            if status == "FAIL":
                action_types = [f"{a['type']}:{a.get('name', a.get('path', '?'))}" for a in actions]
                display = result[:120].replace("\n", "\\n")
                if len(result) > 120:
                    display += "..."
                print(f"       Expected: {desc}")
                print(f"       Got: {action_types if actions else 'no actions'}")
                print(f"       Output: {display}")

            results.append({
                "name": name,
                "category": category,
                "status": status,
                "detail": desc if status == "FAIL" else "",
            })

            time.sleep(0.5)

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY: {model}")
    print(f"{'='*70}")
    print(f"  Passed: {passed}/{len(TESTS)}")
    print(f"  Failed: {failed}/{len(TESTS)}")
    print(f"  Errors: {errors}/{len(TESTS)}")

    print(f"\n  Category breakdown:")
    for cat in ["WRITE", "EDIT", "FILE", "RUN", "TOOL", "EOF", "MULTI", "EDGE"]:
        cat_results = [r for r in results if r["category"] == cat]
        if cat_results:
            cat_pass = sum(1 for r in cat_results if r["status"] == "PASS")
            print(f"    {cat:8s}: {cat_pass}/{len(cat_results)}")

    score = passed / len(TESTS) * 100
    print(f"\n  Score: {score:.0f}%")
    if score >= 90:
        print(f"  Verdict: EXCELLENT -- model works well with this harness")
    elif score >= 75:
        print(f"  Verdict: GOOD -- model works with minor issues")
    elif score >= 50:
        print(f"  Verdict: FAIR -- model has significant compatibility issues")
    else:
        print(f"  Verdict: POOR -- model is not suitable for this harness")

    fails = [r for r in results if r["status"] == "FAIL"]
    if fails:
        print(f"\n  Failed tests:")
        for r in fails:
            print(f"    - {r['name']}: {r['detail']}")

    return results


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:14b"
    run_compatibility_test(model)
