"""what-if skill — explore consequences of a hypothetical scenario."""

from .base import Skill


class WhatIfSkill(Skill):
    name = "what-if"
    description = "Explore consequences of a hypothetical scenario — life decisions, career moves, big changes"
    triggers = ["what if", "what would happen if", "hypothetical", "consequences of", "what if I", "suppose I", "if I were to", "what would be the result", "what are the implications"]
    system_prompt = (
        "## what-if\n"
        "Explore consequences of a hypothetical scenario.\n"
        "Parameters (JSON object):\n"
        "- scenario (string, required): The hypothetical situation to explore\n"
        "\n"
        "When this skill is invoked, reason through the scenario thoroughly:\n"
        "\n"
        "1. **Immediate consequences** — What changes right away? What becomes true the moment this happens?\n"
        "2. **Second-order effects** — What follows from those initial changes? Think cascading impact.\n"
        "3. **Risks & downsides** — What could go wrong? What are the worst-case outcomes?\n"
        "4. **Opportunities & upsides** — What new possibilities open up? What hidden benefits might exist?\n"
        "5. **Reversibility** — Can this be undone? How easily? What would be permanently lost?\n"
        "6. **Blind spots** — What is the person likely not considering? What assumptions might be wrong?\n"
        "7. **Verdict** — A balanced summary of trade-offs. Not a recommendation — just an honest map of the landscape.\n"
        "\n"
        "Consider all relevant context from the conversation — the user's situation, prior discussions, "
        "stated preferences, and any personal details they've shared. Use that context to make the "
        "analysis specific and relevant rather than generic.\n"
        "\n"
        "Be honest and direct. Don't sugarcoat risks or inflate upsides. The goal is clarity, not comfort.\n"
    )
    parameters = {
        "scenario": {"type": "string", "required": True, "description": "The hypothetical situation to explore"},
    }

    def execute(self, params, workdir=None, session=None):
        scenario = params.get("scenario", "")
        if not scenario:
            return "[Skill error: 'scenario' parameter is required for what-if]"
        return f"Explore the following hypothetical scenario:\n\n{scenario}"
