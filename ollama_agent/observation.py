"""Observation truncation — extracted from actions.py process_actions.

Centralizes per-observation and total truncation logic to prevent context bloat.
"""

from .constants import (
    MAX_OBSERVATION_CHARS, MAX_READ_OBSERVATION_CHARS,
    MAX_SKILL_OBSERVATION_CHARS, MAX_TOOL_OBSERVATION_CHARS,
    MAX_TOTAL_OBSERVATION_CHARS,
)
from .display import agent_print


def truncate_observations(observations):
    """Truncate a list of observation strings to prevent context bloat.

    Skill and tool observations get aggressive truncation (intermediate output).
    Read observations get a generous limit (agent needs full source code).
    Tools with `do_not_truncate_observations=True` are never truncated.

    Returns the joined result string, or None if observations is empty.
    """
    truncated = []
    for obs in observations:
        is_skill = obs.startswith(("⚡ [SKILL", "[SKILL"))
        is_tool = obs.startswith("[TOOL")
        is_read = obs.startswith("[File:")

        no_truncate = False
        if is_tool:
            from .tools import get as get_tool
            import re
            _m = re.match(r"^\[TOOL\s+(\S+)\]", obs)
            if _m:
                _t = get_tool(_m.group(1))
                if _t and getattr(_t, "do_not_truncate_observations", False):
                    no_truncate = True

        if no_truncate:
            limit = None
        elif is_skill:
            limit = MAX_SKILL_OBSERVATION_CHARS
        elif is_tool:
            limit = MAX_TOOL_OBSERVATION_CHARS
        elif is_read:
            limit = MAX_READ_OBSERVATION_CHARS
        else:
            limit = MAX_OBSERVATION_CHARS

        if limit is not None and len(obs) > limit:
            trunc_note = f"\n[... truncated, {len(obs)} chars total — use FILE: or TOOL: for full content]"
            truncated.append(obs[:limit] + trunc_note)
        else:
            truncated.append(obs)

    result = "\n".join(truncated) if truncated else None
    if result and len(result) > MAX_TOTAL_OBSERVATION_CHARS:
        trunc_note = f"\n[... total truncated, {len(result)} chars — use FILE: or TOOL: for full content]"
        result = result[:MAX_TOTAL_OBSERVATION_CHARS] + trunc_note
        agent_print(f"[Observations truncated to conserve context ({MAX_TOTAL_OBSERVATION_CHARS} char limit)]")
    return result
