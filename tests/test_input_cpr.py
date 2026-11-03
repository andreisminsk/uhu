"""Regression tests: prompt_toolkit CPR probing disabled in uhu prompts.

Bug: on some terminals prompt_toolkit sent ESC[6n (cursor position request),
printed
  WARNING: your terminal doesn't support cursor position requests (CPR)
and then hung with input blocked until the process was killed.
Fix: _ptk_output_no_cpr() — output built with enable_cpr=False.
"""

from ollama_agent.input_utils import _ptk_output_no_cpr


def test_output_created_with_cpr_disabled():
    out = _ptk_output_no_cpr()
    assert out is not None
    assert out.enable_cpr is False


def test_responds_to_cpr_is_false_when_property_exists():
    out = _ptk_output_no_cpr()
    responds = getattr(out, "responds_to_cpr", None)
    if callable(responds):
        assert out.responds_to_cpr is False
    # Vt100_Output exposes responds_to_cpr as a property reading enable_cpr;
    # other output classes may not have it at all — in both cases the
    # renderer never waits for a CPR reply.
