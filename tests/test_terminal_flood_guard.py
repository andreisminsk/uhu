"""Terminal flood guard — regression tests (dev-docs/TERMINAL-FLOOD-GUARD.md).

Field failure (2026-11-08, SANDBOX): model-run TUI programs streamed raw
screen-control escapes into the console. A curses snake blanked the visible
screen with \\033[2J, cycled the fixed scrollback at ~8 fps until the whole
conversation was evicted, and killed curses processes stranded the terminal
on the alternate screen (\\033[?1049h with no matching leave — alt-screen
has NO scrollback, so a later session's output vanished too).

Contract:
- neutralize_screen_controls strips wipe/position/alt-screen escapes,
  preserves SGR color codes and plain text.
- command_runner console stream is sanitized and capped at
  MAX_STREAMED_LINES; the captured observation keeps raw bytes.
- py_compile 'run' is NOT auto-approved (SAFE_TOOLS regression).
- [Run rc=N] reports the real exit code (poll() reaps; returncode alone
  stayed None when EOF beat the first queue-empty poll).
"""

import sys

from ollama_agent.constants import SAFE_TOOLS
from ollama_agent.display import neutralize_screen_controls
from ollama_agent.command_runner import MAX_STREAMED_LINES


class TestNeutralizeScreenControls:
    def test_clear_screen_stripped(self):
        assert "\x1b[2J" not in neutralize_screen_controls("\x1b[2Jhello")

    def test_scrollback_wipe_stripped(self):
        assert "\x1b[3J" not in neutralize_screen_controls("\x1b[3J")

    def test_cursor_home_stripped(self):
        assert "\x1b[H" not in neutralize_screen_controls("\x1b[Hframe")

    def test_alt_screen_enter_leave_stripped(self):
        assert "\x1b[?1049h" not in neutralize_screen_controls("\x1b[?1049h")
        assert "\x1b[?1049l" not in neutralize_screen_controls("\x1b[?1049l")

    def test_cursor_moves_stripped(self):
        for code in ("\x1b[2A", "\x1b[B", "\x1b[5C", "\x1b[D", "\x1b[s", "\x1b[u"):
            assert code not in neutralize_screen_controls(code)

    def test_sgr_colors_preserved(self):
        s = "\x1b[1;92m[native tool_call]\x1b[0m"
        assert neutralize_screen_controls(s) == s

    def test_plain_text_untouched(self):
        s = "print('hello')\nimport curses\n"
        assert neutralize_screen_controls(s) == s

    def test_snake_frame_neutralized(self):
        # Real shape from the field: clear + home + grid lines
        frame = "\x1b[2J\x1b[H" + "#" * 30 + "\n" + "Length: 6\n"
        out = neutralize_screen_controls(frame)
        assert "\x1b" not in out
        assert "Length: 6" in out


class TestCommandRunnerStreamCap:
    def test_cap_constant(self):
        assert MAX_STREAMED_LINES == 300

    def test_stream_sanitized_and_capped(self, tmp_path, monkeypatch):
        """Flood program (clear + 400 lines + clear) must not flood the console.

        Console echo (captured agent_print calls): sanitized — no escape
        reaches the terminal — and capped at MAX_STREAMED_LINES content
        lines, with a one-line suppression note. Captured observation:
        raw bytes preserved (the trailing escape survives the 60-line trim),
        real exit code, trimmed note.
        """
        import ollama_agent.command_runner as cr

        printed = []
        monkeypatch.setattr(cr, "agent_print",
                            lambda *a, **k: printed.append("".join(a)))

        flood = tmp_path / "flood.py"
        flood.write_text(
            "import sys\n"
            "sys.stdout.write('\\033[2J\\033[H')\n"
            "for i in range(400):\n"
            "    print(f'line {i}')\n"
            "sys.stdout.write('\\033[2J\\033[H')\n"
        )
        runner = cr.CommandRunner(str(tmp_path))
        obs = runner.run(f"\"{sys.executable}\" {flood}", workdir=str(tmp_path))

        # Console: capped + sanitized
        line_prints = [p for p in printed if p.startswith("line")]
        assert len(line_prints) == MAX_STREAMED_LINES
        assert not any("\x1b" in p for p in printed), \
            "screen-control escapes must never reach the console"
        assert any("suppressed" in p for p in printed)

        # Observation: faithful raw record for the model/log
        assert "\x1b[2J" in obs
        assert "line 399" in obs
        assert "[Run rc=0]" in obs
        assert "trimmed" in obs


class RecordingGate:
    """Stands in for ApprovalGate — records prompts, declines everything."""

    auto_all = False
    auto_writes = False
    always_writes = set()
    always_runs = set()
    auto_run_prefixes = set()
    quiet = True

    def __init__(self):
        self.prompts = []

    def confirm(self, prompt, *args, **kwargs):
        self.prompts.append(prompt)
        return False

    def load_config(self):
        pass

    def save_config(self):
        pass

    def config_path(self):
        return "unused"


def _bare_session(tmp_path, gate):
    """Minimal ChatSession for driving execute_tool directly (same attr
    set as tests/test_native_feedback_loop.py::make_session)."""
    from ollama_agent.session import ChatSession

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
    s._play_done_sound = lambda: None
    s.show_ctx = lambda *a, **k: None
    s._approval = gate
    return s


class TestPyCompileNotAutoApproved:
    def test_py_compile_not_in_safe_tools(self):
        assert "py_compile" not in SAFE_TOOLS

    def test_run_action_requires_confirmation(self, tmp_path):
        """py_compile action='run' executes arbitrary code — must hit the
        confirmation path, never auto-safe (SAFE_TOOLS regression)."""
        gate = RecordingGate()
        s = _bare_session(tmp_path, gate)
        action = {"type": "tool", "name": "py_compile",
                  "params": {"action": "run", "code": "print('x')"},
                  "closed": True}
        obs = s.execute_tool(action)
        assert gate.prompts, "py_compile 'run' must require confirmation"
        assert obs is None  # declined → skipped

    def test_syntax_action_still_auto_safe(self, tmp_path):
        """action='syntax' keeps the auto-safe path (no confirmation)."""
        gate = RecordingGate()
        s = _bare_session(tmp_path, gate)
        action = {"type": "tool", "name": "py_compile",
                  "params": {"action": "syntax", "path": "nope.py"},
                  "closed": True}
        obs = s.execute_tool(action)
        assert not gate.prompts, "py_compile 'syntax' must stay auto-safe"
        assert obs is not None
