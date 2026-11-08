# Native Tool_calls Switch — Architecture Notes (design phase)

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
  solicitation). Remaining from the roadmap: streaming-fragment test,
  approval-gate parity test, MODELS-TEST.md absorption.

E2E numbers (glm-5.3-flash:cloud, "list files" task): native call = 6
output tokens vs 43 text-protocol; full agent prompt with 39 schemas =
7,033 prompt tokens vs ~9,976 for the old text tools section alone.

# Open questions

- Do qwen/glm-class models emit PARALLEL native calls reliably, and does
  the approval gate batch them sensibly?
- Token accounting: tools-param schemas count toward prompt_eval_count
  (PoC: B=10,336 vs A=9,976) — factor into context/TPM accounting.
- Should the stripped prompt keep the FILE: read-back block, or route all
  reads through the read_file tool in native mode?
