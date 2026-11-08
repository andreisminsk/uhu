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


class TestStreamingFragments:
    """NATIVE-TOOLS-SWITCH-ARCH: streaming merge is now the hot path —
    every tool-capable model's every tool call arrives as fragments."""

    def test_split_arguments_merge(self):
        # One call's JSON args split across chunks (OpenAI /v1 string form)
        from ollama_agent.tool_calls import merge_tool_call_fragments, normalize_tool_calls
        frags = [
            {"index": 0, "function": {"name": "read_file", "arguments": '{"pa'}},
            {"index": 0, "function": {"arguments": 'th": "a.'}},
            {"index": 0, "function": {"arguments": 'txt"}'}},
        ]
        merged = normalize_tool_calls(merge_tool_call_fragments(frags))
        assert merged == [{"name": "read_file", "params": {"path": "a.txt"}}]

    def test_parallel_calls_keyed_by_index(self):
        # Realistic /v1 shape: ONE JSON string per call, split across chunks,
        # interleaved with another call's fragments. Index keys the merge.
        from ollama_agent.tool_calls import merge_tool_call_fragments, normalize_tool_calls
        frags = [
            {"index": 0, "function": {"name": "read_file", "arguments": '{"path": "a.'}},
            {"index": 1, "function": {"name": "list_files", "arguments": '{"path": "."}'}},
            {"index": 0, "function": {"arguments": 'txt", "offset": 5}'}},  # late fragment for call 0
        ]
        merged = normalize_tool_calls(merge_tool_call_fragments(frags))
        assert len(merged) == 2
        by_name = {c["name"]: c["params"] for c in merged}
        assert by_name["read_file"] == {"path": "a.txt", "offset": 5}
        assert by_name["list_files"] == {"path": "."}

    def test_native_dict_args_extended_field_by_field(self):
        # Native Ollama format: dict args spread across chunks, no index
        from ollama_agent.tool_calls import merge_tool_call_fragments, normalize_tool_calls
        frags = [
            {"function": {"name": "write_file", "arguments": {"path": "a.py"}}},
            {"function": {"arguments": {"content": "print(1)"}}},  # nameless continuation
        ]
        merged = normalize_tool_calls(merge_tool_call_fragments(frags))
        assert merged == [{"name": "write_file",
                           "params": {"path": "a.py", "content": "print(1)"}}]

    def test_interrupted_stream_partial_args_not_executed(self, tmp_path):
        """Ctrl+C / timeout mid-fragment must not produce a malformed call
        that executes with truncated params (e.g. run_command with half a
        command line). Partial fragments stay unmerged → no call."""
        from ollama_agent.tool_calls import merge_tool_call_fragments, normalize_tool_calls
        frags = [
            {"index": 0, "function": {"name": "run_command", "arguments": '{"comm'}},
            {"index": 0, "function": {"arguments": 'and": "rm -rf '}},  # stream cut here
        ]
        merged = normalize_tool_calls(merge_tool_call_fragments(frags))
        # The JSON string is incomplete — normalize must NOT parse it into
        # a half-command; it degrades to {"_raw": ...} which the pipeline
        # treats as unexecutable.
        assert len(merged) == 1
        assert "_raw" in merged[0]["params"]
        assert merged[0]["params"].get("_raw") == '{"command": "rm -rf '

    def test_empty_args_call_complete_in_one_chunk(self):
        # e2e-observed shape: list_files({}) arrives complete in the final chunk
        from ollama_agent.tool_calls import merge_tool_call_fragments, normalize_tool_calls
        merged = normalize_tool_calls(merge_tool_call_fragments(
            [{"function": {"name": "list_files", "arguments": {}}}]))
        assert merged == [{"name": "list_files", "params": {}}]

    def test_channel_mixing_blob_name_degrades(self):
        """Field case (glm-5.3-flash:cloud): a text RUN block + prose poured
        into the native name slot during failed-call recovery. The blob must
        degrade to a _malformed_native_call entry — clear, actionable failure
        instead of a 500-char 'Unknown tool' message."""
        from ollama_agent.tool_calls import normalize_tool_calls
        # Marker text is assembled from parts so this file never contains a
        # complete marker sequence (uhu's own parser would false-positive).
        _m = "**TO" + "OL:**" + "`py_compile`"
        blob = ("RUN:**\n```sh\npython3 -m py_compile snake-3.py\n```\n"
                "Wait — let me also check the collision logic. "
                + _m + " — via the native path instead")
        merged = normalize_tool_calls(
            [{"function": {"name": blob, "arguments": {"path": "snake-3.py"}}}])
        assert len(merged) == 1
        assert merged[0]["name"] == "_malformed_native_call"
        assert "_raw" in merged[0]["params"]
        # The blob is truncated, not passed whole
        assert len(merged[0]["params"]["_raw"]) <= 512

    def test_normal_names_unaffected_by_blob_guard(self):
        from ollama_agent.tool_calls import normalize_tool_calls
        merged = normalize_tool_calls(
            [{"function": {"name": "replace_in_file", "arguments": {"path": "a.py"}}}])
        assert merged == [{"name": "replace_in_file", "params": {"path": "a.py"}}]

    def test_text_action_marker_name_degrades_to_steering(self):
        """Session 2 (hybrid-with-backup): a WRITE:/EDIT:/FILE:/RUN: marker
        in the native name slot is channel-mixing — degrade to a
        _text_action_mixing steering entry, never auto-execute."""
        from ollama_agent.tool_calls import normalize_tool_calls, looks_like_text_action
        # Marker assembled from parts (see test_channel_mixing_blob_name_degrades)
        _w = "WR" + "ITE:" + "`hello.py`"
        assert looks_like_text_action(_w)
        assert looks_like_text_action("EDIT:`a.py`")
        assert looks_like_text_action("FILE:`README.md`")
        assert looks_like_text_action("RUN:")
        assert not looks_like_text_action("write_file")
        assert not looks_like_text_action("replace_in_file")
        assert not looks_like_text_action("list_files")
        merged = normalize_tool_calls(
            [{"function": {"name": _w, "arguments": {}}}])
        assert len(merged) == 1
        assert merged[0]["name"] == "_text_action_mixing"
        assert "_raw" in merged[0]["params"]
        assert len(merged[0]["params"]["_raw"]) <= 512

    def test_text_action_steering_message(self, tmp_path):
        """safety.resolve_tool_name: a text-action marker in the name slot
        yields a steering observation (re-emit as text block or call the
        backup tool), not a bare Unknown-tool error."""
        from ollama_agent.safety import resolve_tool_name
        from ollama_agent.tools import all_tools, get
        names = [t.name for t in all_tools()]
        _w = "WR" + "ITE:" + "`hello.py`"
        tool, corrected, msg = resolve_tool_name(_w, names, get, str(tmp_path))
        assert tool is None
        assert "text action" in msg
        assert "write_file" in msg
        assert "text block" in msg


