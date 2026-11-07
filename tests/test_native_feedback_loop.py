"""Repro: native tool_calls vanish in feedback-loop rounds >= 2.

Live failure (beam:cloud snake session): the FIRST native call of a message
executes through the merge; every subsequent round's native call silently
vanishes — process_actions observes an empty snapshot, a false 'no action
blocks' nudge fires, and the loop ends prematurely ('Max feedback rounds').

This test drives the REAL _send/_feedback_loop with a scripted native-only
backend. Discriminating assertion: all three rounds' native write_file calls
must produce files on disk.

Pre-fix expectation: only out1.txt exists (rounds 2-3 dropped).
Post-fix expectation: out1.txt, out2.txt, out3.txt all exist.
"""

import json
import os

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
        # Mirror real backend contract: last_tool_calls reset per call
        # (LLMBackend.call resets stats before each _call).
        self.last_tool_calls = []
        self.i += 1
        if self.i > len(self.script):
            return ("No more actions — done.", 10)
        content, native = self.script[self.i - 1]
        self.last_tool_calls = list(native)
        return (content, 100)


class FakeApprovalGate:
    """Stands in for ApprovalGate — approves everything, no persistence."""
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
    from ollama_agent.approval import ApprovalGate  # noqa: F401  (parity check)

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
    s.model = " scripted"
    s.max_rounds = None
    s.log_file = None
    s.autosave = False
    s.autosave_name = None
    s._output_tokens_total = 0
    s._sound_warn_context_tokens = 10 ** 9
    s._approval = FakeApprovalGate()
    # Live show_ctx was exonerated (the first round's snapshot survives it),
    # so stub it to avoid its real display dependencies.
    s.show_ctx = lambda *a, **k: None
    # Keep tests silent — sound.play hits real platform audio.
    s._play_done_sound = lambda: None
    s._backend = ScriptedNativeBackend(script)
    return s


def _native_write(path, content):
    return {"name": "write_file", "params": {"path": path, "content": content}}


class TestNativeCallsAcrossFeedbackRounds:
    def test_all_rounds_native_calls_execute(self, tmp_path):
        """Three consecutive native-only responses → three files on disk.

        Regression for the live beam:cloud failure where rounds >= 2 found
        an empty native snapshot (false nudge, premature loop end).
        """
        script = [
            ("", [_native_write("out1.txt", "1")]),
            ("", [_native_write("out2.txt", "2")]),
            ("", [_native_write("out3.txt", "3")]),
        ]
        s = make_session(tmp_path, script)
        s._send("go", max_rounds=3)

        backend = s._backend
        # The loop must have consumed all three scripted responses plus the
        # wrap-up probe. Pre-fix it stops early (i == 2, 'Done' exit).
        assert backend.i == 4, (
            f"Loop consumed only {backend.i} responses — native calls after "
            f"round 1 were dropped (premature loop end)"
        )
        for name in ("out1.txt", "out2.txt", "out3.txt"):
            p = tmp_path / name
            assert p.exists(), f"{name} missing — round's native call never executed"
            assert p.read_text() == name[3]

    def test_first_round_merge_still_works(self, tmp_path):
        """Sanity: the known-good case (round-1 merge) stays green."""
        script = [
            ("", [_native_write("only.txt", "x")]),
            ("", []),
        ]
        s = make_session(tmp_path, script)
        s._send("go", max_rounds=3)
        assert (tmp_path / "only.txt").exists()
        assert s._backend.i == 2

    def test_native_round_does_not_fire_false_nudge(self, tmp_path):
        """A native-call round that fails to merge would produce empty obs and
        a false 'no action blocks' nudge; with the fix the round executes and
        no [System: You described...] message reaches history."""
        script = [
            ("", [_native_write("a.txt", "1")]),
            ("Let me fix the format.", [_native_write("b.txt", "2")]),  # intent-phrased
        ]
        s = make_session(tmp_path, script)
        s._send("go", max_rounds=3)

        user_msgs = [m["content"] for m in s.history if m["role"] == "user"]
        false_nudges = [m for m in user_msgs if "[System: You described what you plan to do" in m]
        assert not false_nudges, (
            f"False 'no action blocks' nudge fired despite native calls: {false_nudges}"
        )
        assert (tmp_path / "a.txt").exists()
        assert (tmp_path / "b.txt").exists()

    def test_live_shape_failed_first_round_then_text_native(self, tmp_path):
        """Live beam:cloud shape: round 1 native call fails at the tool level
        (string-encoded params; here: missing file), rounds 2+ mix prose with
        native calls — every round's native call must still execute. Also
        guards the false-nudge text path (round 2 has intent-phrase prose)."""
        script = [
            # Round 1: replace_in_file on a file that doesn't exist → [TOOL FAILED...]
            ("", [{"name": "replace_in_file",
                   "params": {"path": "nope.py",
                              "replacements": '[{"search": "a", "replace": "b"}]'}}]),
            # Round 2: prose + native write (live: "Let me fix the format...") — 
            # NOTE: "Let me fix..." matches _INTENT_PHRASES; if the merge drops,
            # a false nudge fires and the write never lands.
            ("Let me fix the format and update it.",
             [_native_write("fixed.txt", "ok")]),
            ("", []),
        ]
        s = make_session(tmp_path, script)
        s._send("go", max_rounds=3)
        assert (tmp_path / "fixed.txt").exists(), (
            "Round-2 native call dropped in feedback loop"
        )
        user_msgs = [m["content"] for m in s.history if m["role"] == "user"]
        assert not any("[System: You described what you plan to do" in m for m in user_msgs)
        # 3 scripted responses consumed; 3rd has no actions → clean "Done" exit
        assert s._backend.i == 3, f"Loop consumed {s._backend.i} responses"

    def test_native_parameterless_tool_executes(self, tmp_path):
        """Native calls have explicit params by construction — no 'empty
        parameters' truncation warning; the tool must actually run."""
        s = make_session(tmp_path, script=[])
        s._pending_native_calls = [
            {"name": "py_compile", "params": {"action": "syntax",
                                              "path": "does_not_exist.py"}}]
        obs, _, has_non_read, _ = s.process_actions("")
        assert obs and "py_compile" in obs
        assert "empty parameters" not in obs
