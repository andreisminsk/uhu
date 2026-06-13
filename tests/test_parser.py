#!/usr/bin/env python3
"""Comprehensive unit tests for ollama_agent.parser."""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from ollama_agent.parser import parse_actions, _parse_params, parse_edit_content


class TestParseParams(unittest.TestCase):
    """Tests for _parse_params helper."""

    def test_empty_input(self):
        self.assertEqual(_parse_params(""), {})
        self.assertEqual(_parse_params("  "), {})

    def test_valid_json(self):
        self.assertEqual(_parse_params('{"path": "src/app.py"}'), {"path": "src/app.py"})

    def test_valid_json_multiple_keys(self):
        self.assertEqual(
            _parse_params('{"path": "src/app.py", "limit": 10}'),
            {"path": "src/app.py", "limit": 10}
        )

    def test_json_with_boolean(self):
        self.assertEqual(
            _parse_params('{"recursive": true, "overwrite": false}'),
            {"recursive": True, "overwrite": False}
        )

    def test_curly_double_quotes_in_json(self):
        """Curly/smart double quotes in JSON should be normalized to straight quotes."""
        curly_json = '{\u201cpath\u201d: \u201csrc/app.py\u201d}'
        result = _parse_params(curly_json)
        self.assertEqual(result, {"path": "src/app.py"})

    def test_curly_single_quotes_inside_json_string(self):
        """Curly single quotes inside a JSON string value should be normalized."""
        result = _parse_params('{"pattern": "\u2018hello\u2019"}')
        self.assertEqual(result, {"pattern": "'hello'"})

    def test_fallback_key_value(self):
        result = _parse_params('path: src/app.py\nlimit: 10')
        self.assertEqual(result, {"path": "src/app.py", "limit": 10})

    def test_fallback_key_value_quoted(self):
        result = _parse_params('pattern: "hello.*world"')
        self.assertEqual(result, {"pattern": "hello.*world"})

    def test_fallback_boolean(self):
        result = _parse_params('recursive: true')
        self.assertEqual(result, {"recursive": True})

    def test_fallback_numeric(self):
        result = _parse_params('limit: 42')
        self.assertEqual(result, {"limit": 42})

    def test_fallback_float(self):
        result = _parse_params('rate: 3.14')
        self.assertEqual(result, {"rate": 3.14})

    def test_non_dict_json_returns_empty(self):
        """JSON that parses to a non-dict should fall back."""
        result = _parse_params('[1, 2, 3]')
        self.assertEqual(result, {})


class TestParseEditContent(unittest.TestCase):
    """Tests for parse_edit_content helper."""

    def test_single_search_replace(self):
        content = "<<<<<<< SEARCH\nold code\n=======\nnew code\n>>>>>>> REPLACE"
        blocks = parse_edit_content(content)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0], ("old code", "new code"))

    def test_multiple_search_replace(self):
        content = (
            "<<<<<<< SEARCH\nold1\n=======\nnew1\n>>>>>>> REPLACE\n"
            "<<<<<<< SEARCH\nold2\n=======\nnew2\n>>>>>>> REPLACE"
        )
        blocks = parse_edit_content(content)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0], ("old1", "new1"))
        self.assertEqual(blocks[1], ("old2", "new2"))

    def test_multiline_search_replace(self):
        content = "<<<<<<< SEARCH\nline1\nline2\n=======\nline3\nline4\n>>>>>>> REPLACE"
        blocks = parse_edit_content(content)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0], ("line1\nline2", "line3\nline4"))

    def test_empty_replace(self):
        content = "<<<<<<< SEARCH\nold code\n=======\n>>>>>>> REPLACE"
        blocks = parse_edit_content(content)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0], ("old code", ""))

    def test_no_blocks(self):
        content = "just some text without markers"
        blocks = parse_edit_content(content)
        self.assertEqual(len(blocks), 0)


