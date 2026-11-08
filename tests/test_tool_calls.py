"""Tests for native tool_calls support (NATIVE-TOOL-CALLS-ARCH).

Phase 1: normalize_tool_calls / merge_tool_call_fragments (shared module).
Phase 2: OllamaNativeBackend pass-through (streaming + blocking), content
contract unchanged.
"""

import json

import pytest
from types import SimpleNamespace

from ollama_agent.tool_calls import merge_tool_call_fragments, normalize_tool_calls
from ollama_agent.backends import OllamaNativeBackend, OpenAIBackend

openai_installed = True
try:
    import openai  # noqa: F401
except ImportError:
    openai_installed = False

NO_OPENAI = pytest.mark.skipif(not openai_installed, reason="openai package not installed")


# ── Phase 1: normalize_tool_calls ─────────────────────────────────────


class TestNativeNameCleanup:
    def test_marker_wrapped_name_stripped(self):
        """Field regression (2026-11-08, mistral-large-4:cloud): the model
        emitted "TOOL:`py_compile`" as the native tool name — uhu's TEXT
        syntax glued around the real name. Must resolve to py_compile."""
        calls = normalize_tool_calls([
            {"function": {"name": "TOOL:`py_compile`",
                          "arguments": {"action": "run", "code": "print(1)"}}},
        ])
        assert calls[0]["name"] == "py_compile"

    def test_marker_variants(self):
        for raw, expected in [
            ("TOOL:`py_compile`", "py_compile"),
            ("TOOL: py_compile", "py_compile"),
            ("SKILL:`plan`", "plan"),
            ("TOOL:`read_file`", "read_file"),
        ]:
            calls = normalize_tool_calls([{"function": {"name": raw, "arguments": {}}}])
            assert calls[0]["name"] == expected, raw

    def test_plain_name_untouched(self):
        calls = normalize_tool_calls([{"function": {"name": "py_compile", "arguments": {}}}])
        assert calls[0]["name"] == "py_compile"

class TestNormalizeToolCalls:
    def test_native_dict_args(self):
        raw = [{"function": {"name": "write_file", "arguments": {"path": "a.py", "content": "x"}}}]
        assert normalize_tool_calls(raw) == [
            {"name": "write_file", "params": {"path": "a.py", "content": "x"}}
        ]

    def test_openai_string_args(self):
        raw = [{"function": {"name": "read_file", "arguments": json.dumps({"path": "b.py"})}}]
        assert normalize_tool_calls(raw) == [{"name": "read_file", "params": {"path": "b.py"}}]

    def test_string_args_malformed_degrades_to_raw(self):
        raw = [{"function": {"name": "t", "arguments": "{bad json"}}]
        assert normalize_tool_calls(raw)[0]["params"] == {"_raw": "{bad json"}

    def test_missing_name_skipped(self):
        assert normalize_tool_calls([{"function": {"arguments": {}}}, None]) == []

    def test_none_args_to_empty_params(self):
        assert normalize_tool_calls([{"function": {"name": "list_files"}}]) == [
            {"name": "list_files", "params": {}}
        ]

    def test_flat_format(self):
        raw = [{"name": "t", "arguments": '{"a": 1}'}]
        assert normalize_tool_calls(raw) == [{"name": "t", "params": {"a": 1}}]

    def test_pydantic_like_objects(self):
        fn = SimpleNamespace(name="git", arguments={"action": "status"})
        assert normalize_tool_calls([SimpleNamespace(function=fn)]) == [
            {"name": "git", "params": {"action": "status"}}
        ]

    def test_none_and_empty(self):
        assert normalize_tool_calls(None) == []
        assert normalize_tool_calls([]) == []

    def test_non_dict_args_wrapped(self):
        raw = [{"function": {"name": "t", "arguments": [1, 2]}}]
        assert normalize_tool_calls(raw)[0]["params"] == {"_raw": [1, 2]}

    def test_string_encoded_replacements_coerced(self):
        """Live bug (beam:cloud): nested list param JSON-encoded as string.
        Key-scoped coercion parses it into the structure execute_tool expects."""
        raw = [{"function": {"name": "replace_in_file", "arguments": {
            "path": "app.py",
            "replacements": '[{"search": "a", "replace": "b"}]'}}}]
        assert normalize_tool_calls(raw)[0]["params"]["replacements"] == [
            {"search": "a", "replace": "b"}
        ]

    def test_plain_structured_string_content_not_coerced(self):
        """Free-form string params keep string type even when they parse as
        JSON — write_file content must not be mutated."""
        raw = [{"function": {"name": "write_file", "arguments": {
            "path": "cfg.json", "content": '{"key": "value"}'}}}]
        params = normalize_tool_calls(raw)[0]["params"]
        assert params["content"] == '{"key": "value"}'
        assert isinstance(params["content"], str)

    def test_malformed_structured_string_stays_string(self):
        raw = [{"function": {"name": "replace_in_file", "arguments": {
            "path": "app.py", "replacements": '[{"search": '}}}]
        params = normalize_tool_calls(raw)[0]["params"]
        assert params["replacements"] == '[{"search": '


