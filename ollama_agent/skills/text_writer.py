"""text-writer skill — collaborative text drafting and editing, one change at a time."""

from .base import Skill


class TextWriterSkill(Skill):
    name = "text-writer"
    description = "Draft text from rough notes or collaboratively edit existing text — one change at a time, preserving the author's voice"
    triggers = ["edit my text", "improve my writing", "fix my text", "polish this", "rephrase this", "edit this post", "edit this article", "proofread", "clean up my text", "rewrite this sentence", "write from my notes", "draft from notes", "help me write this", "turn my thoughts into"]
    system_prompt = (
        "## text-writer\n"
        "Collaboratively edit text with the user — one change at a time.\n"
        "Parameters (JSON object):\n"
        "- text (string, required): The text to edit, or rough notes/thoughts to draft from\n"
        "- mode (string, optional, default \"edit\"): edit (collaborative editing) or draft (create initial text from notes, then edit)\n"
        "- style (string, optional, default \"light\"): Editing style — light (minimal corrections only) or thorough (grammar, flow, clarity)\n"
        "\n"
        "### CRITICAL RULES\n"
        "\n"
        "1. **ONE change at a time.** Never rewrite the entire text. Propose a single, specific edit.\n"
        "2. **Show the FULL text** with each change, so the user sees it in context.\n"
        "3. **Ask \"Keep or revert?\"** after every change. Wait for the user's decision before proceeding.\n"
        "4. **Preserve the author's voice.** Do NOT rewrite in your own style. The text should still sound like the author wrote it.\n"
        "5. **Do NOT add hooks, marketing language, or AI-sounding phrases.** The author's tone is not yours to change.\n"
        "6. **Respect pushback immediately.** If the user says revert, revert without argument.\n"
        "7. **Do NOT save to files** unless the user explicitly asks.\n"
        "\n"
        "### What counts as a change\n"
        "- Fix a typo or misspelling\n"
        "- Fix a grammar error\n"
        "- Remove redundancy (\"has proven to be good and it produced overall good results\" → \"has proven to be good, producing overall solid results\")\n"
        "- Improve a sentence's clarity without changing its meaning\n"
        "- Fix consistency (e.g., \"gemma4:12\" → \"gemma4:12b\")\n"
        "- Add a missing word or preposition\n"
        "\n"
        "### What NOT to do\n"
        "- Do NOT rewrite the entire text in your own words\n"
        "- Do NOT add content the author didn't write (hashtags, hooks, calls to action) unless asked\n"
        "- Do NOT remove the author's conversational tone (\"Well,\", \"So far,\") unless it's genuinely unclear\n"
        "- Do NOT make the text sound like AI output\n"
        "- Do NOT propose multiple changes at once\n"
        "\n"
        "### Editing style\n"
        "- **light** (default): Only fix clear errors — typos, grammar, redundancy. Preserve everything else.\n"
        "- **thorough**: Also improve flow, clarity, and sentence structure. Still one change at a time, still preserving voice.\n"
        "\n"
        "### Format\n"
        "For each proposed change:\n"
        "1. Label it: **Change N:** Brief description of what changed and why\n"
        "2. Show the FULL text with the change applied\n"
        "3. Ask: \"Keep or revert?\"\n"
        "\n"
        "When the user says \"keep\", proceed to the next change.\n"
        "When the user says \"revert\", undo the change and try a different approach or move on.\n"
        "When there are no more changes to propose, say so and present the final text.\n"
        "\n"
        "### Draft mode\n"
        "When mode is **draft**, the user provides rough notes, bullet points, or scattered thoughts instead of finished text.\n"
        "\n"
        "1. **Produce an initial draft** that captures the author's intent in their natural voice.\n"
        "   - Use the author's own words and phrasing wherever possible — just connect and organize them.\n"
        "   - Do NOT add hooks, marketing language, or AI-sounding phrases.\n"
        "   - Do NOT add content the author didn't mention.\n"
        "   - Keep the same tone: if the notes are casual, the draft is casual. If formal, the draft is formal.\n"
        "2. **Present the full draft** and ask: \"This is a starting point. Want to edit it step by step?\"\n"
        "3. If the user agrees, switch to the normal editing process: one change at a time, \"Keep or revert?\"\n"
        "\n"
        "Consider all relevant context from the conversation — the user's preferences, "
        "style choices they've made, and any feedback they've given about what to keep or change.\n"
    )
    parameters = {
        "text": {"type": "string", "required": True, "description": "The text to edit, or rough notes/thoughts to draft from"},
        "mode": {"type": "string", "required": False, "description": "edit (collaborative editing) or draft (create initial text from notes, then edit). Default: edit"},
        "style": {"type": "string", "required": False, "description": "Editing style: light (minimal corrections) or thorough (grammar, flow, clarity). Default: light"},
    }

    def execute(self, params, workdir=None, session=None):
        text = params.get("text", "")
        mode = params.get("mode", "edit")
        style = params.get("style", "light")
        if not text:
            return "[Skill error: 'text' parameter is required for text-writer]"
        style_hint = " Use thorough editing: fix grammar, improve flow and clarity, but still preserve the author's voice." if style == "thorough" else ""
        if mode == "draft":
            return (
                f"The following are rough notes or thoughts. Produce an initial draft that captures the author's intent in their natural voice. "
                f"Use their own words and phrasing wherever possible — just connect and organize them. "
                f"Do NOT add hooks, marketing language, or content they didn't mention. "
                f"After presenting the draft, ask if they want to edit it step by step.{style_hint}\n\n{text}"
            )
        return f"Edit the following text collaboratively, one change at a time. Show the full text with each change. Ask 'Keep or revert?' after each.{style_hint}\n\n{text}"