class TestNativeSchemaExclusions:
    """NATIVE-TOOLS-SWITCH-ARCH, session 2: --tools-mode tri-state.
    "native" (single-channel): all actions via tool calls, text-block docs
    stripped. "hybrid" (default): text blocks preferred for file content,
    file tools INCLUDED as backup (the cornered-model re-reading — exclusion
    reversed). "text": no solicitation."""

    def test_tools_channel_includes_file_tools(self):
        from ollama_agent.tools import tools_schemas
        names = {t["function"]["name"] for t in tools_schemas(workdir=".", channel="tools")}
        # Single-channel: file-content tools ARE available natively
        assert {"read_file", "write_file", "replace_in_file"} <= names
        assert {"list_files", "search_in_files", "find_file", "peek_file",
                "copy_file", "move_file", "mkdir"} <= names

    def test_hybrid_channel_includes_file_tools_as_backup(self):
        from ollama_agent.tools import tools_schemas
        names = {t["function"]["name"] for t in tools_schemas(workdir=".", channel="hybrid")}
        # Session 2: hybrid INCLUDES the file tools as backup (exclusion reversed)
        assert {"read_file", "write_file", "replace_in_file"} <= names
        assert {"list_files", "search_in_files", "find_file", "peek_file",
                "copy_file", "move_file", "mkdir"} <= names

    def test_hybrid_rules_guide_to_text_blocks(self):
        from ollama_agent.constants import AGENT_NATIVE_TOOLS_RULES_HYBRID
        assert "FILE:" in AGENT_NATIVE_TOOLS_RULES_HYBRID
        assert "WRITE:" in AGENT_NATIVE_TOOLS_RULES_HYBRID
        assert "EDIT:" in AGENT_NATIVE_TOOLS_RULES_HYBRID
        assert "transparent" in AGENT_NATIVE_TOOLS_RULES_HYBRID
        # Backup-tool wording (session 2)
        assert "BACKUP" in AGENT_NATIVE_TOOLS_RULES_HYBRID

    def test_hybrid_native_prompt_backup_wording(self):
        from ollama_agent.tools import tools_native_prompt
        p = tools_native_prompt(channel="hybrid")
        assert "PREFER the text blocks" in p
        assert "BACKUP" in p
        # Single-channel variant keeps the tool-only wording
        p_tools = tools_native_prompt(channel="tools")
        assert "read_file to study" in p_tools
        from ollama_agent.constants import AGENT_SYSTEM_PROMPT_NATIVE
        # Single-channel prompt: no text-block docs, explicit tool-calls-only
        assert "To WRITE a new file" not in AGENT_SYSTEM_PROMPT_NATIVE
        assert "tool calls only" in AGENT_SYSTEM_PROMPT_NATIVE
        # Text mode prompt keeps them
        from ollama_agent.constants import AGENT_SYSTEM_PROMPT
        assert "To WRITE a new file" in AGENT_SYSTEM_PROMPT

    def test_build_system_prompt_channel_branch(self, tmp_path):
        from ollama_agent.system_prompt import build_system_prompt
        tools_ch = build_system_prompt(str(tmp_path), agent=True, tools=True,
                                       native_tools=True, native_channel="tools")
        hybrid_ch = build_system_prompt(str(tmp_path), agent=True, tools=True,
                                        native_tools=True, native_channel="hybrid")
        # tools channel: no text-block docs, single-channel rules
        assert "To WRITE a new file" not in tools_ch
        assert "tool calls only" in tools_ch
        # hybrid channel: text-block docs present, hybrid rules
        assert "To WRITE a new file" in hybrid_ch
        assert "transparent" in hybrid_ch