# ── Phase 1: merge_tool_call_fragments ────────────────────────────────

class TestMergeToolCallFragments:
    def test_index_keyed_string_concat(self):
        frags = [
            {"index": 0, "function": {"name": "write_", "arguments": '{"pa'}},
            {"index": 0, "function": {"name": "file", "arguments": 'th": "x.py"}'}},
        ]
        calls = normalize_tool_calls(merge_tool_call_fragments(frags))
        assert calls == [{"name": "write_file", "params": {"path": "x.py"}}]

    def test_dict_extend(self):
        frags = [
            {"function": {"name": "t", "arguments": {"a": 1}}},
            {"function": {"name": "", "arguments": {"b": 2}}},
        ]
        calls = normalize_tool_calls(merge_tool_call_fragments(frags))
        assert calls == [{"name": "t", "params": {"a": 1, "b": 2}}]

    def test_no_index_fragments_are_separate_calls(self):
        frags = [
            {"function": {"name": "t1", "arguments": {"a": 1}}},
            {"function": {"name": "t2", "arguments": {"b": 2}}},
        ]
        calls = normalize_tool_calls(merge_tool_call_fragments(frags))
        assert [c["name"] for c in calls] == ["t1", "t2"]

    def test_preserves_id(self):
        merged = merge_tool_call_fragments(
            [{"index": 0, "id": "call_1", "function": {"name": "t", "arguments": "{}"}}]
        )
        assert merged[0]["id"] == "call_1"

    def test_empty(self):
        assert merge_tool_call_fragments(None) == []
        assert merge_tool_call_fragments([]) == []


# ── Phase 2: OllamaNativeBackend pass-through ─────────────────────────

class FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    def iter_lines(self):
        return iter(self._lines)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeRawClient:
    """Stand-in for ollama.Client._client (httpx)."""

    def __init__(self, lines):
        self._lines = lines

    def stream(self, method, url, **kwargs):
        return FakeStreamResponse(self._lines)


def make_backend(lines):
    be = OllamaNativeBackend(host="http://localhost:11434", model="t", ctx_size=512)
    be.client._client = FakeRawClient(lines)
    return be


def _chunk(message, **extra):
    base = {"model": "t", "message": message, "done": False}
    base.update(extra)
    return json.dumps(base)


