# `--max-out` — Output Token Cap Flag

Status: implemented (2026-11-12)
Scope: `ollama_agent/cli.py`, `ollama_agent/backends.py`, `ollama_agent/session.py`
Related: `--ctx`, `--tpm`, `--max-context`, `--think-level`; `dev-docs/UHU-CACHE-ANALYSIS-OPENAI.md`

## Problem

`OpenAIBackend._build_create_kwargs` hardcodes the per-request output cap:

```python
# ollama_agent/backends.py:969
max_val = min(self.ctx_size, 8192)
kwargs["max_completion_tokens"] = max_val
```

Two failure modes observed against a local thinking model (Kapitsa serving
Qwen3.8-27B, 2026-11-12):

1. **Empty replies.** Reasoning tokens count against
   `max_completion_tokens`. An 8192 cap is entirely consumable by hidden
   thinking — session log shows `[out: 8192 tokens (0|8192)]`: zero visible
   tokens, the client then reports "Output cap hit during hidden reasoning".
2. **Cannot raise the cap without code changes.** `min(ctx_size, 8192)`
   ignores the model's real limit (Kapitsa cuts at 16384 by default; some
   providers allow 32K+). Users of thinking models cannot fix this by any
   CLI flag today.

What it is **not**: `--max-context` (input-side history-trim cap, OpenAI +
`--tpm` only) and `--ctx` (assumed model context window) do not solve this.
Confirmed against README.md §Command-line Options.

Note the asymmetry: the native Ollama backend sends no `num_predict` at all
unless `max_tokens` is passed to it explicitly (`tools/llm_query.py` is the
only caller that does) — so only the OpenAI-compatible path exhibits the
problem.

## Design

### Flag

Add to `cli.py` (alphabetical position near `--max-context`):

```python
parser.add_argument("--max-out", type=int, default=None,
                    dest="max_out",
                    help="Max output tokens per model call (OpenAI-compatible: "
                         "max_completion_tokens; default: 16384, or model limit if smaller)")
```

Default `None`; the flag is *not sent as 8192 anymore* — resolved per rules
below.

### Resolution rules (replacing backends.py:969)

```python
max_val = self.max_out if self.max_out is not None else 16384
max_val = min(max_val, self.ctx_size)
if max_val > 0:
    kwargs["max_completion_tokens"] = max_val
```

Semantics:

- `--max-out N` — explicit cap, wins, still clamped by `ctx_size`
  (output can never exceed the assumed window).
- omitted — 16384 (the de-facto modern-server default; matches Kapitsa; safe
  on OpenAI gpt-4o/5 families within 128K ctx; o-series handled by the
  existing `_call_create` fallback chain).
- `--max-out 0` — omit the parameter entirely; the server applies its own
  default. Escape hatch for exotic providers (e.g. ones that reject
  `max_completion_tokens` without trying the fallback).

Why 16384 over 8192: thinking models routinely spend >8K in reasoning before
a single visible token (measured), and the modern default across OpenAI-
compatible servers is ≥16K. Why keep the clamp: `--max-out 999999` must not
ship a request a server will reject outright.

### Plumb-through

1. `cli.py` → `session.py`: pass `max_out=args.max_out` alongside
   `ctx_size=args.ctx` (session constructor + `_rebuild_backend`, mirrors
   `think_level` plumbing).
2. `session.py` → `create_backend(..., max_out=...)` in both call sites
   (L169, L559).
3. `backends.py`: `OpenAIBackend.__init__` accepts `max_out: int | None =
   None`, stores `self.max_out` (normalize `max(0, max_out)`). The native
   Ollama backend ignores it (it already sends no cap by default) — document
   that in its docstring to avoid a surprise later.
4. `/llm` runtime switching: `/llm --ctx` already rebuilds the backend, and
   the flag persists session state — extend `/llm` to carry `max_out` through
   `_rebuild_backend` unchanged (no new slashcommand surface; document in
   `/llm --help`).

### Interaction with existing knobs

| Knob | Interaction |
|---|---|
| `--ctx` | Hard ceiling for `max_out` (`min(max_out, ctx_size)`); unchanged behavior otherwise |
| `--max-context` / `--tpm` | Input-side trim budget; unchanged. Independent of output cap |
| `--think-level` | Complementary: `low`/`off` reduces *consumption* of the output budget; `--max-out` sizes the *budget* |
| `extra_body` (`--openai-extra-body`) | `extra_body` fields override typed kwargs per SDK merge order → an extras file can still override `max_completion_tokens` per provider. Document as the per-provider escape hatch |

### What deliberately does NOT change

- Native Ollama path (`num_predict` still unset by default).
- Trimmer `reserve_output=2048` in `backends.py` (input budgeting, separate
  concern; a larger output cap does not need to grow the reserve — history
  trimming already adapts to `ctx_size`).
- The `stream_options` / temperature / `reasoning_effort` fallback chain in
  `_call_create` (unchanged; an `max_completion_tokens`-rejecting provider is
  already covered by the final "retry without any max parameter" branch —
  verify that branch pops this kwarg too when implementing).

## Failure modes covered

| Scenario | Before | After |
|---|---|---|
| Thinking model eats whole cap, empty reply | hardcoded 8192, `0 visible` | user sets `--max-out 32768` or relies on 16384 default; thinking fits + visible tokens remain |
| Long code generation | cut at 8192 mid-file | cut at 16K+/user value |
| Provider rejects `max_completion_tokens` | fallback chain retried without it | unchanged (verified branch) |
| `--max-out 0` | n/a | param omitted; server default applies |

## Testing

Implemented in `tests/test_max_out.py`:

1. Default: no flag → `max_completion_tokens == 16384` (for ctx_size ≥ 16384).
2. `--max-out 30000`, `ctx_size 48000` → 30000.
3. `--max-out 70000`, `ctx_size 48000` → clamped to 48000.
4. `--max-out 0` → kwarg absent.
5. `--max-out` smaller than ctx → min() respected.
6. Fallback chain: fake provider rejecting `max_completion_tokens` → retried
   without the kwarg (existing pattern as for temperature/top_p).
7. Native backend: `num_predict` still absent by default (regression guard).
8. Plumbing: `args.max_out` → `create_backend` → `OpenAIBackend.__init__` 
   (`--max-out` reaches the backend on first build AND after `/llm` rebuild).

## Open items

- [x] Confirm no other call sites construct `OpenAIBackend` outside
  `create_backend` (grep `OpenAIBackend(`) before merging. — done 2026-11-12:
  only `create_backend` (backends.py) in package code; tests/instantiations
  in tests/test_tool_calls.py are positional and unaffected.
- [x] Decide whether `--max-out` should also clamp `tools/llm_query.py`'s
  explicit `max_tokens` — left as-is (tool is model-invoked and rarely the
  bottleneck, per spec recommendation).
- [x] README update: Features bullet, Options table row, one line with
  `--max-out 32768` example next to the TPM presets (they compose naturally).
- [x] Implemented 2026-11-12, tests in `tests/test_max_out.py`.
```