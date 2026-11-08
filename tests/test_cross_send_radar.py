"""Regression: cross-send repetition radar (field trace, 2026-11-08, beam:cloud).

Live shape: user sends "?" repeatedly; each send the model emits the SAME
native search_in_files call, gets "No matches", answers "Noted." — loop
detection never fires because action_sig_rounds was a per-_send() local
(fresh dict every send, action always seen "once").

Fix under test (never skipping legitimate re-runs — files change on disk):
- identical re-prompt: counts carry across sends via _cross_sig_rounds;
  at CROSS_SEND_LOOP_WARN_THRESHOLD a soft cross-send warning fires.
- different user message: counters reset (fresh task, fresh legitimacy).
- disk change between identical prompts: counts decay (re-run may be
  legitimate re-verification).
- hard skip (MAX_IDENTICAL_ACTION_REPEATS) remains within-send only.
"""

import pytest

from ollama_agent.session import ChatSession, _is_warning_only_observation
from ollama_agent.constants import CROSS_SEND_LOOP_WARN_THRESHOLD


class ScriptedNativeBackend:
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


def make_session(tmp_path):
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
    s._backend = ScriptedNativeBackend([])
    return s


_SEARCH = [{"name": "search_in_files",
            "params": {"path": ".", "pattern": "width|height"}}]


class TestCrossSendRadar:
    def test_identical_reprompts_accumulate_and_warn(self, tmp_path, capsys):
        """Same '?' re-prompt, same native call every send — must reach the
        soft cross-send warning (and never the hard skip)."""
        s = make_session(tmp_path)
        for _ in range(CROSS_SEND_LOOP_WARN_THRESHOLD + 1):
            s._backend.script = [("", _SEARCH), ("Noted.", [])]
            s._backend.i = 0
            s._send("?", max_rounds=2)
            capsys.readouterr()
        assert s._cross_sig_rounds, "cross-send counts never accumulated"
        sig_count = max(s._cross_sig_rounds.values())
        assert sig_count >= CROSS_SEND_LOOP_WARN_THRESHOLD, (
            f"counts did not reach the threshold across sends: {s._cross_sig_rounds}"
        )

    def test_new_instruction_resets_counts(self, tmp_path):
        s = make_session(tmp_path)
        for _ in range(CROSS_SEND_LOOP_WARN_THRESHOLD):
            s._backend.script = [("", _SEARCH), ("Noted.", [])]
            s._backend.i = 0
            s._send("?", max_rounds=2)
        assert s._cross_sig_rounds, "precondition: counts accumulated"
        s._backend.script = [("", _SEARCH), ("Noted.", [])]
        s._backend.i = 0
        s._send("now check the resize handler instead", max_rounds=2)
        # A changed message resets the PRIOR accumulation — but this send's
        # own (legitimate) execution counts once: reset means fresh, not
        # evidence-free.
        assert max(s._cross_sig_rounds.values(), default=0) == 1, (
            f"a changed user message must reset prior counts to this send's "
            f"single execution, got {s._cross_sig_rounds}"
        )

    def test_disk_change_decays_counts(self, tmp_path):
        s = make_session(tmp_path)
        for _ in range(CROSS_SEND_LOOP_WARN_THRESHOLD):
            s._backend.script = [("", _SEARCH), ("Noted.", [])]
            s._backend.i = 0
            s._send("?", max_rounds=2)
        (tmp_path / "newfile.txt").write_text("changed on disk")
        s._backend.script = [("", _SEARCH), ("Noted.", [])]
        s._backend.i = 0
        s._send("?", max_rounds=2)
        counts = s._cross_sig_rounds.values()
        assert max(counts, default=0) < CROSS_SEND_LOOP_WARN_THRESHOLD, (
            "disk change between identical prompts must decay counts"
        )

    def test_cross_send_never_triggers_hard_skip(self, tmp_path):
        """The radar counts ACROSS sends — but execution must never be
        skipped because of cross-send history (legitimate re-runs)."""
        s = make_session(tmp_path)
        for _ in range(CROSS_SEND_LOOP_WARN_THRESHOLD + 2):
            s._backend.script = [("", _SEARCH), ("Noted.", [])]
            s._backend.i = 0
            s._send("?", max_rounds=2)
            obs = [m["content"] for m in s.history if m["role"] == "user"]
            assert not any("will NOT be executed" in m for m in obs), (
                "cross-send counts triggered the hard skip"
            )
