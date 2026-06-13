"""Model compatibility test tool for the ollama-chat-agentic harness.

Tests whether a model can correctly produce all action block formats:
- WRITE, EDIT, FILE, RUN, TOOL blocks
- EOF variants (standard, bare, wrong name)
- Multiple blocks in one response
- Edge cases (empty params, wrong tool names, etc.)

Usage as tool:
    TOOL:model_test with {"model": "minimax-m3:cloud", "base_url": "http://localhost:11434", "timeout": 120}
"""

import json
import os
import re
import sys
import time


# ── Test definitions ───────────────────────────────────────────────────

TESTS = [
    # ═══ File creation (WRITE block or write_file tool) ═══
    {
        "category": "WRITE",
        "name": "write_new_file",
        "prompt": "Create a new file called hello.py with content: print('hello world')",
        "check": lambda actions, text: (
            any(a["type"] == "write" and a["path"].endswith("hello.py") and "print" in a.get("code", "")
                for a in actions if a.get("path"))
            or any(a["type"] == "tool" and a["name"] == "write_file"
                   and a.get("params", {}).get("path", "").endswith("hello.py")
                   for a in actions)
        ),
        "description": "Creates hello.py (WRITE block or write_file tool)",
    },
    {
        "category": "WRITE",
        "name": "write_with_eof",
        "prompt": "Create a new file called config.json with content: {\"key\": \"value\"}",
        "check": lambda actions, text: (
            any(a["type"] == "write" and a["path"].endswith("config.json") and a.get("closed")
                for a in actions if a.get("path"))
            or any(a["type"] == "tool" and a["name"] == "write_file"
                   and a.get("params", {}).get("path", "").endswith("config.json")
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
            any(a["type"] == "edit" and a["path"].endswith("app.py")
                for a in actions if a.get("path"))
            or any(a["type"] == "tool" and a["name"] == "replace_in_file"
                   and a.get("params", {}).get("path", "").endswith("app.py")
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
            any(a["type"] == "edit" and a["path"].endswith("main.py") and a.get("closed")
                for a in actions if a.get("path"))
            or any(a["type"] == "tool" and a["name"] == "replace_in_file"
                   and a.get("params", {}).get("path", "").endswith("main.py")
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
            any(a["type"] == "read" and a["path"].endswith("README.md")
                for a in actions if a.get("path"))
            or any(a["type"] == "tool" and a["name"] == "read_file"
                   and a.get("params", {}).get("path", "").lower().endswith("readme.md")
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
            or any(a["type"] == "tool" and a["name"] == "list_files"
                   for a in actions)
            or any(a["type"] == "tool" and a["name"] == "read_file"
                   and "app.py" in a.get("params", {}).get("path", "")
                   for a in actions)
        ),
        "description": "Uses replace_in_file or checks file first (list_files/read_file)",
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


class ModelTestTool:
    """Test model compatibility with the ollama-chat-agentic harness."""
    name = "model_test"
    description = "Test whether a model is compatible with this harness by running structured prompts."
    system_prompt = (
        "## model_test\n"
        "Test whether a model is compatible with this harness by running structured prompts.\n"
        "Parameters (JSON object):\n"
        "- model (string, required): Model name to test (e.g. 'minimax-m3:cloud', 'qwen2.5:14b')\n"
        "- base_url (string, optional): Ollama API base URL (default: http://localhost:11434)\n"
        "- timeout (integer, optional, default 120): Timeout per test in seconds\n"
        "- categories (string, optional): Comma-separated categories to test (default: all). "
        "Options: WRITE,EDIT,FILE,RUN,TOOL,EOF,MULTI,EDGE"
    )
    parameters = {
        "model": {
            "type": "string",
            "description": "Model name to test (e.g. 'minimax-m3:cloud', 'qwen2.5:14b')",
            "required": True,
        },
        "base_url": {
            "type": "string",
            "description": "Ollama API base URL (default: http://localhost:11434)",
            "required": False,
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout per test in seconds (default: 120)",
            "required": False,
        },
        "categories": {
            "type": "string",
            "description": "Comma-separated categories to test (default: all). Options: WRITE,EDIT,FILE,RUN,TOOL,EOF,MULTI,EDGE",
            "required": False,
        },
        "report_path": {
            "type": "string",
            "description": "Path to write the report file (default: temp file). Use a temp path so the agent can safely append results to MODELS-TEST.md.",
            "required": False,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        model = params.get("model", "")
        base_url = params.get("base_url", "http://localhost:11434")
        timeout = int(params.get("timeout", 120))
        categories_str = params.get("categories", "")
        report_path = params.get("report_path", "")

        if not model:
            return "Error: 'model' parameter is required. Usage: model_test with {\"model\": \"qwen2.5:14b\"}"

        # Filter categories
        if categories_str:
            categories = set(c.strip().upper() for c in categories_str.split(","))
            tests = [t for t in TESTS if t["category"] in categories]
        else:
            tests = TESTS

        from ollama_agent.parser import parse_actions
        from ollama_agent.tools.llm_query import llm_query
        from ollama_agent.tools import tools_system_prompt

        tool_prompt = tools_system_prompt()
        system_prompt = (
            "You are a concise coding assistant with file access.\n\n"
            + tool_prompt
        )

        results = []
        passed = 0
        failed = 0
        errors = 0
        total_start = time.time()

        lines = []
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"{'='*70}")
        lines.append(f"Model Compatibility Test: {model}")
        lines.append(f"Date: {now_str}")
        lines.append(f"System prompt: {len(system_prompt)} chars")
        lines.append(f"Tests: {len(tests)}")
        lines.append(f"{'='*70}")

        for idx, test in enumerate(tests, 1):
            name = test["name"]
            prompt = test["prompt"]
            desc = test["description"]
            test_start = time.time()

            try:
                progress = f"  [{idx}/{len(tests)}] Testing {name}..."
                lines.append(progress)
                print(progress)
                result = llm_query(
                    prompt=prompt,
                    system=system_prompt,
                    model=model,
                    temperature=0.1,
                    max_tokens=500,
                    timeout=timeout,
                    ollama_url=base_url,
                )
            except Exception as e:
                test_elapsed = time.time() - test_start
                err_line = f"  [ERR] {name}: ERROR -- {e} ({test_elapsed:.1f}s)"
                lines.append(err_line)
                print(err_line)
                results.append({"name": name, "category": test["category"], "status": "ERROR", "detail": str(e), "time": test_elapsed})
                errors += 1
                continue

            actions = list(parse_actions(result))

            try:
                check_result = test["check"](actions, result)
            except Exception as e:
                check_result = False

            test_elapsed = time.time() - test_start

            if check_result:
                status = "PASS"
                passed += 1
                icon = "[OK]"
            else:
                status = "FAIL"
                failed += 1
                icon = "[FAIL]"

            result_line = f"  {icon} {name}: {status} ({test_elapsed:.1f}s)"
            lines.append(result_line)
            print(result_line)
            if status == "FAIL":
                action_types = [f"{a['type']}:{a.get('name', a.get('path', '?'))}" for a in actions]
                display = result[:120].replace("\n", "\\n")
                if len(result) > 120:
                    display += "..."
                lines.append(f"       Expected: {desc}")
                lines.append(f"       Got: {action_types if actions else 'no actions'}")
                lines.append(f"       Output: {display}")
                print(f"       Expected: {desc}")
                print(f"       Got: {action_types if actions else 'no actions'}")
                print(f"       Output: {display}")

            results.append({
                "name": name,
                "category": test["category"],
                "status": status,
                "detail": desc if status == "FAIL" else "",
                "time": test_elapsed,
            })

            time.sleep(0.5)

        # Summary
        total_elapsed = time.time() - total_start
        print(f"\n{'='*70}")
        print(f"SUMMARY: {model}")
        print(f"{'='*70}")
        print(f"  Passed: {passed}/{len(tests)}")
        print(f"  Failed: {failed}/{len(tests)}")
        print(f"  Errors: {errors}/{len(tests)}")
        print(f"  Total time: {total_elapsed:.1f}s")
        lines.append(f"\n{'='*70}")
        lines.append(f"SUMMARY: {model}")
        lines.append(f"{'='*70}")
        lines.append(f"  Passed: {passed}/{len(tests)}")
        lines.append(f"  Failed: {failed}/{len(tests)}")
        lines.append(f"  Errors: {errors}/{len(tests)}")
        lines.append(f"  Total time: {total_elapsed:.1f}s")

        lines.append(f"\n  Category breakdown:")
        print(f"\n  Category breakdown:")
        for cat in ["WRITE", "EDIT", "FILE", "RUN", "TOOL", "EOF", "MULTI", "EDGE"]:
            cat_results = [r for r in results if r["category"] == cat]
            if cat_results:
                cat_pass = sum(1 for r in cat_results if r["status"] == "PASS")
                cat_line = f"    {cat:8s}: {cat_pass}/{len(cat_results)}"
                lines.append(cat_line)
                print(cat_line)

        score = passed / len(tests) * 100 if tests else 0
        score_line = f"\n  Score: {score:.0f}%"
        lines.append(score_line)
        print(score_line)
        if score >= 90:
            verdict = "  Verdict: EXCELLENT -- model works well with this harness"
        elif score >= 75:
            verdict = "  Verdict: GOOD -- model works with minor issues"
        elif score >= 50:
            verdict = "  Verdict: FAIR -- model has significant compatibility issues"
        else:
            verdict = "  Verdict: POOR -- model is not suitable for this harness"
        lines.append(verdict)
        print(verdict)

        fails = [r for r in results if r["status"] == "FAIL"]
        if fails:
            lines.append(f"\n  Failed tests:")
            for r in fails:
                lines.append(f"    - {r['name']}: {r['detail']}")

        # Write detailed results to file
        if not report_path:
            import tempfile
            report_path = os.path.join(tempfile.gettempdir(), f"models-test-{model.replace(':', '-').replace('/', '_')}.md")
        try:
            report_lines = []
            report_lines.append("# Model Compatibility Test Results\n")
            report_lines.append("| Model | Date | Tests | Pass | Fail | Status |")
            report_lines.append("|-------|------|-------|------|------|--------|")
            status_icon = "✅" if failed == 0 and errors == 0 else "❌"
            status_text = "Full compatibility" if failed == 0 and errors == 0 else f"{failed} failed, {errors} errors"
            # now_str already computed above
            report_lines.append(f"| {model} | {now_str} | {len(tests)} | {passed} | {failed + errors} | {status_icon} {status_text} |")
            report_lines.append(f"\n## {model} — {now_str}\n")
            report_lines.append(f"- **Result**: {'PASS' if failed == 0 and errors == 0 else 'FAIL'} ({passed}/{len(tests)})")
            report_lines.append(f"- **Total time**: {total_elapsed:.1f}s")
            report_lines.append(f"- **Categories**: {', '.join(cat for cat in ['WRITE','EDIT','FILE','RUN','TOOL','EOF','MULTI','EDGE'] if any(r['category'] == cat for r in results))} — {'all passed' if failed == 0 and errors == 0 else f'{failed} failed, {errors} errors'}\n")
            report_lines.append("### Details\n")
            report_lines.append("| # | Test | Result | Time |")
            report_lines.append("|---|------|--------|------|")
            for r in results:
                icon = "✅" if r["status"] == "PASS" else ("❌" if r["status"] == "FAIL" else "⚠️")
                time_str = f"{r['time']:.1f}s" if r["time"] is not None else "—"
                report_lines.append(f"| {results.index(r)+1} | {r['name']} | {icon} {r['status']} | {time_str} |")
            if fails:
                report_lines.append(f"\n### Failed tests\n")
                for r in fails:
                    report_lines.append(f"- **{r['name']}**: {r['detail']}")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("\n".join(report_lines) + "\n")
        except Exception:
            report_path = None

        # Return concise summary to avoid truncation
        summary_lines = lines[:6]  # header (now 6 lines with date)
        summary_lines.append(f"  Passed: {passed}/{len(tests)}  Failed: {failed}  Errors: {errors}  Score: {score:.0f}%")
        summary_lines.append(f"  Total time: {total_elapsed:.1f}s")
        if report_path:
            summary_lines.append(f"\n  📄 Full results written to: {report_path}")
            summary_lines.append(f"  ⚠️ Results are in a temp file — append them to MODELS-TEST.md manually, do NOT overwrite existing entries.")
        return "\n".join(summary_lines)


# Standalone CLI
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test model compatibility with ollama-chat-agentic harness")
    parser.add_argument("model", help="Model name to test (e.g. minimax-m3:cloud)")
    parser.add_argument("--base-url", default="http://localhost:11434", help="Ollama API base URL")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per test in seconds")
    parser.add_argument("--categories", default="", help="Comma-separated categories to test")
    args = parser.parse_args()

    tool = ModelTestTool()
    result = tool.execute({
        "model": args.model,
        "base_url": args.base_url,
        "timeout": args.timeout,
        "categories": args.categories,
    })
    print(result)
