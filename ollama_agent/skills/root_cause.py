"""root-cause skill — trace a problem to its underlying causes."""

from .base import Skill


class RootCauseSkill(Skill):
    name = "root-cause"
    description = "Trace an observed problem to its root causes — one-shot analysis or guided interview"
    triggers = ["root cause", "why is this happening", "why does this keep happening", "what's causing", "root cause analysis", "why did this fail", "why is it broken", "what went wrong", "underlying cause", "why won't it work"]
    system_prompt = (
        "## root-cause\n"
        "Trace an observed problem to its underlying causes.\n"
        "Parameters (JSON object):\n"
        "- problem (string, required): The observed symptom or problem to analyze\n"
        "- mode (string, optional, default \"analyze\"): Analysis mode — analyze (one-shot breakdown) or interview (guided diagnostic session)\n"
        "\n"
        "### Analyze mode (default)\n"
        "Produce a structured one-shot root-cause analysis:\n"
        "\n"
        "1. **Symptom definition** — What exactly is happening? Clarify the observable problem.\n"
        "2. **Immediate causes** — What directly produces this symptom? The surface-level \"why\".\n"
        "3. **5 Whys drill-down** — Iteratively ask \"why?\" to push past surface causes. Don't stop at the first answer.\n"
        "4. **Contributing factors** — What conditions enabled or worsened this? Not the cause itself, but the environment that let it happen.\n"
        "5. **Systemic causes** — Underlying patterns, structures, incentives, or habits that sustain the problem.\n"
        "6. **Evidence assessment** — Which causes are confirmed vs. hypothesized? What would confirm or rule them out?\n"
        "7. **Fixes** — What addresses the *root* cause vs. just the symptom? Distinguish band-aids from real solutions.\n"
        "\n"
        "Consider all relevant context from the conversation — the user's situation, prior discussions, "
        "and any details they've shared. Use that context to make the analysis specific rather than generic.\n"
        "\n"
        "### Interview mode\n"
        "Conduct a guided diagnostic session. Do NOT produce a full analysis upfront.\n"
        "\n"
        "Instead:\n"
        "1. Start with 1-2 initial observations about the problem and ask targeted questions.\n"
        "2. After the user answers, analyze their response and ask deeper follow-up questions.\n"
        "3. Adapt your questions based on what you learn — follow unexpected leads.\n"
        "4. Continue probing until you have enough information to identify the root cause.\n"
        "5. When ready, present a final diagnosis with:\n"
        "   - Root cause(s) identified\n"
        "   - Evidence that supports the diagnosis\n"
        "   - Recommended fixes (addressing root cause, not just symptoms)\n"
        "   - What to watch for to confirm the fix worked\n"
        "\n"
        "In interview mode, ask ONE question at a time. Be curious, not judgmental. "
        "The goal is to help the user discover the root cause, not to lecture them.\n"
        "\n"
        "Be honest and direct in both modes. Don't jump to conclusions — follow the evidence.\n"
    )
    parameters = {
        "problem": {"type": "string", "required": True, "description": "The observed symptom or problem to analyze"},
        "mode": {"type": "string", "required": False, "description": "Analysis mode: analyze (one-shot breakdown) or interview (guided diagnostic session). Default: analyze"},
    }

    def execute(self, params, workdir=None, session=None):
        problem = params.get("problem", "")
        mode = params.get("mode", "analyze")
        if not problem:
            return "[Skill error: 'problem' parameter is required for root-cause]"
        if mode == "interview":
            return (
                f"Begin a guided root-cause interview for the following problem.\n\n"
                f"Problem: {problem}\n\n"
                f"Start with initial observations and ask 1-2 targeted questions. "
                f"Wait for the user's answers before going deeper."
            )
        return f"Perform a structured root-cause analysis for the following problem:\n\n{problem}"