class TestOllamaNativePassThrough:
    def test_streaming_fragmented_tool_calls(self):
        # Native no-index continuation: name arrives once, dict args extend
        # across chunks (nameless fragment continues the previous call).
        lines = [
            _chunk({"role": "assistant", "content": "",
                    "tool_calls": [{"function": {"name": "write_file", "arguments": {}}}]}),
            _chunk({"role": "assistant", "content": "",
                    "tool_calls": [{"function": {"name": "", "arguments": {"path": "a.py"}}}]}),
            _chunk({"role": "assistant", "content": ""}, done=True, eval_count=10, prompt_eval_count=5),
        ]
        be = make_backend(lines)
        msg, tokens = be.call([{"role": "user", "content": "x"}], stream=True)
        assert be.last_tool_calls == [{"name": "write_file", "params": {"path": "a.py"}}]
        assert msg == ""
        # Contract: second tuple element is prompt_eval_count (backend convention)
        assert tokens == 5

    def test_streaming_final_chunk_complete_call(self):
        lines = [
            _chunk({"role": "assistant", "content": "hi",
                    "tool_calls": [{"function": {"name": "list_files", "arguments": {}}}]}),
            _chunk({"role": "assistant", "content": ""}, done=True, eval_count=3),
        ]
        be = make_backend(lines)
        msg, _ = be.call([{"role": "user", "content": "x"}], stream=True)
        assert be.last_tool_calls == [{"name": "list_files", "params": {}}]
        assert msg == "hi"

    def test_streaming_absent_tool_calls(self):
        lines = [
            _chunk({"role": "assistant", "content": "hello "}),
            _chunk({"role": "assistant", "content": "world"}, done=True, eval_count=4),
        ]
        be = make_backend(lines)
        msg, _ = be.call([{"role": "user", "content": "x"}], stream=True)
        assert be.last_tool_calls == []
        assert msg == "hello world"

    def test_streaming_reset_between_calls(self):
        with_calls = [
            _chunk({"role": "assistant", "content": "",
                    "tool_calls": [{"function": {"name": "t1", "arguments": {"a": 1}}}]}),
            _chunk({"role": "assistant", "content": ""}, done=True),
        ]
        without = [
            _chunk({"role": "assistant", "content": "plain"}),
            _chunk({"role": "assistant", "content": ""}, done=True),
        ]
        be = make_backend(with_calls)
        be.call([{"role": "user", "content": "x"}], stream=True)
        assert len(be.last_tool_calls) == 1
        be.client._client = FakeRawClient(without)
        be.call([{"role": "user", "content": "y"}], stream=True)
        assert be.last_tool_calls == []

    def test_blocking_complete_call(self):
        be = make_backend([])
        resp = {
            "message": {"role": "assistant", "content": "ok",
                        "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "x"}}}]},
            "eval_count": 7,
            "prompt_eval_count": 2,
        }
        be.client.chat = lambda **kw: resp
        msg, tokens = be.call([{"role": "user", "content": "x"}], stream=False)
        assert be.last_tool_calls == [{"name": "read_file", "params": {"path": "x"}}]
        assert msg == "ok"
        assert tokens == 2

    def test_blocking_absent_tool_calls(self):
        be = make_backend([])
        resp = {"message": {"role": "assistant", "content": "ok"}, "eval_count": 7}
        be.client.chat = lambda **kw: resp
        be.call([{"role": "user", "content": "x"}], stream=False)
        assert be.last_tool_calls == []


# ── Phase 3: OpenAIBackend pass-through ───────────────────────────────

def _delta(content="", tool_calls=None, finish_reason=None):
    return SimpleNamespace(usage=None, choices=[SimpleNamespace(
        finish_reason=finish_reason,
        delta=SimpleNamespace(content=content, tool_calls=tool_calls))])


def _frag(index, name, args, fid="call_1"):
    return SimpleNamespace(index=index, id=fid,
                           function=SimpleNamespace(name=name, arguments=args))


class TestOpenAIPassThrough:
    @NO_OPENAI
    def test_streaming_delta_fragments(self):
        be = OpenAIBackend("http://localhost:9999/v1", "k", "t", 4096)
        chunks = [
            _delta(tool_calls=[_frag(0, "write_", '{"pa')]),
            _delta(tool_calls=[_frag(0, "file", 'th": "x.py"}', fid=None)]),
            _delta(finish_reason="tool_calls"),
        ]
        be._call_create = lambda messages, stream: iter(list(chunks))
        msg, _ = be.call([{"role": "user", "content": "x"}], stream=True)
        assert be.last_tool_calls == [{"name": "write_file", "params": {"path": "x.py"}}]
        assert msg == ""

    @NO_OPENAI
    def test_streaming_no_tool_calls(self):
        be = OpenAIBackend("http://localhost:9999/v1", "k", "t", 4096)
        chunks = [
            _delta(content="hello"),
            _delta(finish_reason="stop"),
        ]
        be._call_create = lambda messages, stream: iter(list(chunks))
        msg, _ = be.call([{"role": "user", "content": "x"}], stream=True)
        assert be.last_tool_calls == []
        assert msg == "hello"

    @NO_OPENAI
    def test_streaming_length_truncation_no_tool_calls(self):
        be = OpenAIBackend("http://localhost:9999/v1", "k", "t", 4096)
        be._call_create = lambda messages, stream: iter([_delta(finish_reason="length")])
        msg, _ = be.call([{"role": "user", "content": "x"}], stream=True)
        assert be.last_tool_calls == []
        assert msg == ""

    @NO_OPENAI
    def test_streaming_reset_between_calls(self):
        be = OpenAIBackend("http://localhost:9999/v1", "k", "t", 4096)
        with_calls = [_delta(tool_calls=[_frag(0, "t1", '{"a": 1}')], finish_reason="tool_calls")]
        without = [_delta(content="ok", finish_reason="stop")]
        be._call_create = lambda messages, stream: iter(list(with_calls))
        be.call([{"role": "user", "content": "x"}], stream=True)
        assert len(be.last_tool_calls) == 1
        be._call_create = lambda messages, stream: iter(list(without))
        be.call([{"role": "user", "content": "y"}], stream=True)
        assert be.last_tool_calls == []

    @NO_OPENAI
    def test_blocking_tool_calls_json_string_args(self):
        be = OpenAIBackend("http://localhost:9999/v1", "k", "t", 4096)
        response = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    tool_calls=[SimpleNamespace(
                        id="call_1",
                        function=SimpleNamespace(
                            name="read_file",
                            arguments=json.dumps({"path": "src/app.py"})),
                    )],
                ),
                finish_reason="tool_calls")],
            usage=None,
        )
        be._call_create = lambda messages, stream: response
        msg, eval_count = be.call([{"role": "user", "content": "x"}], stream=False)
        assert be.last_tool_calls == [{"name": "read_file", "params": {"path": "src/app.py"}}]
        assert msg == ""
        assert eval_count is None

    @NO_OPENAI
    def test_blocking_malformed_args_degrade(self):
        be = OpenAIBackend("http://localhost:9999/v1", "k", "t", 4096)
        response = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    tool_calls=[SimpleNamespace(
                        id="call_1",
                        function=SimpleNamespace(name="broken_tool", arguments='{"path": '),
                    )],
                ),
                finish_reason="tool_calls")],
            usage=None,
        )
        be._call_create = lambda messages, stream: response
        be.call([{"role": "user", "content": "x"}], stream=False)
        assert be.last_tool_calls == [{"name": "broken_tool", "params": {"_raw": '{"path": '}}]


