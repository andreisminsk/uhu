"""Event sounds for uhu — best-effort, fire-and-forget, never blocks or crashes.

Events:
- "done":     the agent finished a round and user feedback is needed
- "question": a confirmation prompt (y/N/...) is being shown
- "warn":     extra warning played after "done" when context exceeds the
              token threshold (see ChatSession._play_done_sound)

Platform support:
- macOS:    afplay + /System/Library/Sounds/*.aiff
- Windows:  winsound (stdlib) SND_ALIAS system sounds, SND_ASYNC
- Linux:    paplay / pw-play with the freedesktop sound theme (candidate chain)
- Headless / other: terminal bell \a (TTY only)

Everything degrades silently: missing binaries, missing sound-theme files,
and absent audio daemons never propagate an error — worst case is silence.
Popen children never produce visible stderr (DEVNULL) and are never waited on.

Muted globally with --no-sound (CLI) or toggled with /sound (slash command).

NOTE: sound.play() is safe to call from any thread, but it is NOT async-safe
against concurrent PlaySound on Windows — winsound.SND_ASYNC serializes
internally, so this is harmless in practice.
"""

import os
import shutil
import subprocess
import sys

_ENABLED = True

# ── Sound definitions ─────────────────────────────────────────────────
# Ordered candidate lists: first playable wins, terminal bell is the
# universal fallback.

_MAC_SOUNDS = {
    "done": "/System/Library/Sounds/Glass.aiff",
    "question": "/System/Library/Sounds/Ping.aiff",
    "warn": "/System/Library/Sounds/Basso.aiff",
}

# freedesktop sound theme file names vary slightly across distros and
# versions — try several candidates per event.
_LINUX_FILES = {
    "done": [
        "complete.oga",
        "bell.oga",
        "message.oga",
    ],
    "question": [
        "dialog-question.oga",
        "message-new-instant.oga",
        "bell.oga",
    ],
    "warn": [
        "dialog-error.oga",
        "bell.oga",
    ],
}
_LINUX_BASE_DIRS = [
    "/usr/share/sounds/freedesktop/stereo",
    "/usr/share/sounds/freedesktop",
]
_LINUX_PLAYERS = ("paplay", "pw-play")

_WIN_SOUNDS = {
    "done": "SystemExclamation",
    "question": "SystemAsterisk",
    "warn": "SystemHand",
}


def set_enabled(enabled: bool):
    """Enable/disable all event sounds (--no-sound sets False, /sound toggles)."""
    global _ENABLED
    _ENABLED = bool(enabled)


def is_enabled() -> bool:
    return _ENABLED


def _bell():
    """Terminal bell — only meaningful when stdout is a TTY."""
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\a")
            sys.stdout.flush()
    except Exception:
        pass


def _mac_play(path: str) -> bool:
    """Spawn afplay for a .aiff file. Returns True if spawned."""
    if not (shutil.which("afplay") and os.path.isfile(path)):
        return False
    try:
        subprocess.Popen(
            ["afplay", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def _linux_play(fname: str) -> bool:
    """Try paplay/pw-play against freedesktop sound-theme candidates.

    Headless-safe: shutil.which() never raises, os.path.isfile() is safe,
    and Popen without wait() means an exited audio daemon just produces
    a dead child with no visible error.
    """
    for player in _LINUX_PLAYERS:
        if not shutil.which(player):
            continue
        for base in _LINUX_BASE_DIRS:
            path = os.path.join(base, fname)
            if not os.path.isfile(path):
                continue
            try:
                subprocess.Popen(
                    [player, path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                continue
    return False


def _win_play(alias: str) -> bool:
    """winsound SND_ALIAS — plays nothing (silently) if the user's sound
    scheme is set to 'No Sounds'. SND_ASYNC = fire-and-forget, no thread."""
    try:
        import winsound
        winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
        return True
    except Exception:
        return False


def _play_once(kind: str):
    """Play one event sound on the current platform; else terminal bell."""
    if sys.platform == "darwin":
        path = _MAC_SOUNDS.get(kind)
        if path and _mac_play(path):
            return
    elif sys.platform == "win32":
        alias = _WIN_SOUNDS.get(kind)
        if alias and _win_play(alias):
            return
    elif sys.platform.startswith("linux"):
        for fname in _LINUX_FILES.get(kind, []):
            if _linux_play(fname):
                return
    _bell()


def play(kind: str):
    """Fire-and-forget event sound. Never raises, never blocks the agent.

    kind: "done" (feedback needed) or "question" (confirmation prompt).
    """
    if not _ENABLED:
        return
    try:
        _play_once(kind)
    except Exception:
        pass
