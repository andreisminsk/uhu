# Native Tool_calls Switch — Architecture Notes (design phase)

## CURRENT STATE (2026-11-08, session restart point)

**Shipped and tested (full suite green):**

- Native-first is the DEFAULT for tool-capable models: `tools` param sent on
  /api/chat + /v1, capability auto-detected via /api/tags (cached, re-checked
  on /llm swaps). `--no-native-tools` = legacy text-protocol mode
  (solicitation off; the merge catch for unsolicited native calls is
  UNCONDITIONAL — never disabled).
- **Channel policy is TUNABLE** via `native_tools.channel` in
  .ollama_agent.json:
  - `"tools"` (default): single-channel — text-block docs stripped from the
    prompt (AGENT_SYSTEM_PROMPT_NATIVE), ALL actions via tool calls, file
    tools included. Field-evidenced anti-confusion default.
  - `"hybrid"`: text blocks (FILE/WRITE/EDIT) documented + preferred for
    file content; read_file/write_file/replace_in_file EXCLUDED from the
    schemas array. The transparency play, opt-in.
- 39 schemas built from the flat `parameters` attribute (all tools covered;
  py_compile/token_count/calculator/google_calendar gained parameters after
  the empty-schema field case). `audit_tools_schemas()` warns at session
  start if any tool ships an empty schema.
- Native names >64 chars degrade to `_malformed_native_call` (channel-mixing
  blob guard, glm field case).
- Tests: streaming fragments, approval-gate parity, schema exclusions,
  channel branches — all in tests/test_tool_calls.py.

**Field lessons recorded below (read before changing prompt policy):**
1. The `tools` param alone flips the channel (PoC: B went native with the
   full text prompt present); prompt-stripping is a cost lever (24x), not a
   channel lever.
2. Empty schemas cause failed calls → channel-mixing recovery attempts
   (RUN blob, WRITE-in-name cases). In native mode, GLM-class models route
   ALL action-intent through the tool-call structure — text-block docs in
   native mode invite collisions. Hence the "tools" default.
3. uhu's failure handling is correct end-to-end: fail safe, observation fed
   back, model self-recovers.

**Open items (not started):**
- `--native-channel` CLI flag override (config-only today)
- Transparency parity: diff-style confirmation for write_file/
  replace_in_file instead of raw JSON dump — would make the "tools" channel
  match the text blocks' review experience (the real fix for the original
  transparency concern)
- MODELS-TEST.md absorption of the probe
- Model-variance replication (qwen3-coder-next:cloud, local qwen2.5)

**Key files:** ollama_agent/{constants,system_prompt,session,actions,
tool_calls,backends,persistence}.py, ollama_agent/tools/__init__.py,
tests/test_tool_calls.py, tests/poc_native_tools_switch.py

---

# DESIGN UPDATE (2026-11-08, session 2): --tools-mode + hybrid-with-backup

Owner decision (Andrei), superseding the config-based channel policy above:

**Status: IMPLEMENTED (2026-11-08, session 2) — full test suite green.**
Shipped: --tools-mode tri-state (hybrid default), config read removed,
hybrid includes file tools as backup, marker-name steering
(_text_action_mixing) + safety.py steering message, mixing counter
(1st → warning, 3rd → suggest --tools-mode native), --no-native-tools
deprecated alias (conflict fails fast, one-time notice). Remaining:
transparency parity (phase 2), live e2e on glm-5.3-flash:cloud.

## 1. `--tools-mode {native,hybrid,text}` — CLI-only, hybrid default

The channel policy moves OUT of .ollama_agent.json (run-specific, not
project config) onto the CLI as a tri-state flag:

- `native` — single-channel: all actions via tool calls, text-block docs
  stripped (AGENT_SYSTEM_PROMPT_NATIVE). The old "tools" channel.
- `hybrid` (DEFAULT) — native tools solicited; text blocks (FILE/WRITE/EDIT)
  documented + PREFERRED for file content (transparency: diffs, review,
  rollback, .uhu/.cache/); file tools INCLUDED as backup (see §2).