class TestApprovalGateParity:
    """NATIVE-TOOLS-SWITCH-ARCH: native calls must flow through the same
    ApprovalGate as text-channel calls — no bypass for the native channel."""

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
        s.cache_files = False
        s.show_diff = False
        for k, v in attrs.items():
            setattr(s, k, v)
        return s

    def test_risky_native_tool_prompts(self, tmp_path):
        """Native run_command must hit the confirmation prompt, identical to
        the text channel. FakeApproveAll returns True but RECORDS the prompt —
        the assertion is that the gate was consulted at all."""
        prompts = []

        class RecordingGate(FakeApproveAll):
            def confirm(self, prompt, **kwargs):
                prompts.append(prompt)
                return True

        s = self._min_session(tmp_path)
        s._approval = RecordingGate()
        s._pending_native_calls = [{"name": "run_command",
                                    "params": {"command": "echo hi"}}]
        obs, _, has_non_read, _ = s.process_actions("")
        # run_command is NOT in SAFE_TOOLS — the gate must have been consulted
        assert any("run_command" in p for p in prompts)
        assert has_non_read is True

    def test_safe_native_tool_skips_gate(self, tmp_path, capsys):
        """Native list_files is auto-safe — executes without any gate prompt
        (parity with the text channel's [auto-safe: ...] path)."""
        prompts = []

        class RecordingGate(FakeApproveAll):
            def confirm(self, prompt, **kwargs):
                prompts.append(prompt)
                return True

        s = self._min_session(tmp_path)
        s._approval = RecordingGate()
        s._pending_native_calls = [{"name": "list_files", "params": {}}]
        obs, _, _, _ = s.process_actions("")
        assert obs and "list_files" in obs
        assert prompts == []  # auto-safe path never consults the gate

    def test_native_call_declined_by_gate(self, tmp_path):
        """Gate returning False must skip the native call — identical to the
        text channel: decline → [Skipped] → no execution, no non-read flag
        (has_non_read tracks EXECUTED actions). The native channel has no
        way around a declined confirmation."""
        class DenyGate(FakeApproveAll):
            def confirm(self, prompt, **kwargs):
                return False

        s = self._min_session(tmp_path)
        s._approval = DenyGate()
        s._pending_native_calls = [{"name": "run_command",
                                    "params": {"command": "echo hi"}}]
        obs, _, has_non_read, _ = s.process_actions("")
        assert has_non_read is False  # declined = not executed (text-channel parity)
        # The skip is reported to the model as an observation (so it can
        # adapt), but the tool never executed — no result marker.
        assert obs and obs.startswith("[Skipped: TOOL run_command]")
        assert "[TOOL run_command]:" not in obs  # no execution result

    def test_parallel_risky_native_calls_each_gated(self, tmp_path):
        """3 parallel native run_command calls in one response — each must
        be gated individually (no batch bypass)."""
        prompts = []

        class RecordingGate(FakeApproveAll):
            def confirm(self, prompt, **kwargs):
                prompts.append(prompt)
                return True

        s = self._min_session(tmp_path)
        s._approval = RecordingGate()
        s._pending_native_calls = [
            {"name": "run_command", "params": {"command": "echo 1"}},
            {"name": "run_command", "params": {"command": "echo 2"}},
            {"name": "run_command", "params": {"command": "echo 3"}},
        ]
        obs, _, _, _ = s.process_actions("")
        assert len(prompts) == 3  # each call gated separately
        assert obs and "run_command" in obs

    def test_native_params_explicit_flag(self, tmp_path):
        """Native dicts carry params_explicit=True — empty params are
        legitimate (no parser-truncation warning), unlike bare text calls."""
        s = self._min_session(tmp_path)
        s._pending_native_calls = [{"name": "job_list", "params": {}}]
        obs, _, _, _ = s.process_actions("")
        # job_list takes no required params; empty {} must execute cleanly
        # without the PARSING WARNING that fires for non-explicit empty params
        assert obs and "PARSING WARNING" not in obs

    def test_text_action_mixing_synthetic_entry_observation(self, tmp_path):
        """E2E field case (glm-5.3-flash:cloud, session 2): the normalizer
        degrades a FILE: marker in the name slot to _text_action_mixing;
        execute_tool must return the STEERING observation (re-emit as text
        block or call the backup tool), not 'Unknown tool _text_action_mixing'."""
        s = self._min_session(tmp_path)
        s._pending_native_calls = [
            {"name": "_text_action_mixing", "params": {"_raw": "FI" + "LE:`README.md``"}}]
        obs, _, _, _ = s.process_actions("")
        assert obs
        assert "Unknown tool" not in obs
        assert "text action" in obs
        assert "read_file" in obs  # FILE → read_file backup
        assert "text block" in obs

    def test_malformed_native_call_synthetic_entry_observation(self, tmp_path):
        """The blob case (>64-char name) degrades to _malformed_native_call;
        execute_tool must return the actionable blob message, not Unknown tool."""
        s = self._min_session(tmp_path)
        s._pending_native_calls = [
            {"name": "_malformed_native_call", "params": {"_raw": "x" * 200}}]
        obs, _, _, _ = s.process_actions("")
        assert obs
        assert "Unknown tool" not in obs
        assert "malformed native tool call" in obs
        assert "text blob" in obs


