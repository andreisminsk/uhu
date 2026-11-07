# Native tool_calls Support — Architecture Design (v2)

Status: v2 design — IMPLEMENTED + validated live (Phases 1–5, plus field
fixes below; Phase 6 E2E: glm-5.3-flash:cloud 26/26 text-channel regression,
beam:cloud 23/26 all-native, real-backend one-shot runs rounds 1–3 clean)

## Field findings (live beam:cloud snake session, post-Phase-6)

1. **String-encoded nested params** — the model JSON-encoded the
   `replacements` list as a string: `"replacements": "[{\"search\": ...}]"`.
   `execute_tool` crashed with `'str' object has no attribute 'get'`.
   Fix: key-scoped coercion in `tool_calls.py` (`_STRUCTURED_PARAM_KEYS`,
   currently only `replacements`) — a string starting with `[`/`{` that
   parses as list/dict becomes the parsed structure. Free-form strings
   (e.g. `write_file` content) are never coerced.
2. **Parameterless native calls were swallowed** — `execute_tool`'s
   "empty parameters" truncation warning (a text-parser heuristic gated on
   `params_explicit`) fired for native calls like `list_files {}`, and the
   tool never ran. Fix: `_native_action_dicts` sets `params_explicit: True`
   — native calls have explicit params by construction.
3. **Feedback-loop rounds ≥2 dropping native calls (reported live)** —
   could not be reproduced after fixes 1–2: the repro suite drives the real
   `_send`/`_feedback_loop` with scripted native-only and text+native
   backends (5 shapes), and a real-backend one-shot run executed native
   calls in rounds 1–3 consecutively. Evidence points at the reporter's
   process predating the fixes; keep the repro suite
   (tests/test_native_feedback_loop.py) as the regression net.
   Note: `--no-native-tools` gates the merge, not the display — the native
   listing still renders (transparency rule).
4. **Loss confirmed post-hardening → render recovery added** — after the
   round-top capture and the lost-calls detector shipped, the field bug was
   observed live once more (detector fired: render present, snapshot empty
   at round-1 merge, round 2 clean). Root loss point still unidentified
   between `_call_model` and the merge, so the pipeline now recovers
   deterministically: `_recover_native_from_render` re-parses native calls
   from the faithful render text embedded in the response (section marker +
   args JSON; `json.dumps` escaping makes blank-line section splitting
   safe). Recovered calls flow through the same approval gate; unrecoverable
   (display-truncated) calls still get the ⚠ warning as last resort.
   Recovery + loss detector + round-top capture covered in tests.
  Console: native listings render in bold bright green (NATIVE_COLOR), with a
  600-char line-boundary preview (NATIVE_CALL_CONSOLE_PREVIEW_CHARS); full
  (2000-capped) args go only to history/log — pretty-printed args flooded
  macOS Terminal's fixed scrollback during long all-native sessions.
  Preview hardening (field, 2026-11-08): a raw line-boundary cut collapsed
  to a bare "{" when one giant value line (2461-char write_file content)
  dwarfed the rest — the path key was invisible, nothing judgeable. The
  preview now elides over-long value lines per-line first
  (NATIVE_CALL_PREVIEW_VALUE_CHARS=160) so every param key stays visible
  under the cap; history/log keep the faithful text.

5. **Detector prose false-positive → flag-gated (root identified)** — the
   lost-calls detector gated on `"[native tool_call " in response_text`, so
   any TEXT mentioning the render format triggered it. Reproduced twice live
   in the dev session (2026-11-08, glm-5.3-flash:cloud): the assistant quoted
   the format in prose ("[native tool_call N/M: name]"), recovery's `\d+/\d+`
   regex then found nothing → the ⚠ "vanished" warning fired with zero
   native calls involved. Models may also echo the render from their own
   history (the faithful render lives in assistant messages), which produced
   the earlier "render present, snapshot empty" sightings — recoverable
   echoes, not pipeline losses. Fix: `_call_model` sets
   `_native_rendered_last_call` only when uhu itself rendered native
   sections; `process_actions` gates the recovery/warning branch on that
   flag instead of a substring search. Genuine loss always has the flag set
   (render ⇒ native calls non-empty), echoed renders become inert text
   (nudge path), prose can never set the flag. Same session, related fix:
   the "no visible output" note reported `prompt_eval_count` (prompt/ctx
   total — showed 12826) instead of `last_output_tokens` (real output: 38);
   it now gates on and reports the true output-token count.