# ── Phases 4–5: session display + process_actions merge ───────────────

class FakeNativeBackend:
    last_tool_calls = [{"name": "t", "params": {}}]
    last_output_tokens = 5

    def call(self, messages, stream=True):
        return "hello", 3


class FakeApproveAll:
    """Approves everything — keeps execute paths off real stdin."""
    auto_all = True
    auto_writes = True
    always_writes = set()
    always_runs = set()
    auto_run_prefixes = set()
    quiet = True

    def confirm(self, *args, **kwargs):
        return True

    def load_config(self):
        pass

    def save_config(self):
        pass

    def config_path(self):
        return "unused"


class TestNativeSessionPhases45:
    """Lightweight ChatSession tests — __new__ + attrs, no heavy __init__."""

    def _min_session(self, tmp_path, **attrs):
        from ollama_agent.session import ChatSession
        s = ChatSession.__new__(ChatSession)
        s.native_tools = True
        s._pending_native_calls = None
        s.quiet = True
        s.workdir = str(tmp_path)
        s.agent = True
        s.tools = True
        s.skills = False
        s.ctx_size = 4096
        s.history = []
        s.stream = True
        s._approval = FakeApproveAll()
        s.cache_files = False
        s.show_diff = False
        for k, v in attrs.items():
            setattr(s, k, v)
        return s

    # Phase 4 — faithful display

    def test_render_empty_content_native_only(self, tmp_path, capsys):
        s = self._min_session(tmp_path)
        out = s._render_native_calls("", [{"name": "write_file", "params": {"path": "a.py"}}])
        assert out.startswith("[native tool_call 1/1: write_file]")
        assert '"path": "a.py"' in out
        printed = capsys.readouterr().out
        assert "[native tool_call 1/1: write_file]" in printed

    def test_render_appends_to_content(self, tmp_path):
        s = self._min_session(tmp_path)
        out = s._render_native_calls("hi", [{"name": "t", "params": {}}])
        assert out.startswith("hi")
        assert "[native tool_call 1/1: t]" in out

    def test_render_truncates_large_args(self, tmp_path):
        s = self._min_session(tmp_path)
        out = s._render_native_calls("", [{"name": "t", "params": {"x": "y" * 5000}}])
        # History keeps the 2000-char faithful version
        assert "truncated for display" in out

    def test_console_preview_giant_single_line_shows_keys(self, tmp_path, capsys):
        """Field regression (2026-11-08): a 2461-char write_file content value
        sat on ONE json line — the line-boundary cut found the newline right
        after "{" and the preview collapsed to a bare "{", hiding the path
        key entirely. Per-line value elision must keep every param key
        visible under the cap."""
        s = self._min_session(tmp_path)
        params = {"content": "x" * 2461, "path": "snake.py"}
        s._render_native_calls("", [{"name": "write_file", "params": params}])
        printed = capsys.readouterr().out
        assert '"path": "snake.py"' in printed
        assert '"content"' in printed
        assert "…[+" in printed  # per-line elision marker
        assert "full args in history" in printed

    def test_console_preview_caps_output(self, tmp_path, capsys):
        """Console shows only the preview slice; scrollback stays small.
        The full faithful text still reaches history (return value)."""
        s = self._min_session(tmp_path)
        huge = "y" * 5000
        out = s._render_native_calls("", [{"name": "t", "params": {"x": huge}}])
        printed = capsys.readouterr().out
        assert "full args in history" in printed
        assert printed.count("yyyyyyyy") < out.count("yyyyyyyy") // 10
        # but small args remain fully visible in console
        s2 = self._min_session(tmp_path)
        s2._render_native_calls("", [{"name": "t", "params": {"path": "a.py"}}])
        out2 = capsys.readouterr().out
        assert '"path": "a.py"' in out2

    def test_render_no_calls_passthrough(self, tmp_path):
        s = self._min_session(tmp_path)
        assert s._render_native_calls("hi", []) == "hi"

    def test_wire_tool_results_converts_user_obs(self):
        """Wire fix (field 400, mistral-large-4:cloud): user obs after an
        assistant tool_calls message must become per-call tool results."""
        from ollama_agent.backends import OllamaNativeBackend
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "",
             "tool_calls": [{"function": {"name": "py_compile", "arguments": {"action": "import"}}},
                             {"function": {"name": "list_files", "arguments": {}}}]},
            {"role": "user", "content": "[TOOL py_compile]: OK\n[TOOL list_files]: 3 files"},
        ]
        out = OllamaNativeBackend._wire_tool_results(msgs)
        assert [m["role"] for m in out] == ["user", "assistant", "tool", "tool"]
        assert out[2]["tool_name"] == "py_compile"
        assert out[3]["tool_name"] == "list_files"
        assert "[TOOL py_compile]: OK" in out[2]["content"]

    def test_wire_tool_results_defers_system(self):
        """System messages (job notifications) between the assistant and its
        results are deferred until after the results (server: "Unexpected
        role 'tool' after role 'system'")."""
        from ollama_agent.backends import OllamaNativeBackend
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "",
             "tool_calls": [{"function": {"name": "t", "arguments": {}}}]},
            {"role": "system", "content": "[job done]"},
            {"role": "user", "content": "obs"},
        ]
        out = OllamaNativeBackend._wire_tool_results(msgs)
        # The obs user message IS consumed as the tool result; the deferred
        # system notification flushes after it (server accepts system after
        # tool results — probed live).
        assert [m["role"] for m in out] == ["user", "assistant", "tool", "system"]
        assert out[2]["content"] == "obs"
        assert out[3]["content"] == "[job done]"

    def test_wire_tool_results_plain_history_untouched(self):
        """Text-only history passes through unchanged."""
        from ollama_agent.backends import OllamaNativeBackend
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "bye"},
        ]
        assert OllamaNativeBackend._wire_tool_results(msgs) == msgs

    def test_wire_tool_results_openai_synthesizes_ids(self):
        """/v1 path: tool results carry tool_call_id matching the call."""
        from ollama_agent.backends import OpenAIBackend
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "",
             "tool_calls": [{"function": {"name": "t", "arguments": "{}"}}]},
            {"role": "user", "content": "obs"},
        ]
        out = OpenAIBackend._wire_tool_results(msgs)
        assert [m["role"] for m in out] == ["user", "assistant", "tool"]
        assert out[1]["tool_calls"][0]["id"] == out[2]["tool_call_id"]

    def test_call_model_snapshots_native(self, tmp_path):
        s = self._min_session(tmp_path)
        s._backend = FakeNativeBackend()
        s._output_tokens_total = 0
        content, eval_count = s._call_model()
        assert s._pending_native_calls == [{"name": "t", "params": {}}]
        assert content.startswith("hello")
        assert "[native tool_call 1/1: t]" in content
        assert eval_count == 3
        assert s._output_tokens_total == 5

    def test_call_model_flag_off(self, tmp_path):
        # NATIVE-TOOLS-SWITCH-ARCH: the flag now gates SOLICITATION, not the
        # merge — unsolicited native calls (beam/mistral reflex) still merge.
        s = self._min_session(tmp_path, native_tools=False)
        s._backend = FakeNativeBackend()
        s._output_tokens_total = 0
        content, _ = s._call_model()
        assert s._pending_native_calls == [{"name": "t", "params": {}}]
        assert content.startswith("hello")
        assert "[native tool_call 1/1: t]" in content

    # Phase 5 — merge into the action pipeline

    def test_native_action_dicts(self, tmp_path):
        s = self._min_session(tmp_path)
        d = s._native_action_dicts([{"name": "t", "params": {"a": 1}}, {"params": {}}])
        assert d == [{"type": "tool", "name": "t", "params": {"a": 1},
                      "closed": True, "native": True, "params_explicit": True}]

    def test_process_actions_merges_native_tool(self, tmp_path):
        s = self._min_session(tmp_path)
        s._pending_native_calls = [{"name": "list_files", "params": {}}]
        obs, _, has_non_read, _ = s.process_actions("")
        assert has_non_read is True
        assert obs and "list_files" in obs

    def test_process_actions_consumes_snapshot(self, tmp_path):
        s = self._min_session(tmp_path)
        s._pending_native_calls = [{"name": "list_files", "params": {}}]
        s.process_actions("")
        assert s._pending_native_calls is None
        # Second processing must not re-execute the consumed native call
        obs2, _, has2, _ = s.process_actions("")
        assert obs2 is None and has2 is False

    def test_process_actions_dedupes_against_text(self, tmp_path):
        s = self._min_session(tmp_path)
        text = '**TOOL:`list_files`**\n```json\n{"path": "."}\n```\n**EOF:`list_files`**'
        s._pending_native_calls = [{"name": "list_files", "params": {"path": "."}}]
        obs, _, _, _ = s.process_actions(text)
        assert obs.count("[TOOL list_files]:") == 1

    def test_process_actions_flag_off_still_merges(self, tmp_path):
        # Flag gates SOLICITATION only — the merge catch is always active
        # (beam/mistral-class models emit native calls with no tools param).
        s = self._min_session(tmp_path, native_tools=False)
        s._pending_native_calls = [{"name": "list_files", "params": {}}]
        obs, _, has_non_read, _ = s.process_actions("")
        assert obs and "list_files" in obs
        assert has_non_read is True

    def test_process_actions_explicit_native_calls_param(self, tmp_path):
        """Feedback-loop round-top capture: snapshot passed explicitly, not
        read from session state (field-hardening for the drop bug)."""
        s = self._min_session(tmp_path)
        s._pending_native_calls = None  # must NOT be consulted
        obs, _, has_non_read, _ = s.process_actions(
            "", native_calls=[{"name": "list_files", "params": {}}])
        assert obs and "list_files" in obs
        assert has_non_read is True
        assert s._pending_native_calls is None

    def test_lost_native_calls_recovered_executes(self, tmp_path):
        """Field-found failure mode: render happened but snapshot empty at
        merge — recoverable calls now execute (list_files auto-safe).
        As-is history (AS-IS-HISTORY-ARCH) + flag-gate hardening: recovery
        requires _call_model's render signal (_native_rendered_last_call)."""
        s = self._min_session(tmp_path)
        s._pending_native_calls = None
        s._native_rendered_last_call = True  # uhu rendered native sections
        marker_msg = "[native tool_call 1/1: list_files]\n{}"
        obs, _, has_non_read, has_skill = s.process_actions(marker_msg)
        assert obs and "list_files" in obs
        assert "vanished" not in obs
        assert has_non_read is True

    def test_render_marker_without_flag_stays_inert(self, tmp_path):
        """Prose-quoting false-positive: render-formatted text without uhu's
        render flag must NOT trigger recovery or the lost-calls warning."""
        s = self._min_session(tmp_path)
        s._pending_native_calls = None
        # no _native_rendered_last_call set (default False)
        marker_msg = "[native tool_call 1/1: list_files]\n{}"
        obs, _, _, _ = s.process_actions(marker_msg)
        assert obs is None or "vanished" not in obs
        assert "list_files" not in (obs or "")

    def test_render_echo_with_solicit_off_still_breaker(self, tmp_path):
        """As-is-history era: with native_tools=False (solicitation off) the
        merge is still on, but echo-shaped render text is still caught by the
        text-channel breaker — echo protection is independent of the flag."""
        s = self._min_session(tmp_path, native_tools=False)
        s._native_rendered_last_call = False
        s._pending_native_calls = None
        obs, _, _, _ = s.process_actions("[native tool_call 1/1: t]\n{}")
        assert obs and "imitates" in obs

    def test_invisible_tokens_hint(self, tmp_path, capsys):
        """beam:cloud field behavior: 55 eval tokens, nothing rendered —
        session must surface where the tokens could have gone."""
        class GhostBackend:
            last_tool_calls = []
            last_output_tokens = 55
            last_cached_tokens = None
            last_reasoning_tokens = None
            last_thinking_chars = 0
            def call(self, messages, stream=True):
                return "", 55
        s = self._min_session(tmp_path)
        s._backend = GhostBackend()
        s._output_tokens_total = 0
        s._call_model()
        assert "no visible" in capsys.readouterr().out

    def test_invisible_tokens_hint_not_fire_for_thinking(self, tmp_path, capsys):
        class ThinkingBackend:
            last_tool_calls = []
            last_output_tokens = 55
            last_cached_tokens = None
            last_reasoning_tokens = None
            last_thinking_chars = 120  # thinking was surfaced
            def call(self, messages, stream=True):
                return "", 55
        s = self._min_session(tmp_path)
        s._backend = ThinkingBackend()
        s._output_tokens_total = 0
        s._call_model()
        assert "no visible" not in capsys.readouterr().out

    def test_lost_calls_recovered_from_render(self, tmp_path, capsys):
        """Field bug: snapshot lost between render and merge — the faithful
        render in the response text recovers the call for execution."""
        s = self._min_session(tmp_path)
        s._pending_native_calls = None
        s._native_rendered_last_call = True  # uhu rendered these sections
        render = ('[native tool_call 1/1: write_file]\n'
                  '{\n  "path": "rec.txt",\n  "content": "hello\\nworld\\n"}')
        obs, _, has_non_read, _ = s.process_actions(render)
        assert obs and "write_file" in obs
        assert has_non_read is True
        assert (tmp_path / "rec.txt").exists(), "recovered call did not execute"
        # Recovery notice goes to console, not into the observation
        assert "recovered from render: 1" in capsys.readouterr().out

    def test_render_recovery_multi_call(self, tmp_path):
        s = self._min_session(tmp_path)
        s._pending_native_calls = None
        s._native_rendered_last_call = True
        render = ('[native tool_call 1/2: read_file]\n'
                  '{\n  "path": "a.txt"\n}\n\n'
                  '[native tool_call 2/2: list_files]\n{}')
        obs, _, _, _ = s.process_actions(render)
        assert "read_file" in obs and "list_files" in obs

    def test_render_recovery_truncated_args_falls_to_breaker(self, tmp_path):
        s = self._min_session(tmp_path)
        s._pending_native_calls = None
        s._native_rendered_last_call = True
        bad = '[native tool_call 1/1: write_file]\n{\n  "content": "x'
        obs, _, _, _ = s.process_actions(bad)
        # Truncated args are unrecoverable; the echo breaker (shape-gated)
        # is the last-resort response for this render-shaped text.
        assert obs and ("vanished" in obs or "imitates" in obs)

    def test_render_recovery_skips_placeholder_name(self, tmp_path):
        s = self._min_session(tmp_path)
        s._pending_native_calls = None
        render = '[native tool_call 1/1: ?]\n{}'
        obs, _, _, _ = s.process_actions(render)
        assert obs is None or "vanished" in obs
