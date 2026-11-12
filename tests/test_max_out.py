"""Tests for --max-out (output cap) resolution and fallback chain.

Covers the dev-docs/MAX-OUTPUT-TOKENS-FLAG.md testing matrix:
default 16384, ctx clamping, 0 = omit, fallback retries without the kwarg,
native num_predict regression, and plumbing.
"""


# ── Resolution matrix (spec cases 1–5) ──────────────────────────────

def _build_backend(max_out, ctx_size):
    from ollama_agent.backends import OpenAIBackend
    return OpenAIBackend("http://localhost:9999/v1", "k", "t", ctx_size,
                         max_out=max_out)


def _kwargs(be):
    return be._build_create_kwargs([{"role": "user", "content": "hi"}], False)


def test_default_max_out_is_16384():
    be = _build_backend(None, 48000)
    assert be.max_out is None
    assert be._resolved_out_cap() == 16384
    assert _kwargs(be)["max_completion_tokens"] == 16384


def test_explicit_max_out_wins_when_under_ctx():
    assert _build_backend(30000, 48000)._resolved_out_cap() == 30000


def test_max_out_clamped_by_ctx():
    be = _build_backend(70000, 48000)
    assert be._resolved_out_cap() == 48000
    assert _kwargs(be)["max_completion_tokens"] == 48000


def test_max_out_zero_omits_kwarg():
    be = _build_backend(0, 48000)
    assert be._resolved_out_cap() == 0
    assert "max_completion_tokens" not in _kwargs(be)


def test_negative_max_out_normalized_to_zero():
    be = _build_backend(-5, 48000)
    assert be.max_out == 0
    # normalization clamps negatives to 0, which means "omit the cap"
    # (same semantics as an explicit --max-out 0)
    assert "max_completion_tokens" not in _kwargs(be)


def test_max_out_smaller_than_ctx_respected():
    be = _build_backend(4096, 48000)
    assert _kwargs(be)["max_completion_tokens"] == 4096


def test_max_out_never_exceeds_ctx():
    assert _build_backend(2000000, 1024000)._resolved_out_cap() == 1024000
    assert _build_backend(16384, 1000000)._resolved_out_cap() == 16384


# ── Fallback chain (spec case 6) ────────────────────────────────────

class _FakeCompletions:
    """Records create() kwargs; configurable rejection script."""

    def __init__(self, calls, reject=lambda kw: []):
        self._calls = calls
        self._reject = reject

    def create(self, **kwargs):
        self._calls.append(kwargs)
        reasons = self._reject(kwargs)
        for reason in reasons:
            if reason:
                raise RuntimeError(reason)
        return "ok"


def _wire(be, completions):
    be.client = type("C", (), {})()
    be.client.chat = type("Chat", (), {})()
    be.client.chat.completions = completions


def test_fallback_switches_to_max_tokens_with_resolved_cap():
    calls = []
    be = _build_backend(None, 48000)
    _wire(be, _FakeCompletions(calls, reject=lambda kw: ["max_completion_tokens is not recognized"]
                               if "max_completion_tokens" in kw else []))
    assert be._call_create([{"role": "user", "content": "x"}], stream=False) == "ok"
    # calls[0] is the rejected attempt (cap present); calls[1] retries with max_tokens
    assert calls[0]["max_completion_tokens"] == 16384
    assert calls[1].get("max_tokens") == 16384


def test_fallback_omits_cap_when_max_out_zero():
    calls = []
    be = _build_backend(0, 48000)
    _wire(be, _FakeCompletions(calls, reject=lambda kw: ["unrecognized"]
                               if "max_completion_tokens" in kw else []))
    assert be._call_create([{"role": "user", "content": "x"}], stream=False) == "ok"
    assert all("max_completion_tokens" not in c and "max_tokens" not in c for c in calls)


def test_fallback_removes_all_caps_on_second_failure():
    calls = []

    def reject(kw):
        if "max_completion_tokens" in kw:
            return ["max_completion_tokens unrecognized"]
        if "max_tokens" in kw:
            return ["max_tokens unsupported"]
        return []

    be = _build_backend(None, 48000)
    _wire(be, _FakeCompletions(calls, reject=reject))
    assert be._call_create([{"role": "user", "content": "x"}], stream=False) == "ok"
    assert "max_tokens" not in calls[-1]


# ── Native regression guard (spec case 7) ───────────────────────────

def test_native_backend_ignores_max_out():
    from ollama_agent.backends import OllamaNativeBackend
    be = OllamaNativeBackend("http://localhost:11434", "m", 4096)
    assert not hasattr(be, "max_out")
    opts = be._build_options()
    assert "num_predict" not in opts


def test_native_factory_ignores_max_out():
    from ollama_agent.backends import create_backend
    be = create_backend(api_type="ollama", host="http://localhost:11434",
                        model="m", ctx_size=4096, max_out=32768)
    assert not hasattr(be, "max_out")
    assert "num_predict" not in be._build_options()


# ── Plumbing (spec case 8) ──────────────────────────────────────────

def test_factory_passes_max_out_to_openai_backend():
    from ollama_agent.backends import create_backend
    be = create_backend(api_type="openai", host="http://localhost:9999/v1",
                        model="t", ctx_size=48000, max_out=32768)
    assert be.max_out == 32768
    assert be._resolved_out_cap() == 32768


def test_session_retains_max_out_for_rebuild():
    import inspect
    from ollama_agent.session import ChatSession
    init_src = inspect.getsource(ChatSession.__init__)
    rebuild_src = inspect.getsource(ChatSession._rebuild_backend)
    assert "max_out" in inspect.signature(ChatSession.__init__).parameters
    assert "self._max_out = max_out" in init_src
    assert 'max_out=getattr(self, "_max_out", None)' in rebuild_src


def test_session_default_max_out_is_none():
    import inspect
    from ollama_agent.session import ChatSession
    param = inspect.signature(ChatSession.__init__).parameters["max_out"]
    assert param.default is None


def test_cli_flag_registered_and_wired():
    import inspect
    from ollama_agent import cli
    src = inspect.getsource(cli)
    # argparse registration
    assert '"--max-out"' in src
    # plumbed into ChatSession along max-context
    assert "max_out=args.max_out" in src
