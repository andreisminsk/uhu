# As-Is History — Protocol-Native Native-Tool-Call Records

Status: v1 design — replaces the faithful-render-in-history decision of
NATIVE-TOOL-CALLS-ARCH.md (v2), model-facing channel only.
Field driver: render mimicry (see NATIVE-TOOL-CALLS-ARCH.md finding #6 and
the live session of 2026-11-08, beam:cloud).

## Problem

uhu stores the assistant turn in conversation history as TEXT — our
"faithful render" (`[native tool_call N/M: name]` + args JSON), appended to
whatever text content the model produced. History is what the model sees on
the next round. Consequences, observed live:

1. **Mimicry teaching signal.** Function-calling models imitate the most
   salient in-context pattern when degraded. The render IS a text pattern —
   complete with pretty-printed multi-line JSON. beam:cloud copied it
   (degenerate 1/1 numbering, inline-glued after prose), nothing executed,
   rounds burned to max. Our own breaker/escalation texts quote the format
   and re-teach it while correcting it.
2. **Not the model's response as-is.** The design rule "history contains
   what the model actually emitted" was defined from the human's viewpoint.
   On the API level the model emitted STRUCTURED tool_calls (with empty
   content). Storing our text projection of them is beautification injected
   into the model channel — the exact thing the transparency rule was meant
   to prevent, just pointed the other way.

## Chosen approach — protocol-native records

Store the assistant turn **as-is per channel**:

| Channel | Content |
|---|---|
| Assistant history record | `{content}` text as emitted, PLUS `tool_calls` — the raw structured message, the way Ollama's chat API expects it for tool loops |
| Human record (console/log/session JSON) | Faithful render (unchanged display behavior) |

Ollama's chat template renders tool_calls in the model's own trained
format on the server side. The model re-sees its calls in a native shape —
no copyable uhu-text pattern, args fully visible, zero information loss.

### Rules

1. **History shape.** When a turn carries native tool_calls, the history
   entry is a dict shaped like the API's assistant message: text content
   (possibly empty) + `tool_calls` (raw normalized calls — same structure
   the backend received: `{"function": {"name", "arguments"}}`). The
   render text is NOT stored in the model-facing history.
2. **Processing separation.** `_feedback_loop`, `process_actions`,
   recovery and loop detection keep consuming the current call's text
   (render assembled in `_call_model` as today). Only the STORED message
   changes — `history.append` uses the as-is entry; observations continue
   as text user-messages (protocol requirement: tool results travel as
   plain user/system text on the native API anyway... uhu's observations
   already do).
3. **Backends.** Native Ollama: pass the structured entry through directly.
   OpenAI-compatible: same structure is already the /v1 wire shape.
   Persistence: history JSON serializes dicts transparently; add a version
   marker. Pre-2.2 sessions (render-text history) reload unchanged —
   mimicry risk exists only if the user continues an old session with a
   native-calling model; acceptable, documented.
4. **Compaction** (`/compact`): summarizer sees render text for old turns
   (generated from tool_calls on the fly where cheap) — summaries are
   prose, which never mimics.
5. **Breaker/escalation texts** de-formatted: describe the failure without
   quoting any literal render example (existing fix, kept).
6. **Transparency unchanged for humans.** Console render caps, `.log`
   faithful record, `FILE log` audit trail — all untouched. The render is
   also still available for `/history` style tooling via the human record.
7. **Loop detection and recovery**: `_action_signature` and
   `_recover_native_from_render` operate on the current response text —
   not on history — so they are unaffected.

## Implementation plan

- Phase A — session: `_call_model` returns render for processing; a
  separate `_history_entry` (as-is) is stored by `_feedback_loop` /
  `_send` / run_once wrap-up.
- Phase B — persistence: save/load handles structured entries (marker
  + passthrough for text entries).
- Phase C — backends: native passthrough (already a dict-friendly path);
  OpenAI conversion if needed.
- Phase D — validation: mimicry regression (stub loop, echo in history),
  model_test rerun beam:cloud, full pytest.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Some Ollama versions drop tool_calls on replay (typed models) | `extra='allow'` patch already applied to Message; structured entries are first-class |
| Old sessions with render text | Load unchanged; only NEW turns are as-is (documented) |
| `/compact` summarizer sees structured entries | Render-on-the-fly for summarization input only |
| Double storage semantics (human vs model record) | Explicit: `.log`/console stay faithful render; history becomes as-is. Documented in this doc. |
```
**EOF:`dev-docs/AS-IS-HISTORY-ARCH.md**
