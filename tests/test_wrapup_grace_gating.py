"""Regression: feedback-loop wrap-up duplicated output and burned grace calls.

Live trace (2026-11-08): a wrap-up round whose only action was a native
read_file produced the SAME result twice on console — once truncated by the
executor echo ([... 2414 chars total, truncated for display]) and once FULL,
re-printed via agent_print by the wrap-up tail. Worse, the "Grace round"
model call fired for this ordinary read result (appended only as user obs —
no warning to act on), wasting a model call and re-appending the file
content to history.

Root causes fixed:
1. Unpack-order bug: process_actions returns (result, user_cancelled_run,
   has_executed_non_read, has_skill); the wrap-up bound element 2 (nearly
   always False) into wrap_ran_non_read, so every non-empty obs — including
   plain read results — entered the warning-only print + grace branch.
2. Missing classification: the tail never distinguished warning-shaped obs
   ([SYSTEM WARNING…, [⚠ …) from ordinary executed results, which their
   executors already echo to console.

Discriminating expectations:
- Ordinary read-result wrap-up: NO duplicate [AGENT] print, NO grace call.
- Warning-shaped wrap-up: grace round still fires (consumability kept).
"""

from ollama_agent.session import ChatSession


class ScriptedNativeBackend:
    """Pops scripted (content, native_calls) per call; empty list = no calls."""

    def __init__(self, script):
        self.script = list(script)
        self.i = 0
        self.last_tool_calls = []
        self.last_output_tokens = 5
        self.last_cached_tokens = None

    def call(self, messages, stream=True):
        self.last_tool_calls = []
        self.i += 1
        if self.i > len(self.script):
            return ("No more actions — done.", 10)
        content, native = self.script[self.i - 1]
        self.last_tool_calls = list(native)
        return (content, 100)


class FakeApprovalGate:
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


def make_session(tmp_path, script):
    s = ChatSession.__new__(ChatSession)
    s.quiet = True
    s.workdir = str(tmp_path)
    s.agent = True
    s.tools = True
    s.skills = False
    s.mcp = False
    s.ctx_size = 4096
    s.cache_files = False
    s.show_diff = False
    s.native_tools = True
    s._pending_native_calls = None
    s.history = []
    s.stream = True
    s.model = "scripted"
    s.max_rounds = None
    s.log_file = None
    s.autosave = False
    s.autosave_name = None
    s._output_tokens_total = 0
    s._sound_warn_context_tokens = 10 ** 9
    s._approval = FakeApprovalGate()
    s.show_ctx = lambda *a, **k: None
    s._play_done_sound = lambda: None
    s._backend = ScriptedNativeBackend(script)
    return s


def _native_read(path):
    return {"name": "read_file", "params": {"path": path}}


class TestWrapupGraceGating:
    def test_read_result_wrapup_no_duplicate_print_no_grace(self, tmp_path, capsys):
        """The last (unprocessed) response is an ordinary native read_file.

        Fixed behavior: executed exactly once through the wrap-up, result
        echoed by the executor only, NO Grace round model call.
        Pre-fix: backend consumed 4 responses (grace) and the full result was
        re-printed via agent_print (untruncated duplicate).
        """
        (tmp_path / "data.txt").write_text("hello world")
        read_call = _native_read("data.txt")
        script = [
            ("", [read_call]),
            ("", [read_call]),
            ("", [read_call]),  # lands in the wrap-up round
        ]
        s = make_session(tmp_path, script)
        s._send("go", max_rounds=2)

        assert s._backend.i == 3, (
            f"Backend consumed {s._backend.i} responses — an extra (grace) "
            f"model call fired for a plain read result"
        )
        out = capsys.readouterr().out
        assert "Grace round" not in out, "Grace round fired without a warning"
        # The duplicated second copy carried the [AGENT] prefix (agent_print);
        # the executor's echo uses tool_print without it.
        assert "[AGENT] [TOOL read_file]" not in out, (
            "Wrap-up re-printed the already-echoed tool result untruncated"
        )

    def test_warning_wrapup_still_fires_grace_round(self, tmp_path, capsys):
        """A warning-shaped final response must still get the grace call."""
        mimicry = 'Sure!\n\n[native tool_call 1/1: list_files]\n{\n  "path": "."\n}'
        script = [
            (mimicry, []),
            (mimicry, []),   # lands in the wrap-up round → warning obs
            ("Understood.", []),
        ]
        s = make_session(tmp_path, script)
        s._send("go", max_rounds=1)

        out = capsys.readouterr().out
        assert "Grace round" in out, (
            "Grace round no longer fires for genuinely warning-shaped wrap-ups"
        )
        assert s._backend.i == 3, (
            "Grace round did not make its single extra model call"
        )