- `text` — no tools param, full text-protocol prompt. The old
  `--no-native-tools` mode.

`--no-native-tools` becomes a deprecated alias for `--tools-mode text`
(error on conflict with an explicit --tools-mode, one-time deprecation
warning). The merge catch stays UNCONDITIONAL in all modes.

Default resolution: CLI flag only — no config fallback, no per-model
memory. Capability downgrade: non-tool model (via /api/tags) → text mode
regardless of flag.

## 2. Hybrid redefinition: backup tools, not exclusion

The exclusion of read_file/write_file/replace_in_file from the hybrid
schemas array is REVERSED. Rationale — re-reading the two field cases:

- Both mixing blobs (RUN blob, WRITE-in-name) occurred when the model was
  CORNERED: hybrid excluded write_file from schemas while the prompt
  demanded text-block output the native chat template makes hard to emit.
  The text had nowhere to go, so it poured into the tool_call name slot.
- Mixing was caused by REMOVING the native option while demanding text
  output — not by having both options. Pre-tools-param field history:
  models switched fluently and safely between WRITE blocks and write_file
  when both paths were genuinely available and parseable.
- Exclusion also destroys the fallback: a failed text block (parse error,
  EOF mismatch) leaves the model with no native recovery path.

Hybrid now: text blocks preferred (prompt guidance), file tools included
as backup. The model has a real native fallback when a text block fails
or feels unnatural — the same fluency as the pre-native era, now with
solicitation on.

## 3. Mixing mitigation (the precise handling this session targets)