6. **Render mimicry (field, 2026-11-08, beam:cloud)** — with faithful renders
   stored verbatim in assistant history, a degraded all-native session taught
   the model the display format: it emitted "[native tool_call 1/1: name]"
   sections as plain text (degenerate 1/1 numbering, inline-glued after
   prose) instead of real actions — zero execution, loop ended "Done — no
   more actions" as if complete. The model then drifted further to malformed
   **TOOL:** signal lines (the built-in incomplete-format warning fired —
   that catch worked). Mitigation: render-echo breaker in process_actions —
   when no actions parse and the text contains digit-form render markers, a
   SYSTEM WARNING observation nudges the model back to executable forms;
   the digits-only gate keeps prose "N/M" placeholders from triggering.
   Hardened shortly after: the digits-only gate proved leaky — digit-bearing
   examples occur naturally in docs/analysis, and this dev session's own
   assistant message (quoting a full render example) fired the breaker in a
   restarted session live. Now SHAPE-gated: the header must be followed by
   newline + JSON args block (real renders and their echoes always are;
   prose mentions aren't). The warning text is also de-formatted — it no
   longer quotes the literal format, since injected corrections re-teach
   the very pattern being corrected. (First ship attempt was skipped by the
   harness parser reacting to marker quotes inside the edit's search block;
   re-applied via the replace_in_file tool path, whose fenced JSON is
   mask-safe.)
   Future option: compact history record (shortened args) to remove the
   teaching signal at the source.

7.4. **Marker-wrapped native tool names (field, 2026-11-08, mistral-large-4:cloud)**
   — the model emitted uhu's TEXT action syntax glued around the native
   tool name: `"TOOL:\`py_compile\`"` as `function.name`, failing as
   "Unknown tool". Fix in `tool_calls.py::_clean_native_name` (single
   normalization choke point for both backends and model_test): strips
   `TOOL:`/`SKILL:` marker wrappers and backticks from native names.
   Plain names pass through untouched.

7.5. **Wire-protocol 400 on round ≥1 (field, 2026-11-08, mistral-large-4:cloud)**
   — the first native call round executed fine, then the round-1 model
   continuation failed with `400 Bad Request` on `/api/chat`. Root cause:
   the native function-calling protocol requires `tool`-role results
   IMMEDIATELY after an assistant `tool_calls` message — one per call, no
   other role in between (server errors probed live: "Expected last role
   User or Tool", "Not the same number of function calls and responses",
   "Unexpected role 'tool' after role 'system'"). uhu stores the round's
   observation as a single `user` message (AS-IS-HISTORY-ARCH), so the
   replayed history violated the protocol. Fix at the wire boundary only:
   `_wire_tool_results` (both backends) converts the user-obs following a
   tool_calls assistant into per-call `tool` results (full obs text each —
   the blob covers all of the round's actions and can't be split reliably;
   count matches protocol), defers intervening system messages (job
   notifications) until after the results, and on `/v1` synthesizes
   `tool_call_id`s on both sides (Ollama's /v1 accepts missing ids; other
   providers require them). Stored history unchanged. Probed live:
   converted sequence returns 200 and the model reasons correctly from the
   results.

7. **Post-loop feedback gap (field, 2026-11-08, beam:cloud)** — the wrap-up
   after MAX_FEEDBACK_ROUNDS appended warning-only observations (mimicry
   breaker, incomplete format) to history/log but never printed them to
   console and never called the model — feedback injected after the last
   model call cannot be acted on. Live case: the model's final response
   echoed its CORRECTED write_file (path added) as render text with zero
   native calls; the breaker fired in the wrap-up, console stayed silent,
   and the fixed write was lost. Fix: warning-only wrap-up observations are
   console-printed, and if the final turn executed nothing, ONE grace model
   call is granted so the warning is actually received (strictly once, no
   recursion; grace results run the normal approval gate).
Scope: `ollama_agent/backends.py` (OllamaNativeBackend + OpenAIBackend),
`ollama_agent/session.py` (display), `ollama_agent/actions.py` (merge)
Related: `MODELS-TEST.md` (beam:cloud evidence), `ollama_agent/tools/llm_query.py`,
`ollama_agent/tools/model_test.py`, `ollama_agent/parser.py`

## Problem

Models with native function-calling chat templates (confirmed on `beam:cloud`)
respond to uhu's tool-documented system prompt by emitting structured
`message.tool_calls` in the API response instead of text-based action blocks.
Both API paths read only the text channel, so these responses surface as
**empty assistant messages** with nonzero token counts:

- **Native Ollama** (`/api/chat`): backend reads `message.content` only.
  Evidence (probe `debug_beam5.py`): a snake-program prompt returned
  `{"message": {"content": "", "tool_calls": [{"function": {"name":
  "write_file", "arguments": {"path": "snake_ascii.py", "content": "import
  os\n..."}}}]}}` — the model called uhu's real registered tool with valid
  JSON-dict arguments.

- **OpenAI-compatible** (`/v1/chat/completions`, probe `debug_beam6.py`):
  same model, same system prompt, no `tools` param sent — identical behavior:
  `finish_reason=tool_calls`, empty `content`, `message.tool_calls` with
  `arguments` as a **JSON string** (OpenAI wire format), `reasoning` instead
  of `thinking`. Streaming delivers tool_calls as **delta fragments**
  (`index` + incremental `arguments` string concat), reassembled to valid
  JSON in the probe. Truncation (`finish_reason=length`) cuts before the call
  begins — no partial tool_calls leak.

The intent maps 1:1 onto uhu's existing tool action; the gap is a boundary
translation problem on both backends.

### Requirements

1. Native tool_calls execute through the **same** action pipeline as
   text-based calls: parse → approval gate → execute → observation → feedback loop.
2. Text-based action blocks (WRITE/EDIT/FILE/RUN/TOOL) keep working unchanged.
3. Mixed responses (content + tool_calls; thinking + tool_calls) are supported.
4. No new safety surface: native calls hit the same y/N/auto/all/always gate.
5. **Transparency**: the user-facing `AI:` output must reflect what the model
   actually emitted — uhu must not display fabricated or rendered text that
   the model never typed.

## Chosen approach (v2) — structured pass-through with faithful projection

**The backend surfaces native tool_calls as structured data
(`self.last_tool_calls`); the session displays them faithfully and merges them
into the action pipeline before the approval gate.**

### Decision rationale

- **Transparency first** (project's core value). The v1 design (synthesizing
  canonical TOOL-block text inside the backend) was rejected: under it, the
  `AI:` section would show text the model never produced.
- **Consistent with existing backend conventions.** The backend already
  stashes per-call metadata (`last_output_tokens`, `last_cached_tokens`,
  `last_reasoning_tokens`); `last_tool_calls` follows the same pattern.
- **One gate, no duplicated safety review.** Approval, loop-detection, and
  observation machinery all operate on action dicts *after* the merge point —
  structured pass-through does not split the pipeline into two entry points;
  it joins one existing entry point.
- **Self-consistent history.** The assistant message stored in history is the
  faithful rendering (marker + args JSON), so replays, logs, and the model's
  own next-round view all match reality. No `role: "tool"` messages are
  fabricated.
- **Rejected alternatives:**
  - *Backend text synthesis* — violates transparency (see v1 review above).
  - *Server-side suppression* (send empty `tools: []`) — no clean switch
    exists when uhu doesn't pass a `tools` param; tool-trained models then
    emit malformed text instead, a worse failure mode.
  - *OpenAI backend parity deferred entirely* — the /v1 probe proves the
    model behavior is identical there; designed in this doc (see
    "OpenAI-compatible spec"), implementation follows the Ollama patch.

## Component flow

```
Ollama API (/api/chat or /v1/chat/completions)
      |
      v
Backend._call()                            (backends.py, both classes)
  |- stream path: accumulate content + thinking + tool_call fragments
  |- block path: read content / tool_calls directly
  |- NEW: expose normalized self.last_tool_calls
  `- returns content AS-IS (empty stays empty)
      |
      v
session display (unchanged code path, new faithful rendering)
  `- [native tool_call: write_file] + args JSON shown after AI:
      |
      v
process_actions                            (actions.py)
  `- merge last_tool_calls into parsed actions as
     {"type": "tool", "name": ..., "params": ..., "native": True}
      |
      v
approval gate -> execute_tool() -> observation -> next round (unchanged)
```

## Backend spec

- `self.last_tool_calls`: normalized `[{"name": str, "params": dict}]`, set
  in both streaming and blocking paths of `_call()` on **both backends**.
- **Contract unchanged**: `call()` still returns `(content, tokens)`; empty
  content stays empty. `--no-native-tools` disables the session-side merge
  (backend still reports `last_tool_calls`) for A/B experiments.

### Format-specific deltas

| Aspect              | Native Ollama                    | OpenAI-compatible (/v1)                     |
|---------------------|----------------------------------|---------------------------------------------|
| Detection signal    | `message.tool_calls` present     | `finish_reason == "tool_calls"` (+ tool_calls present) |
| Arguments format    | dict                             | JSON **string** → `json.loads` with `{"_raw": ...}` fallback |
| Streaming delivery  | final-chunk fields (observed)    | delta fragments: `index`, name once, `arguments` concat |
| Reasoning field     | `message.thinking`               | `message.reasoning` (display mapping)       |
| Truncation          | eval_count budget exhausted      | `finish_reason=length` — no tool_calls emitted |

- **Streaming assembly** (required, not defensive — proven by the /v1 probe):
  merge tool_call fragments across chunks keyed by `function.index` —
  concatenate name and arguments strings; extend dict fields on native
  format. On OpenAI format, `json.loads` each accumulated arguments string
  at the end; on native format use the dict as-is.
- **Pydantic patch**: extend `_apply_cache_stats_patch` to also set
  `extra='allow'` on `Message`, so tool_calls survive on Ollama versions
  where the typed model would drop them.
- **History trimming**: `OpenAIBackend._group_tool_pairs` groups assistant
  tool_calls with `role: "tool"` messages — uhu's faithful-rendering history
  stores plain assistant text instead, so no tool-pair grouping is triggered;
  trimming still works on text lengths.

## Display spec

After the `AI:` header, native calls render as what the model actually sent:

```
[native tool_call 1/2: write_file]
{"path": "snake_ascii.py", "content": "import os\nimport time\n..."}
```

- Regular content lines print as usual.
- Empty content + tool_calls (the common failure mode today) renders only the
  native-call listing — the user sees *why* the assistant message is empty.
- OpenAI backend maps `reasoning` to the existing thinking display path.

## Pipeline spec

- Merge point: `process_actions` combines text-parsed actions with
  `[{"type": "tool", "name": ..., "params": ..., "closed": True, "native": True}]`.
- Dedupe: skip native calls whose name+params signature already exists among
  text-parsed actions (models occasionally emit both channels).
- Approval gate: prompts identically to text-based TOOL calls (safety parity).
- Loop detection: identical-action signatures include native calls — a
  spiraling native-calling model stops at `MAX_IDENTICAL_ACTION_REPEATS`.

## model_test integration (implemented)

- `llm_query.py`: new `llm_query_full()` returns
  `{"content", "thinking", "tool_calls"}`; `llm_query()` preserved as a thin
  content-only wrapper (original str contract intact for all callers).
- `model_test.py`: native calls are normalized (`_normalize_tool_calls` —
  handles native dict args *and* OpenAI JSON-string args, degrades malformed
  payloads to `{"_raw": ...}`), merged into the parsed action list before
  category checks run (dedup by name+params signature), and marked
  `[native]` in console output, the markdown report, and the summary line
  ("Native tool_calls used in: N/26 test(s)").
- Works independently of the backend patch — it measures the model's native
  channel today (this is what exposed beam:cloud's tool-emitting behavior).
  Text-protocol compliance stays visible per-test via the `[native]` tag:
  a test passing only through native calls is labeled as such.

## Risks & mitigations

| Risk                                        | Mitigation |
|---------------------------------------------|------------|
| Partial tool_call args across stream chunks | Index-keyed fragment merge (required on /v1, defensive on native); regression test with synthetic chunk sequences |
| Mid-arguments truncation                    | `json.loads` failure → `{"_raw": args}` degradation; becomes an observation, never a crash |
| Model invents nonexistent tool names        | Existing unknown-tool observation path; model self-corrects next round |
| Model loops on the same native call         | Signature-repeat detection blocks after `MAX_IDENTICAL_ACTION_REPEATS` |
| Dual-channel emission (text + tools)        | Dedupe by name+params signature at merge |
| Regression for text-only models             | Merge is a no-op when `last_tool_calls` empty; full test suite + model_test reruns |

## Testing plan

1. **Backend unit tests**: `last_tool_calls` normalization (both wire
   formats); OpenAI delta-fragment merge; pydantic Message patch; flag-off
   behavior.
2. **Session/display tests**: faithful native rendering after `AI:`; merge +
   dedupe in `process_actions`; approval prompt parity.
3. **model_test reruns**: `beam:cloud` — expect TOOL-category passes now
   labeled `[native]`; one text-based model (e.g. `glm-5.3-flash:cloud`) —
   expect unchanged results, zero `[native]` tags.

## Implementation plan

Ordered phases, each independently shippable and testable. Start each phase
in its own section below (Phase 1: …, Phase 2: …) as work progresses.

### Phase 1 — Normalizer module (shared foundation)

*Goal: single normalization unit both backends and model_test reuse.*

- Extract `_normalize_tool_calls` (currently in
  `ollama_agent/tools/model_test.py`) into a shared location —
  `ollama_agent/tool_calls.py` (new module) or `ollama_agent/parser.py` —
  keeping the model_test import working.
- Unit: dict args (native Ollama), JSON-string args (OpenAI /v1),
  malformed → `{"_raw": ...}`, missing-name skip, non-dict wrap.
- Tests: port existing model_test cases; add pydantic-object inputs.
- Deliverable: `normalize_tool_calls(raw) -> [{"name", "params"}]`.

### Phase 2 — OllamaNativeBackend pass-through

*Goal: native backend surfaces tool_calls; content contract unchanged.*

- Extend `_apply_cache_stats_patch` to also rebuild `Message` with
  `extra='allow'` (same pattern as `ChatResponse`).
- Streaming path: accumulate content chunks; collect tool_calls from chunks;
  merge fragments keyed by `function.index` (concat strings, extend dicts).
- Blocking path: read `message.tool_calls` directly.
- Set `self.last_tool_calls = normalize_tool_calls(...)` in both paths
  (empty list when absent); reset at the top of `call()` alongside the
  existing `last_*` stats.
- `call()` return value unchanged — content as-is, empty stays empty.
- Tests: synthetic chunk sequences (fragmented tool_calls; final-chunk
  tool_calls; absent tool_calls; mixed content+tools).

### Phase 3 — OpenAIBackend pass-through

*Goal: /v1 parity; delta-fragment reassembly.*

- `_call` blocking path: detect `finish_reason == "tool_calls"`; read
  `choices[].message.tool_calls`; `json.loads` each arguments string (fall
  back `{"_raw": ...}`).
- `_call` streaming path: accumulate deltas keyed by `tool_calls[].index`
  (concat name + arguments strings); finalize with `json.loads` per call.
- Set `self.last_tool_calls` with the same normalized contract; reset in
  `call()`.
- `reasoning` → existing thinking-display mapping stays.
- Tests: synthetic delta streams; JSON-string args; truncated-args
  degradation; `finish_reason=length` (no tool_calls).

### Phase 4 — Session display (faithful rendering)

*Goal: show what the model actually emitted; no fabricated text.*

- After `AI:` content, render per native call:
  `[native tool_call N/M: name]` + args JSON (indent=2, truncated per
  observation limits).
- Empty content + tool_calls renders only the native listing.
- OpenAI `reasoning` feeds the existing thinking display.
- Reset/restore paths: `last_tool_calls` is per-call state — ensure
  `/reset`, `/restore`, and `/llm` swaps don't leak stale calls into the
  merge (reset in backend swap).
- Tests: display fixtures; stale-state regression.

### Phase 5 — process_actions merge

*Goal: one action pipeline; native calls reach the approval gate.*

- In `process_actions`: read `self._backend.last_tool_calls` (guard
  `--no-native-tools`), merge as `{"type": "tool", "name": ..., "params":
  ..., "closed": True, "native": True}` after text-parsed actions.
- Dedupe by (name, params-signature) against text-parsed tool actions.
- Loop detection: native signatures counted in the existing
  identical-action-repeat guard.
- `--no-native-tools` CLI flag (default ON = merge active) — plumb through
  `cli.py` → `ChatSession`.
- Tests: merge+dedupe fixtures; loop-repeat with native calls; flag-off.

### Phase 6 — End-to-end validation

*Goal: prove the whole chain with the original failing case.*

- model_test rerun `beam:cloud` — expect TOOL-category passes labeled
  `[native]` (via llm_query_full path, already implemented).
- Interactive uhu session with `beam:cloud`: the snake prompt must produce a
  visible native tool_call, approval prompt, execution, observation, and a
  follow-up round.
- Regression rerun `glm-5.3-flash:cloud` — unchanged results, zero
  `[native]` tags.
- Full pytest suite green.

## Future work

- **OpenAI-compatible implementation phase**: design complete above;
  implementation follows the Ollama backend patch, sharing the normalizer
  semantics and the session merge.
- **Tool-pair history compat**: if a future protocol needs real
  `role: "tool"` echo messages, extend `persistence.py` rather than the
  display-faithful text history.
- **System prompt note**: if field data shows native-callers still
  underperform, experiment with one prompt line steering toward text blocks.
- **model_test channel stat**: per-category native/text breakdown in the
  report if channel mixing becomes common.
