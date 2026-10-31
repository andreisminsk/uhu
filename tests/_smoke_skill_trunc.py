"""Smoke test: skill observations must pass through truncate_observations untruncated."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ollama_agent.observation import truncate_observations
from ollama_agent.constants import (
    MAX_TOOL_OBSERVATION_CHARS, MAX_READ_OBSERVATION_CHARS,
    MAX_TOTAL_OBSERVATION_CHARS,
)

# Exact prefixes as produced by actions.py execute_skill()
skill = "⚡ [SKILL video-montage (markdown)]: " + "x" * 20000
tool = "[TOOL web_fetch]: " + "y" * 9000
read = "[File: app.py | Lines 1-10 of 10]\n" + "z" * 80000

out = truncate_observations([skill, tool, read])

# 1. Skill passes through untouched
assert skill in out, f"skill truncated! first 80: {out[:80]!r}"

# 2. Tool truncated at MAX_TOOL_OBSERVATION_CHARS with size note
truncated_tool = tool[:MAX_TOOL_OBSERVATION_CHARS]
assert truncated_tool in out, "tool content not truncated at limit"
assert f"[... truncated, {len(tool)} chars total" in out, "tool truncation note missing"

# 3. Read truncated at MAX_READ_OBSERVATION_CHARS
truncated_read = read[:MAX_READ_OBSERVATION_CHARS]
assert truncated_read in out, "read content not truncated at limit"

# 4. Total cap safety net still applies (skill obs included)
big_skill = "⚡ [SKILL mega]: " + "m" * (MAX_TOTAL_OBSERVATION_CHARS + 50000)
out2 = truncate_observations([big_skill])
assert "[... total truncated" in out2, "total cap did not trigger on huge skill"
assert len(out2) <= MAX_TOTAL_OBSERVATION_CHARS + 200, "cap integrity violated"

print("PASS: skill untruncated (%d chars), tool@%d, read@%d, total cap %d enforced"
      % (len(skill), MAX_TOOL_OBSERVATION_CHARS, MAX_READ_OBSERVATION_CHARS,
         MAX_TOTAL_OBSERVATION_CHARS))