- **Marker-name detection** (tool_calls.py): extend `_MARKER_NAME_RE` to
  WRITE:/EDIT:/FILE: — a name like "WRITE:`hello.py`" yields a STEERING
  observation ("emit a WRITE: text block, or call write_file with
  {path, content}"), not auto-execution (name slot may be truncated).
- **Blob guard stays**: >64-char names degrade to `_malformed_native_call`
  with a 512-char `_raw` preview — the unreconstructable case; fail-safe
  observation, model self-recovers (field-proven, round 3).
- **Mixing counter**: 1st event → yellow warning; 3rd → persistent notice
  suggesting `--tools-mode native` for this model.
- **Transparency parity (phase 2)**: diff-style confirmation + rollback/
  caching integration for write_file/replace_in_file, so the backup path
  is also transparent. Dissolves the preference question — both paths
  reviewable.

## 4. Implementation surface

- cli.py: `--tools-mode` arg + post-parse validation (conflict with
  --no-native-tools, deprecation warning)
- session.py: `tools_mode` constructor param (default "hybrid"); DELETE the
  config read at session.py:77; `_native_solicit = mode != "text" and
  _model_supports_tools(...)`; mixing counter
- system_prompt.py: hybrid branch keeps text-block docs + preference
  guidance; tools_native_prompt(channel="hybrid") gains backup-tool wording
- tools/__init__.py: tools_schemas(channel="hybrid") INCLUDES the file
  tools again (drop _NATIVE_TEXT_DUPLICATES exclusion in hybrid)
- tool_calls.py: extended marker regex + steering observation
- Banner: `Native tools: on (hybrid|native)` / `off (text protocol)`
- Tests: update TestNativeSchemaExclusions (hybrid now includes file tools),
  channel-branch tests, flag-conflict + default-resolution tests,
  marker-name steering tests
- README: flag docs; this doc's open-items list updated

---

Status: IMPLEMENTED (2026-11-08) — native-first default for tool-capable models,
--no-native-tools = legacy text-protocol mode. E2E verified on glm-5.3-flash:cloud.
See "PoC results", "Decision", "Implementation notes" below.
Original design-phase notes preserved above for history.

## Motivation

Today uhu runs a **text protocol primary + native tool_calls tolerance**
architecture (see NATIVE-TOOL-CALLS-ARCH.md). Field observation and
model_test data (MODELS-TEST.md) show a stable split:

| Model family | Channel behavior |
|---|---|
| Qwen, GLM, Gemma, MiniMax, Nemotron, qwen2.5 local | Respect the text protocol (`**TOOL:`...`**` blocks), 26/26 text-channel passes |
| beam:cloud, mistral-large-4:cloud | Emit native `tool_calls` regardless of prompt; no `tools` param sent — template-driven reflex |

For the native-first camp, uhu catches calls at the wire boundary and merges
them into the normal pipeline. For the text-protocol camp, the native channel
stays dormant — because uhu never *presents* tools.

## The key question

**What would it take to motivate Qwen/GLM-class models (instruction followers)
to use native tool_calls?**

Short answer: stop asking politely. The native channel only fires when the
model's chat template is *shown* tools. uhu never sends the `tools` parameter,
and the system prompt (AGENT_SYSTEM_PROMPT + tools_system_prompt) actively
documents the text action format — a counter-signal competing with the
models' tool-training prior.

## Levers (in order of power)

1. **Send `tools: [...]` on `/api/chat`.** The chat template injects tool
   schemas with special tokens. Qwen3/GLM-4.x are fine-tuned on exactly this
   context and reliably emit `message.tool_calls`. This alone flips the mode.
2. **Strip the text-protocol sections from the system prompt in native mode**
   (keep WRITE/EDIT if desired; replace the tool listing with "use the
   provided tools"). The current prompt is the main suppressor.
3. **History consistency.** Once a round contains `tool_calls` + `role:"tool"`
   results, later rounds mirror it. `_wire_tool_results` already produces the
   correct wire shape (per-call results immediately after the assistant's
   tool_calls message; system messages deferred).

## Costs

- **JSON schemas per tool**: tools currently describe parameters only in
  prose (`system_prompt` attribute). Native mode needs a schema attribute per
  tool class — real but tedious work for the ~35 registered tools.
  Note: wire traffic may still be *smaller* than today's ~33k-char tools
  system prompt section.
- **Pipeline emphasis flip**: Phase 2–5 machinery (merge, dedupe, wire fix,
  approval gate) becomes the hot path instead of the fallback. It exists and
  is tested; the risk is shift-in-variance, not new code.

## Validate-first experiment

Rerun the probe (`probe_beam_tools.py` in the conversation workdir — POST to
`/api/chat` non-streaming) against a text-protocol-respecting model, e.g.
`qwen3-coder-next:cloud`, with:

- a small `tools` array (2–3 entries, e.g. `list_files`, `read_file`),
- a stripped system prompt (no text-protocol sections),
- and compare against the same probe without `tools` (text channel).

If the model goes native with `tools` present, the whole mode is viable.

## Compatibility matrix this targets

| Mode | beam/mistral-class | qwen/glm-class | non-tool models |
|---|---|---|---|
| Today (text primary, native tolerance) | works via catch | works via text | works (text-only) |
| Native mode (tools param + stripped prompt) | unchanged | flips to native | must keep text fallback |

Non-tool models are the reason text mode cannot be removed — native mode is
an *addition*, selected per model capability (Ollama `/api/tags` already
exposes a `tools` capability flag).

## Related

- `dev-docs/NATIVE-TOOL-CALLS-ARCH.md` — implemented native-call boundary support
- `MODELS-TEST.md` — per-model channel evidence
- `ollama_agent/backends.py` — `_wire_tool_results`, `last_tool_calls`
- `ollama_agent/tools/__init__.py` — registry (would need schema attribute)

---

# PoC results (2026-11-08) — VALIDATED

Probe: `tests/poc_native_tools_switch.py` (rerunnable: `--model`, `--task`, `--rounds`).
Model: `glm-5.3-flash:cloud` (capabilities from `/api/tags`: completion, thinking, tools, vision).
Task: "List the files in the current directory." Three tool schemas sent
(list_files, read_file, search_in_files).

| Condition | System prompt | tools param | Channel | Prompt tokens |
|---|---|---|---|---|
| A baseline | full text-protocol (40,369 chars) | no | text | 9,976 |
| B | full text-protocol (40,369 chars) | yes | native | 10,336 |
| C | stripped (198 chars) | yes | native | 422 |
| C round 2 | stripped + fed-back tool result | yes | native (stayed) | — |

Findings:

1. The `tools` param ALONE flips the channel — condition B went native
   with the full text-protocol prompt still present. The system prompt is
   NOT the main suppressor for this model: lever 1 dominates, and
   prompt-stripping is about token cost, not channel selection.
2. Stripped prompt + tools param: 422 vs 9,976 prompt tokens (24x). The
   "schemas are cheaper than prose" hypothesis is confirmed emphatically.
3. History consistency holds: with a synthetic `role:"tool"` result fed
   back in the `_wire_tool_results` wire shape, the model stayed native
   and correctly followed up (read_file on README.md).

# Re-assessment (architect review, 2026-11-08)

Evidence sufficiency: sufficient for the channel-flip decision on
glm-class models. Gaps to close before shipping:

- **Model variance**: one model probed. Replicate on qwen3-coder-next:cloud
  and a local qwen2.5 before making native-first the default; absorb the
  probe into the MODELS-TEST.md harness.
- **Streaming**: tool_call fragments across chunks are already merged
  (`merge_tool_call_fragments`), but native-first makes this the hot path —
  needs a streaming-specific test pass, including interrupted streams.
- **Approval gates**: native calls must flow through the same ApprovalGate
  as text-channel calls (auto-approve rules, explain option). Verify no bypass.
- **Skills channel**: skills are text-protocol. v1: keep skills on the text
  channel (hybrid prompt) — they are opt-in and rare. Wrapping skills as
  tools is a later option.
- **MCP**: MCP tools register dynamically; v1 excludes them from the tools
  param (schema generation for them is follow-up work).
- **WRITE/EDIT/RUN/FILE**: file ops have tool equivalents (write_file,
  replace_in_file, run_command), but text blocks are more context-efficient
  for large content. v1: keep the text blocks for file-write/shell in the
  stripped prompt; native tools for read/search/list. Revisit later.
- **OpenAI backend parity**: `/v1` accepts tools too. Implement both
  backends behind the same solicitation switch, or gate v1 to
  Ollama-native first.
- **Non-tool models**: auto-select text mode via the `tools` capability
  flag from `/api/tags`; the CLI flag forces text mode regardless.

# Decision: repurpose --no-native-tools

The existing debug flag `--no-native-tools` (currently: disable merging
native tool_calls into the pipeline) becomes the legacy text-protocol
mode flag. A new `--no-text-tools` opt-in was considered and rejected.

- **Polarity**: native-first is the better default (24x token reduction,
  channel stability across rounds), so an opt-out flag is the right shape.
  Two negative flags would invite nonsense combinations; opt-in would hide
  the win.
- **Semantics shift**: the flag now controls SOLICITATION (tools param +
  stripped prompt), not the merge. The tolerance catch — merging unsolicited
  native calls from beam/mistral-class models — stays active in ALL modes;
  removing it would break those models in text mode.
- **Backward compat**: the flag was documented as an A/B debug flag; for
  text-protocol models the new meaning is a superset of the old. Update
  help text and README.

Final mode matrix (supersedes the design-phase matrix above):

| Mode | tools param | system prompt | merge catch |
|---|---|---|---|
| Default, tools-capable model | yes | stripped (+ text blocks for WRITE/EDIT/RUN/FILE) | yes |
| Default, non-tool model (auto via /api/tags) | no | full text protocol | yes |
| --no-native-tools | no | full text protocol | yes |

# Implementation notes (2026-11-08)

All roadmap items shipped; full test suite green; live e2e verified on
glm-5.3-flash:cloud (native call → merge → execute → observation → correct
final answer, 34% KV-cache on the follow-up call).

- **Tool schemas**: `tools_schemas()` in `ollama_agent/tools/__init__.py`
  converts the existing flat `parameters` attribute ({name: {type,
  description, required}}) to JSON Schema — no hand-written schemas. 39
  schemas built at session start. Prose-only tools (web_fetch, web_search,
  image-analysis, google_search, llm_query) gained `parameters` attributes.
  MCP tools are INCLUDED: MCPTool already exposes `parameters` (converted
  from its input_schema), so they ride along with real schemas.
- **Capability detection**: `ChatSession._model_supports_tools()` queries
  `/api/tags`, caches per (host, model), degrades to text mode on failure.
  Re-checked on `/llm` backend swaps.
- **Prompt branch**: `build_system_prompt(native_tools=...)` — native mode
  uses AGENT_NATIVE_TOOLS_RULES + AGENT_NATIVE_CALL_RULE (constants.py) and
  the compact `tools_native_prompt()` instead of the per-tool prose listing.
  WRITE/EDIT/FILE/RUN text blocks stay. Skills stay on the text channel
  (AGENT_CALL_RULE appended when skills are on).
- **Backends**: `tools_schemas` param on both backends; sent on every
  /api/chat call (streaming + blocking) and /v1 create. OpenAI fallback
  ladder gained a "tools" rejection retry (solicitation drops, text
  channel + merge catch remain).
- **Flag rewire**: `--no-native-tools` = solicitation off (legacy text
  mode). The merge catch is now UNCONDITIONAL — snapshot in _call_model and
  merge in process_actions no longer check the flag (beam/mistral-class
  reflex calls must merge in all modes). Startup banner shows
  "Native tools: on/off".
- **Init order**: backend creation moved after tools/native_solicit are
  set (schema building reads them).
- **Tests**: flag-semantics tests updated (merge always-on; flag gates
  solicitation). Streaming-fragment tests (split args, parallel calls keyed
  by index, native dict-args continuation, interrupted stream → no
  malformed call, empty-args single chunk) and approval-gate parity tests
  (risky native call prompts, auto-safe skips gate, decline → [Skipped]
  observation, parallel risky calls gated individually, params_explicit
  empty-params legitimacy) added in tests/test_tool_calls.py
  (TestStreamingFragments, TestApprovalGateParity). Remaining:
  MODELS-TEST.md absorption.

E2E numbers (glm-5.3-flash:cloud, "list files" task): native call = 6
output tokens vs 43 text-protocol; full agent prompt with 39 schemas =
7,033 prompt tokens vs ~9,976 for the old text tools section alone.

# Field case: channel-mixing blob in the native name slot (2026-11-08)

First real-world native-mode session (glm-5.3-flash:cloud, "three snakes"
task) surfaced the empty-schema bug the e2e missed:

1. Model called py_compile natively with only {"path": ...} — the required
   `action` param was invisible because py_compile had NO `parameters`
   attribute; its schema shipped as {"properties": {}, "required": []}.
2. After the "Unknown action ''" failure, the model attempted text-protocol
   recovery (RUN block + prose + a TOOL: marker) while the chat template
   forced native tool-call structure — the text poured into the name slot.
3. uhu failed it as "Unknown tool '<500-char blob>'" (fail-safe, correct).
4. Round 3: clean native run_command recovery. The model was fine; the
   environment was broken.

Fixes shipped:
- `parameters` attributes added to the four prose-only tools missed by the
  first pass: py_compile (with action enum), token_count, calculator,
  google_calendar. All 39 schemas now populated.
- `audit_tools_schemas()` in tools/__init__.py: session-start warning for
  any tool that takes params but ships an empty schema (parameterless
  tools exempt via _PARAMLESS_TOOLS). The gap is now visible, not silent.
- `normalize_tool_calls` degrades >64-char native names to a
  `_malformed_native_call` entry with a 512-char `_raw` preview — clear
  actionable failure instead of a blob in the "Unknown tool" message.
- Regression tests: blob degradation + normal-name pass-through
  (TestStreamingFragments).

Lesson: schema generation assumed every tool carries `parameters`; the
"list files" e2e never exercised a multi-param tool, so the gap sailed
through. The audit makes the class of bug self-announcing.

# Channel split: file content stays on the text blocks (2026-11-08)

Design decision after the first real-world sessions: WRITE/EDIT/FILE text
blocks are the TRANSPARENT path for file content — colored diffs, review
prompts, in-memory rollback, .uhu/.cache/ file caching. The duplicating
tools (read_file, write_file, replace_in_file) show a raw JSON params dump
at confirmation instead — no diff, no rollback integration.

Native mode now enforces the split structurally, not just by prompt:

- `tools_schemas()` excludes read_file/write_file/replace_in_file
  (_NATIVE_TEXT_DUPLICATES) — the model can't be tempted by what it
  can't see. 36 schemas ship instead of 39.
- AGENT_NATIVE_TOOLS_RULES actively guides: FILE: to read, WRITE: to
  create, EDIT: to modify — "the transparent path (diffs, review,
  rollback)".
- tools_native_prompt() carries the same guidance.
- No-text-equivalent fs tools stay native: search_in_files, list_files,
  find_file, peek_file, copy_file, move_file, mkdir.
- The merge catch still handles unsolicited calls to excluded tools
  (beam/mistral reflex), and text mode (--no-native-tools) keeps the
  full tool set — the exclusion is native-mode only.

Tests: TestNativeSchemaExclusions (exclusion set + guidance text).

# Channel policy: tunable "tools" vs "hybrid" (2026-11-08)

Second field case (WRITE-in-name): the model, told to CREATE a file via a
WRITE: text block, poured the marker + 12,810 tokens of content into the
native tool_call structure — same channel-mixing as the RUN blob. The
channel-split hypothesis was falsified: in native mode, GLM-class models
route ALL action-intent through the tool-call structure; text-block docs
in native mode are an invitation to collide, not a usable second channel.

Hardcoding either policy was rejected (user decision): the fix is a TUNABLE
channel policy instead of a bet.

- **"tools" (default)**: single-channel native mode. Text-block docs
  STRIPPED from the base prompt (AGENT_SYSTEM_PROMPT_NATIVE), all actions
  via tool calls, file tools included in the schemas array. Anti-confusion
  default, field-evidenced.
- **"hybrid"**: the transparency play — text blocks documented + preferred
  for file content, duplicating tools (read_file/write_file/
  replace_in_file) excluded from schemas. Available for users who want
  diffs/review/rollback on file ops and accept the mixing risk.

Configuration: `native_tools.channel` in .ollama_agent.json ("tools" |
"hybrid", default "tools"). Startup banner shows the active channel.

Implementation: build_system_prompt(native_channel=...),
tools_schemas(channel=...), tools_native_prompt(channel=...),
session reads config into _native_channel. Tests:
TestNativeSchemaExclusions (both channels + prompt branches).

Open: a CLI flag override (--native-channel) and transparency parity for
the file tools (diff-style confirmation instead of raw JSON dump) — the
latter would make "tools" channel fully match the text blocks' review
experience and is the real fix for the original transparency concern.

**SUPERSEDED (2026-11-08, session 2):** the config-based policy above is
replaced by the `--tools-mode` CLI flag (hybrid default, no config) and the
hybrid redefinition (backup tools, not exclusion) — see the DESIGN UPDATE
section at the top of this doc. The "cornered model" re-reading of the two
field cases reverses the exclusion decision: mixing was caused by removing
the native option while demanding text output, not by having both options.
Pre-tools-param field history: models switched fluently and safely between
WRITE blocks and write_file when both paths were genuinely available.

# Open questions

- Do qwen/glm-class models emit PARALLEL native calls reliably, and does
  the approval gate batch them sensibly?
- Token accounting: tools-param schemas count toward prompt_eval_count
  (PoC: B=10,336 vs A=9,976) — factor into context/TPM accounting.
- Should the stripped prompt keep the FILE: read-back block, or route all
  reads through the read_file tool in native mode?