class TestParseActionsTool(unittest.TestCase):
    """Tests for parse_actions with TOOL blocks."""

    def test_tool_basic(self):
        text = '**TOOL:`read_file`**\n```json\n{"path": "src/app.py"}\n```\n**EOF:`read_file`**'
        actions = parse_actions(text)
        self.assertEqual(len(actions), 1)
        a = actions[0]
        self.assertEqual(a["type"], "tool")
        self.assertEqual(a["name"], "read_file")
        self.assertEqual(a["params"], {"path": "src/app.py"})

    def test_tool_multiple_params(self):
        text = '**TOOL:`search_in_files`**\n```json\n{"pattern": "hello", "path": "src", "max_results": 10}\n```\n**EOF:`search_in_files`**'
        actions = parse_actions(text)
        self.assertEqual(len(actions), 1)
        a = actions[0]
        self.assertEqual(a["params"], {"pattern": "hello", "path": "src", "max_results": 10})

    def test_tool_curly_quotes_in_params(self):
        """Tool params with curly quotes should still parse correctly."""
        text = '**TOOL:`read_file`**\n```json\n{\u201cpath\u201d: \u201csrc/app.py\u201d}\n```\n**EOF:`read_file`**'
        actions = parse_actions(text)
        self.assertEqual(len(actions), 1)
        a = actions[0]
        self.assertEqual(a["params"], {"path": "src/app.py"})

    def test_multiple_tools(self):
        text = (
            '**TOOL:`read_file`**\n```json\n{"path": "a.py"}\n```\n**EOF:`read_file`**\n'
            '**TOOL:`list_files`**\n```json\n{"path": "."}\n```\n**EOF:`list_files`**'
        )
        actions = parse_actions(text)
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["name"], "read_file")
        self.assertEqual(actions[1]["name"], "list_files")


class TestParseActionsWrite(unittest.TestCase):
    """Tests for parse_actions with WRITE blocks."""

    def test_write_basic(self):
        text = '**WRITE:`hello.py`**\n```python\nprint("hello")\n```\n**EOF:`hello.py`**'
        actions = parse_actions(text)
        self.assertEqual(len(actions), 1)
        a = actions[0]
        self.assertEqual(a["type"], "write")
        self.assertEqual(a["path"], "hello.py")
        self.assertIn('print("hello")', a["code"])

    def test_write_markdown(self):
        text = '**WRITE:`README.md`**\n```markdown\n# Title\n\nContent\n```\n**EOF:`README.md`**'
        actions = parse_actions(text)
        self.assertEqual(len(actions), 1)
        self.assertIn("# Title", actions[0]["code"])


class TestParseActionsEdit(unittest.TestCase):
    """Tests for parse_actions with EDIT blocks."""

    def test_edit_basic(self):
        text = (
            '**EDIT:`hello.py`**\n'
            '```search-replace\n'
            '<<<<<<< SEARCH\n'
            'old code\n'
            '=======\n'
            'new code\n'
            '>>>>>>> REPLACE\n'
            '```\n'
            '**EOF:`hello.py`**'
        )
        actions = parse_actions(text)
        self.assertEqual(len(actions), 1)
        a = actions[0]
        self.assertEqual(a["type"], "edit")
        self.assertEqual(a["path"], "hello.py")
        self.assertEqual(len(a["edits"]), 1)
        self.assertEqual(a["edits"][0], ("old code", "new code"))


class TestParseActionsRun(unittest.TestCase):
    """Tests for parse_actions with RUN blocks."""

    def test_run_basic(self):
        text = '**RUN:**\n```bash\necho hello\n```'
        actions = parse_actions(text)
        self.assertEqual(len(actions), 1)
        a = actions[0]
        self.assertEqual(a["type"], "run")
        self.assertIn("echo hello", a["code"])


class TestParseActionsFile(unittest.TestCase):
    """Tests for parse_actions with FILE blocks."""

    def test_file_basic(self):
        text = '**FILE:`README.md`**\n```markdown\n# Title\n```\n**EOF:`README.md`**'
        actions = parse_actions(text)
        self.assertEqual(len(actions), 1)
        a = actions[0]
        self.assertEqual(a["type"], "read")
        self.assertEqual(a["path"], "README.md")


class TestParseActionsMixed(unittest.TestCase):
    """Tests for parse_actions with mixed block types."""

    def test_write_then_tool(self):
        text = (
            '**WRITE:`app.py`**\n```python\nprint("hi")\n```\n**EOF:`app.py`**\n'
            '**TOOL:`read_file`**\n```json\n{"path": "app.py"}\n```\n**EOF:`read_file`**'
        )
        actions = parse_actions(text)
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["type"], "write")
        self.assertEqual(actions[1]["type"], "tool")

    def test_no_actions(self):
        text = "Just some regular text without any action blocks."
        actions = parse_actions(text)
        self.assertEqual(len(actions), 0)


if __name__ == "__main__":
    unittest.main()
