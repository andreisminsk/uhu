"""Regression tests for the 'd' (details) confirmation option.

Bug: for RUN confirmations the LLM explainer received a doubly-truncated
payload — _extract_run_code() returned only the single "cmd: <first-line>"
line (dropping the entire heredoc body), and the prompt title embedded
cmd[:80] + ellipsis. The explainer, instructed to judge only what is
literally in front of it, correctly refused with "NOT ANALYZABLE —
truncated". Fix: pass the FULL diff_text (cwd + complete command) and a
neutral "Command details" title.
"""

import pytest

import ollama_agent.approval as approval
import ollama_agent.llm_parser as llm_parser
from ollama_agent.approval import ApprovalGate

HEREDOC_CMD = "python3 - <<'PY'\nimport os\np = '/data/x'\nprint(p)\nPY"
RUN_DIFF = "[Command details]\n  cwd: /tmp/work\n  cmd: " + HEREDOC_CMD
RUN_PROMPT = "[RUN] python3 - <<'PY'\nimport os\np = '/Users/…"


@pytest.fixture
def gate():
    return ApprovalGate(workdir=".")


@pytest.fixture
def enabled(gate):
    gate._explain_cfg = {"enabled": True, "model": "test-model",
                         "base_url": "http://localhost", "timeout": 5}
    return gate


@pytest.fixture
def answers(monkeypatch):
    """Canned confirmation answers: first 'd', then 'y'. Records prompts."""
    seq = iter(["d", "y"])
    prompts = []
    monkeypatch.setattr(approval.sound, "play", lambda *a, **k: None)
    monkeypatch.setattr(
        approval, "read_full_input",
        lambda prompt, **k: (prompts.append(prompt), next(seq))[1])
    return prompts


@pytest.fixture
def explain_calls(monkeypatch):
    """Capture _llm_explain calls; return (events, calls) — events records
    the interleaving of raw-diff display and LLM explanation."""
    events, calls = [], []

    def fake_explain(base_url, model, text, timeout=60, api_type="ollama", api_key="ollama"):
        calls.append(text)
        events.append("explain")
        return ("SAFE", None)

    monkeypatch.setattr(llm_parser, "_llm_explain", fake_explain)
    monkeypatch.setattr(approval, "show_diff_colored",
                        lambda text: events.append("show"))
    return events, calls


class TestExplainerPayload:
    def test_full_heredoc_body_and_cwd_reach_explainer(self, enabled, answers, explain_calls):
        _, calls = explain_calls
        assert enabled.confirm(RUN_PROMPT, cmd=HEREDOC_CMD, diff_text=RUN_DIFF) is True
        assert len(calls) == 1
        assert "cwd: /tmp/work" in calls[0]
        assert HEREDOC_CMD in calls[0]          # entire multi-line body present
        assert "print(p)" in calls[0]
        assert "…" not in calls[0]              # no truncation marker leaked in

    def test_neutral_title_for_run_actions(self, enabled, answers, explain_calls):
        _, calls = explain_calls
        enabled.confirm(RUN_PROMPT, cmd=HEREDOC_CMD, diff_text=RUN_DIFF)
        # First line of the payload is the title — must not embed cmd[:80]
        assert calls[0].split("\n")[0] == "Command details"

    def test_prompt_title_for_path_confirms(self, enabled, answers, explain_calls):
        _, calls = explain_calls
        enabled.confirm("[WRITE] notes.txt (3 lines)", path="notes.txt",
                        diff_text="--- a/notes.txt\n+++ b/notes.txt\n")
        # Without cmd, the prompt itself is the title
        assert calls[0].startswith("[WRITE] notes.txt (3 lines)\n\n")

    def test_raw_diff_shown_before_explainer(self, enabled, answers, explain_calls):
        events, _ = explain_calls
        enabled.confirm(RUN_PROMPT, cmd=HEREDOC_CMD, diff_text=RUN_DIFF)
        assert events == ["show", "explain"]


class TestExplainerEnablement:
    def test_skipped_when_not_configured(self, gate, answers, explain_calls):
        _, calls = explain_calls
        assert gate.confirm(RUN_PROMPT, cmd=HEREDOC_CMD, diff_text=RUN_DIFF) is True
        assert calls == []

    def test_skipped_when_diff_text_missing(self, enabled, answers, explain_calls):
        _, calls = explain_calls
        assert enabled.confirm(RUN_PROMPT, cmd=HEREDOC_CMD, diff_text=None) is True
        assert calls == []


def test_extract_run_code_removed():
    """The truncating helper must be gone — nothing else used it."""
    assert not hasattr(approval, "_extract_run_code")