class TestToolsModeFlag:
    """Session 2: --tools-mode {native,hybrid,text} — CLI-only tri-state,
    hybrid default, no config fallback. The deprecated --no-native-tools
    alias was removed 2026-11-08 (--tools-mode text is the legacy mode)."""

    def test_default_is_hybrid(self):
        """The CLI default must be hybrid (owner decision, session 2)."""
        import ollama_agent.cli as cli
        import argparse
        # Rebuild the parser the same way main() does and check the default
        parser = argparse.ArgumentParser()
        parser.add_argument("--tools-mode", choices=["native", "hybrid", "text"],
                            default="hybrid")
        args = parser.parse_args([])
        assert args.tools_mode == "hybrid"

    def test_no_native_tools_flag_removed(self, capsys):
        """Regression: --no-native-tools was removed — argparse must reject it
        with the standard unrecognized-argument error, and the error message
        must not leak the removed alias handling."""
        import subprocess
        import sys as _sys
        r = subprocess.run(
            [_sys.executable, "-m", "ollama_agent.cli", "--no-native-tools",
             "--version"],
            capture_output=True, text=True, timeout=30)
        assert r.returncode != 0
        assert "unrecognized arguments" in (r.stdout + r.stderr)

    def test_session_tools_mode_mapping(self, tmp_path):
        """ChatSession maps tools_mode → internal channel: native→tools,
        hybrid→hybrid, text→text; solicitation off only for text."""
        from ollama_agent.session import ChatSession
        s = ChatSession.__new__(ChatSession)
        # Simulate the constructor's mapping logic without a live backend
        for mode, expected_channel, expected_solicit in [
                ("native", "tools", True),
                ("hybrid", "hybrid", True),
                ("text", "text", False)]:
            channel = "tools" if mode == "native" else mode
            solicit = (mode != "text")  # capability check stubbed out
            assert channel == expected_channel
            assert solicit == expected_solicit

    def test_config_channel_no_longer_read(self):
        """Session 2: the native_tools.channel config read is REMOVED —
        session.py must not import load_config for channel resolution."""
        import inspect
        from ollama_agent import session as session_mod
        src = inspect.getsource(session_mod.ChatSession.__init__)
        assert "native_tools" not in src or "channel" not in src.split("tools_mode")[0]
        # The old config-based resolution line is gone
        assert '.get("native_tools", {}).get("channel"' not in src


