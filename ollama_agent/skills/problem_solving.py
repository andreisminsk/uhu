"""problem-solving skill — find solutions to a problem through structured analysis or collaborative interview."""

from .base import Skill


class ProblemSolvingSkill(Skill):
    name = "problem-solving"
    description = "Find solutions to a problem — brainstorm, evaluate, and recommend approaches"
    triggers = ["how do I solve", "how to fix", "solve this problem", "problem solving", "need a solution", "help me figure out", "stuck on", "can't figure out", "what should I do about", "how to overcome"]
    system_prompt = (
        "## problem-solving\n"
        "Find solutions to a problem through structured analysis or collaborative interview.\n"
        "Parameters (JSON object):\n"
        "- problem (string, required): The problem to solve\n"
        "- mode (string, optional, default \"analyze\"): Interaction mode — analyze (one-shot) or interview (guided collaborative session)\n"
        "- approach (string, optional, default \"full\"): Analysis approach — diverge (generate many options), converge (evaluate and pick), full (both)\n"
        "\n"
        "### Analyze mode (default)\n"
        "Produce a structured one-shot problem-solving analysis.\n"
        "\n"
        "If approach is **diverge**: Focus on generating many possible solutions. No evaluation yet.\n"
        "1. **Problem framing** — Restate the problem clearly. Often the stated problem is a symptom of a poorly defined real problem.\n"
        "2. **Constraints & requirements** — What must be true? What can't change? What resources are available?\n"
        "3. **Solution generation** — Multiple approaches, from obvious to creative. No judgment yet. Aim for quantity and variety.\n"
        "\n"
        "If approach is **converge**: Focus on evaluating existing options and picking the best.\n"
        "1. **Problem framing** — Restate the problem clearly.\n"
        "2. **Evaluation** — For each known approach: effort, risk, likelihood of success, side effects.\n"
        "3. **Recommendation** — The best path (or combination), with reasoning.\n"
        "4. **First step** — What to do right now to start solving it. Actionable, concrete.\n"
        "\n"
        "If approach is **full** (default): Do both.\n"
        "1. **Problem framing** — Restate the problem clearly. Often the stated problem is a symptom of a poorly defined real problem.\n"
        "2. **Constraints & requirements** — What must be true? What can't change? What resources are available?\n"
        "3. **Solution generation** — Multiple approaches, from obvious to creative. No judgment yet.\n"
        "4. **Evaluation** — For each approach: effort, risk, likelihood of success, side effects.\n"
        "5. **Recommendation** — The best path (or combination), with reasoning.\n"
        "6. **First step** — What to do right now to start solving it. Actionable, concrete.\n"
        "\n"
        "### Interview mode\n"
        "Conduct a collaborative problem-solving session. Do NOT produce a full analysis upfront.\n"
        "\n"
        "Instead:\n"
        "1. Start by restating the problem to confirm understanding, and ask 1-2 clarifying questions.\n"
        "2. After the user answers, brainstorm together — suggest approaches, ask what they've tried, challenge assumptions.\n"
        "3. Adapt your approach based on what you learn — follow the user's thinking, introduce new angles when stuck.\n"
        "4. When a promising direction emerges, help refine it into a concrete plan.\n"
        "5. End with a clear first step the user can take right now.\n"
        "\n"
        "In interview mode, you are a thinking partner — not an oracle. Brainstorm with the user, "
        "challenge their assumptions respectfully, and help them discover solutions rather than prescribing them. "
        "Ask ONE question at a time. Be curious and collaborative.\n"
        "\n"
        "Consider all relevant context from the conversation — the user's situation, prior discussions, "
        "and any details they've shared. Use that context to make solutions specific and practical rather than generic.\n"
    )
    parameters = {
        "problem": {"type": "string", "required": True, "description": "The problem to solve"},
        "mode": {"type": "string", "required": False, "description": "Interaction mode: analyze (one-shot) or interview (guided collaborative session). Default: analyze"},
        "approach": {"type": "string", "required": False, "description": "Analysis approach: diverge (generate options), converge (evaluate and pick), full (both). Default: full"},
    }

    def execute(self, params, workdir=None, session=None):
        problem = params.get("problem", "")
        mode = params.get("mode", "analyze")
        approach = params.get("approach", "full")
        if not problem:
            return "[Skill error: 'problem' parameter is required for problem-solving]"
        if mode == "interview":
            return (
                f"Begin a collaborative problem-solving session for the following problem.\n\n"
                f"Problem: {problem}\n\n"
                f"Start by restating the problem to confirm understanding, and ask 1-2 clarifying questions. "
                f"Wait for the user's answers before going deeper."
            )
        approach_hint = ""
        if approach == "diverge":
            approach_hint = " Focus on generating many diverse solutions without evaluating them yet."
        elif approach == "converge":
            approach_hint = " Focus on evaluating known options and recommending the best path."
        return f"Perform a structured problem-solving analysis for the following problem:\n\n{problem}{approach_hint}"
