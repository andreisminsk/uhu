# Sleep Tool v2 — Event-Driven Wait Design

Status: implemented — `ollama_agent/tools/sleep.py`
Scope: `ollama_agent/tools/sleep.py`
Related: `ollama_agent/tools/jobs.py`, `ollama_agent/jobs.py`, `JOB-SYSTEM-CODER.md`

## Problem

Today `sleep` is blind: the model must guess a duration, sleep it, then poll
`job_list`. If the estimate is too long, one round is wasted; if too short,
the model enters a busy poll loop. Goal: make the wait **event-driven** —
exit on the earliest of:

1. timeout (`seconds` elapses)
2. watched `job_id` reaches a terminal state (completed / failed / cancelled)
3. watched `process_id` (PID) is no longer alive

Constraints: stay auto-approved, keep context output tiny, keep Ctrl+C
behavior, no new JobManager API surface.

## API

```json
{"seconds": 300, "job_id": "custom-001", "process_id": 1234}
```

| Param        | Type    | Default | Notes                                                        |
|--------------|---------|---------|--------------------------------------------------------------|
| `seconds`    | int     | 600     | Required in plain mode; optional in watch mode (timeout cap) |
| `job_id`     | string  | —       | Optional watcher: JobManager job                             |
| `process_id` | int     | —       | Optional watcher: OS process PID                             |

All modes:

- No watchers → current behavior (plain sleep, unchanged contract).
- Watch mode → `seconds` becomes the **timeout**; earliest event wins.

## Behavior

### Validation (fail fast, before any sleeping)

- `seconds`: int, 0 < n <= 600 (clamped to 600 as today).
- `job_id`: must exist in the active JobManager — checked via
  `mgr.get_result(job_id)` returning something other than `not_found`.
  Unknown id → immediate error observation, no sleep.
- `process_id`: must be a positive int. Dead-at-check PID → immediate return
  `{"event": "process_finished", "waited": 0}` (the event already happened).
- Manager missing (jobs disabled) → job watch degrades to plain sleep with a
  note in the result; never crashes.

### Polling loop (1s tick, as today)

Each tick checks three exit conditions in order:

1. `elapsed >= seconds` → event: `timeout`
2. job terminal → event: `job_finished`, with `job_status`
3. PID not alive → event: `process_finished`

Countdown line shows all watchers:

```
[Waiting... 240s remaining | running jobs: 2 | job custom-001: running | pid 1234: alive]
```

Ctrl+C → `{"event": "interrupted", "waited": N}` — the model learns how far
the round got instead of losing state.

### Return contract

Structured dict (matching the job tools), payload deliberately **excluded** —
the model fetches output via `job_result`:

```json
{"event": "job_finished", "job_id": "custom-001", "job_status": "completed", "waited": 42}
{"event": "timeout", "waited": 300, "note": "job custom-001 still running — check job_list"}
{"event": "process_finished", "process_id": 1234, "waited": 5}
{"event": "interrupted", "waited": 17}
```

## Component Breakdown

```
SleepTool.execute(params)
│
├─ parse: seconds (default 600, cap 600), job_id?, process_id?
├─ validate upfront (fail fast — don't sleep on bad input)
│    job_id  → mgr = get_active_manager(); get_result(id) != 'not_found'
│    process → _pid_alive(pid) — may already be finished → return immediately
│
└─ 1s polling loop (unchanged cadence) — each tick checks:
     ① elapsed >= seconds            → "timeout"
     ② job terminal                  → "job_finished" (+job_status)
     ③ not _pid_alive(pid)           → "process_finished"
```

New dependencies (lazy imports inside `execute()` — avoids circular import;
`jobs.py` already lazily imports the registry the same way):

- `from .jobs import get_active_manager` — status source
- `_pid_alive(pid)` helper, tiered:
  1. `psutil` if installed (best semantics; detects zombies via `status()`)
  2. POSIX `os.kill(pid, 0)` (`ProcessLookupError` = dead;
     `PermissionError` = alive, owned by another user)
  3. Shell fallback (`ps -p` on POSIX, `tasklist` on Windows)

## Decision Rationale

- **1s polling over blocking primitives** — portable across POSIX/Windows,
  one loop serves three watchers, latency bounded at 1s (irrelevant here),
  preserves countdown UX and Ctrl+C. `waitpid` / `WaitForSingleObject` cannot
  watch unrelated PIDs *and* a foreign job system simultaneously.
- **`mgr.get_result()` as the terminal-state source** — already returns
  `(status, result)` for running jobs; zero changes to the job system; uses a
  tested code path. A new `JobManager.wait_job()` with a `threading.Event`
  would be more precise but splits wait logic across two modules, loses the
  unified countdown/timeout semantics, and still cannot watch external PIDs.
- **Fail-fast validation before sleeping** — an unknown job_id or dead PID
  must return an observation immediately; sleeping 600s to then report "not
  found" would be the worst failure mode.
- **`seconds` optional in watch mode (default 600)** — a watcher *is* a
  duration bound; requiring both would be redundant.
- **Payload excluded** — keeps the observation within the 8k tool tier; the
  caller has `job_result` for output.

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| PID reuse (process died, PID recycled) | Watcher never fires; `seconds` timeout still bounds the wait. Note in prompt text. Advanced (out of scope): psutil `create_time` pinning. |
| Zombie child on POSIX seen as alive | `os.kill(pid, 0)` cannot detect zombies; psutil tier (when installed) can via `status()`. Timeout bounds the wait regardless. |
| CPU cost | Unchanged — same 1s tick as current plain sleep. |
| Manager missing / jobs disabled | Lazy import returns `None` → degrades to plain sleep with a note. |
| Model passes both `job_id` and `process_id` | Supported — earliest event wins; result says which watcher fired. |

## Operational Concerns

- Countdown line must be cleared on **every** exit event (existing `\r`
  overwrite pattern).
- System-prompt text updated to promote the recommended pattern:

```
job_submit → sleep({"seconds": est, "job_id": X}) → job_result
```

This replaces sleep-then-list-then-result and saves one full feedback round
per job.
- Auto-approved status is preserved (no side effects; watchers are read-only).

## Example Flows

Typical (recommended) job flow:

```
Tool: job_submit {"name": "encode", "type": "custom", "command": "ffmpeg ..."}
→ {"job_id": "custom-001", "status": "submitted"}

Tool: sleep {"seconds": 120, "job_id": "custom-001"}
→ {"event": "job_finished", "job_id": "custom-001", "job_status": "completed", "waited": 87}

Tool: job_result {"job_id": "custom-001"}
→ output
```

Timeout path:

```
Tool: sleep {"seconds": 60, "job_id": "custom-001"}
→ {"event": "timeout", "waited": 60, "note": "job custom-001 still running — check job_list"}
```
