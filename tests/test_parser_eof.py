#!/usr/bin/env python3
"""Test parser handles various EOF formats correctly."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ollama_agent.parser import parse_actions

def test_eof_formats():
    tests = [
        # (name, input_text, expected_tool, expected_path, expected_params)
        (
            "standard_eof",
            '**TOOL:`read_file`**\n```json\n{"path": "src/app.py"}\n```\n**EOF:`read_file`**',
            "read_file", "read_file", {"path": "src/app.py"},
        ),
        (
            "bare_eof",
            '**TOOL:`read_file`**\n```json\n{"path": "README.md"}\n```\n**EOF:**',
            "read_file", "read_file", {"path": "README.md"},
        ),
        (
            "eof_wrong_name_with_content",
            '**TOOL:`read_file`**\n```json\n{"path": "config.py"}\n```\n**EOF:`config.py`**',
            "read_file", "read_file", {"path": "config.py"},
        ),
        (
            "eof_no_closing_asterisks",
            '**TOOL:`read_file`**\n```json\n{"path": "test.txt"}\n```\n**EOF: `read_file`**',
            "read_file", "read_file", {"path": "test.txt"},
        ),
        (
            "eof_path_no_backticks",
            '**TOOL:`read_file`**\n```json\n{"path": "main.py"}\n```\n**EOF:**read_file',
            "read_file", "read_file", {"path": "main.py"},
        ),
        (
            "write_with_standard_eof",
            '**WRITE:`hello.py`**\n```python\nprint("hello")\n```\n**EOF:`hello.py`**',
            None, "hello.py", None,
        ),
        (
            "multiple_tools_with_bare_eof",
            '**TOOL:`read_file`**\n```json\n{"path": "a.py"}\n```\n**EOF:**\n\n**TOOL:`list_files`**\n```json\n{"path": "."}\n```\n**EOF:`list_files`**',
            "list_files", "list_files", {"path": "."},
        ),
    ]

    passed = 0
    failed = 0
    for name, text, expected_tool, expected_path, expected_params in tests:
        actions = list(parse_actions(text))
        if not actions:
            print(f"FAIL [{name}]: No actions parsed")
            failed += 1
            continue

        action = actions[-1] if name == "multiple_tools_with_bare_eof" else actions[0]
        
        # Check we got the right number of actions for multiple test
        if name == "multiple_tools_with_bare_eof":
            if len(actions) != 2:
                print(f"FAIL [{name}]: Expected 2 actions, got {len(actions)}")
                failed += 1
                continue
            action = actions[1]  # Check the second one

        a_type = action.get("type")
        a_name = action.get("name")  # tool/skill name
        a_path = action.get("path")   # file path for write/edit/read
        a_params = action.get("params")
        a_closed = action.get("closed", False)

        errors = []
        if expected_tool:
            if a_type != "tool":
                errors.append(f"type={a_type!r}, expected 'tool'")
            if a_name != expected_tool:
                errors.append(f"name={a_name!r}, expected {expected_tool!r}")
        if a_path != expected_path and a_name != expected_path:
            errors.append(f"path={a_path!r}, name={a_name!r}, expected_path={expected_path!r}")
        if expected_params and a_params != expected_params:
            errors.append(f"params={a_params!r}, expected {expected_params!r}")
        if not a_closed:
            errors.append("closed=False, expected True")

        if errors:
            print(f"FAIL [{name}]: {', '.join(errors)}")
            failed += 1
        else:
            print(f"PASS [{name}]")
            passed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests")
    return failed == 0

if __name__ == "__main__":
    success = test_eof_formats()
    sys.exit(0 if success else 1)
