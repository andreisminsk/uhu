"""test-gen skill — generate test cases for code."""

import os

from .base import Skill


class TestGenSkill(Skill):
    name = "test-gen"
    description = "Generate test cases for source code"
    triggers = ["generate tests", "write tests", "test cases", "unit tests", "test coverage"]
    system_prompt = (
        "## test-gen\n"
        "Generate test cases for source code.\n"
        "Parameters (JSON object):\n"
        "- path (string, required): Source file to generate tests for\n"
        "- framework (string, optional, default \"auto\"): Test framework — pytest, unittest, jest, auto-detect\n"
        "- style (string, optional, default \"unit\"): Test style — unit, integration, both\n"
        "\n"
        "When this skill is invoked with file content, generate appropriate tests:\n"
        "1. Analyze the code's public API, functions, and classes\n"
        "2. Generate comprehensive test cases covering normal and edge cases\n"
        "3. Use the specified framework and style\n"
        "4. Write the tests using WRITE blocks to create test files\n"
    )
    parameters = {
        "path": {"type": "string", "required": True, "description": "Source file to generate tests for"},
        "framework": {"type": "string", "required": False, "description": "Test framework: pytest, unittest, jest, auto-detect (default: auto)"},
        "style": {"type": "string", "required": False, "description": "Test style: unit, integration, both (default: unit)"},
    }

    def execute(self, params, workdir=None, session=None):
        path = params.get("path", "")
        framework = params.get("framework", "auto")
        style = params.get("style", "unit")
        if not path:
            return "[Skill error: 'path' parameter is required for test-gen]"

        full_path = os.path.join(workdir or ".", path) if not os.path.isabs(path) else path

        if not os.path.isfile(full_path):
            return f"[Skill error: File not found: {path}]"

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return f"[Skill error: Cannot read {path}: {e}]"

        lines = content.count("\n") + 1
        ext = os.path.splitext(path)[1].lower()

        # Auto-detect framework based on language
        if framework == "auto":
            if ext in ('.py',):
                framework = "pytest"
            elif ext in ('.js', '.ts', '.jsx', '.tsx'):
                framework = "jest"
            elif ext in ('.java',):
                framework = "junit"
            elif ext in ('.go',):
                framework = "testing"
            else:
                framework = "pytest"

        return (
            f"[Skill test-gen invoked]\n"
            f"Target: {path} ({lines} lines, {ext})\n"
            f"Framework: {framework}\n"
            f"Style: {style}\n"
            f"Content:\n{content}"
        )
