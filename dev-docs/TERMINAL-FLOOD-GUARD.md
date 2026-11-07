# Terminal Flood Guard — Design

Status: v1 — implemented 2026-11-08, regression tests in
`tests/test_terminal_flood_guard.py`.

## Field failure (2026-11-08, SANDBOX, beam:cloud + glm-5.3-flash:cloud)

A model-driven snake-game development session destroyed the terminal:

1. **Scrollback eviction.** Raw-print snake variants (`os.system('clear')`
   or `\033[2J\033[H` per frame, ~8 fps, run for minutes) streamed thousands
   of lines into macOS Terminal's fixed scrollback (~10k lines). The buffer
   cycled and evicted the entire earlier conversation. Log evidence: 43
   `\033[2J`/`\033[H` pairs across 15+ snake runs.
2. **Alternate-screen stranding.** Curses probes emit `\033[?1049h`
   (enter alt-screen). Killed processes never emit the matching
   `\033[?1049l` (curses cleanup runs on normal exit only). Log evidence:
   4 enters vs 1 leave; the last event was an enter. The alt-screen has NO
   scrollback — everything printed after the stranding (the tail of the
   snake session AND the entire following model-test session) rendered into
   a screen with no history. Terminal state is per-tab, not per-process —
   a finished session leaves the tab stranded for the next one.
3. **Visible-screen blanking.** `\033[2J` clears the visible screen; the
   user's snapshot "started" at the last post-flood output.

The native tool_calls work (NATIVE-TOOL-CALLS-ARCH) exposed this: before it,
beam:cloud's run_commands surfaced as empty responses and never executed.
Now they run — and iterate-run-observe loops on TUI programs flood the
terminal 15 times in one session.

## Design

**Principle: sanitize the console echo, never the captured record.** The
observation returned to the model and written to the log keeps raw bytes
(faithful record). Only the human-facing console stream is guarded.

1. **`neutralize_screen_controls`** (`display.py`) — strips screen-control
   escapes from console text: erase display/scrollback (`J`), private modes
   incl. alt-screen (`?...h/l`), cursor positioning (`H`, `f`, `A-D`, `s`,
   `u`). SGR color codes (`m`) pass through untouched.
2. **Stream cap** (`command_runner.py`) — console echo capped at
   `MAX_STREAMED_LINES` (300) per command; capture continues silently with
   a one-line `[... console streaming suppressed ...]` note. The 60-line
   observation trim already bounded the model-facing record.
3. **Echo sites** — `command_runner` stream, `execute_tool` result echo,
   skill result echo, FILE-read echo (`file_executor.py`) all route through
   the neutralizer.

## Related fix: py_compile auto-approval

`py_compile` was in `SAFE_TOOLS`, making the intended conditional gate in
`actions.py` (`action in ("syntax", "import")` only) dead code —
`action: "run"` (arbitrary code execution) was auto-approved. Removed from
`SAFE_TOOLS`; the conditional gate now governs. Regression tests assert
both the SAFE_TOOLS membership and the confirmation-path behavior.

## Related fix: `[Run rc=None]` race

`_execute_subprocess` read `proc.returncode` without reaping — when stdout
EOF arrived before any queue-empty `poll()` call (fast, quiet commands),
the code was never set and the model was told `[Run rc=None]`. Now
`proc.poll()` reaps before reporting. Found by the flood-guard tests.

## Non-goals

- No filtering of the model-facing observation (faithful record).
- No new confirmation prompts for RUN of TUI programs — the safety gate
  already confirms; the guard only bounds the blast radius.