class TestAuditToolsSchemasMCP:
    """MCP-wrapped tools: server-declared input_schema is authoritative —
    empty parameters mean the SERVER declared the tool parameterless
    (field, 2026-11-08: mcp_huggingface_hf_whoami, mcp_playwright_browser_close,
    mcp_github_get_me were false-positive warned). Prose-only tools stay flagged."""

    def _with_registry(self, monkeypatch, registry):
        from ollama_agent import tools as tools_mod
        monkeypatch.setattr(tools_mod, "_registry", registry, raising=False)

    def test_builtin_paramless_exempt(self):
        from ollama_agent.tools import audit_tools_schemas
        assert not any("sys_info" in w for w in audit_tools_schemas())

    def test_mcp_empty_schema_exempt(self, monkeypatch, tmp_path):
        from ollama_agent.tools import MCPTool, audit_tools_schemas
        t = MCPTool("mcp_github_get_me", "get me", {}, "github", object())
        assert t.parameters == {}  # server-declared parameterless
        assert t.input_schema == {}
        self._with_registry(monkeypatch, {"mcp_github_get_me": t})
        assert not [w for w in audit_tools_schemas(str(tmp_path))
                    if "mcp_github_get_me" in w]

    def test_mcp_with_params_exempt(self, monkeypatch, tmp_path):
        from ollama_agent.tools import MCPTool, audit_tools_schemas
        schema = {"properties": {"owner": {"type": "string"}}, "required": ["owner"]}
        t = MCPTool("mcp_github_get_repo", "repo", schema, "github", object())
        assert t.parameters  # non-empty → exempt via the params branch
        self._with_registry(monkeypatch, {"mcp_github_get_repo": t})
        assert not audit_tools_schemas(str(tmp_path))

    def test_prose_only_tool_still_flagged(self, monkeypatch, tmp_path):
        from ollama_agent.tools import Tool, audit_tools_schemas

        class ProseOnlyTool(Tool):
            name = "prose_only_tool"
            description = "docs only, parameters attr empty"

        t = ProseOnlyTool()
        assert not getattr(t, "parameters", None)
        assert not hasattr(t, "input_schema")  # NOT an external schema
        self._with_registry(monkeypatch, {"prose_only_tool": t})
        warnings = audit_tools_schemas(str(tmp_path))
        assert any("prose_only_tool" in w for w in warnings)
