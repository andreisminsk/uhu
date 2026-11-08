"""System prompt builder — extracted from session.py and persistence.py.

Centralizes system prompt assembly to eliminate duplication between
ChatSession.__init__ and PersistenceMixin.do_restore.
"""

from datetime import date
from pathlib import Path

from .constants import (
    AGENT_SYSTEM_PROMPT, AGENT_SYSTEM_PROMPT_NATIVE,
    AGENT_TOOLS_RULES, AGENT_CALL_RULE,
    AGENT_NATIVE_TOOLS_RULES, AGENT_NATIVE_TOOLS_RULES_HYBRID,
    AGENT_NATIVE_CALL_RULE,
    get_platform_info, get_platform_shell_guidance,
)


def build_system_prompt(workdir, agent=True, tools=False, skills=False,
                        native_tools=False, native_channel="tools"):
    """Build the complete system prompt for a chat session.

    native_tools=True selects the native-tools mode prompt (NATIVE-TOOLS-SWITCH-ARCH):
    tool schemas travel via the /api/chat tools param, so the text TOOL: protocol
    docs are replaced by compact native-mode rules. Skills stay on the text channel.

    native_channel tunes the policy (see the doc for field evidence):
    - "tools" (default): single-channel — text-block docs stripped from the
      base prompt, ALL actions via tool calls (anti-confusion).
    - "hybrid": text blocks documented + preferred for file content.

    Assembles in order:
    1. Agent base prompt (with date and shell_lang placeholder replaced)
    2. Tool rules (if tools enabled; native variant when native_tools)
    3. Call-and-wait rules (if tools or skills enabled)
    4. Platform shell guidance
    5. Tools system prompt (if tools enabled; compact native note when native_tools)
    6. Skills system prompt (if skills enabled)
    7. User name from config (if set)
    8. Permanent memory (project + agent)

    Returns the assembled system prompt string, or empty string if
    agent/tools/skills are all disabled and no memory/user_name exists.
    """
    parts = []

    if agent:
        base = AGENT_SYSTEM_PROMPT_NATIVE if (native_tools and native_channel == "tools") else AGENT_SYSTEM_PROMPT
        system_prompt = f"Current date: {date.today().isoformat()}\n\n" + base
        info = get_platform_info()
        system_prompt = system_prompt.replace("{shell_lang}", info["shell_lang"])
        if tools and native_tools:
            system_prompt += AGENT_NATIVE_TOOLS_RULES_HYBRID if native_channel == "hybrid" else AGENT_NATIVE_TOOLS_RULES
            if skills:
                system_prompt += AGENT_CALL_RULE  # SKILL: stays on the text channel
            system_prompt += AGENT_NATIVE_CALL_RULE
        else:
            if tools:
                system_prompt += AGENT_TOOLS_RULES
            if tools or skills:
                system_prompt += AGENT_CALL_RULE
        parts.append(system_prompt + get_platform_shell_guidance())

    if tools:
        if native_tools:
            from .tools import tools_native_prompt
            parts.append(tools_native_prompt(channel=native_channel))
        else:
            from .tools import tools_system_prompt
            parts.append(tools_system_prompt(workdir=workdir))

    if skills:
        from .skills import skills_system_prompt
        parts.append(skills_system_prompt())

    # User name from config
    from .tools._config import load_config as _load_cfg
    _cfg = _load_cfg(workdir)
    _user_name = _cfg.get("user_name", "")
    if _user_name:
        parts.append(f"The user's name is '{_user_name}'. Address them by name when appropriate.")

    # Self-help: teach the model to read its own manual when asked about uhu
    if agent or tools:
        parts.append(build_self_help_section())

    # Permanent memory (project + agent)
    from .memory import build_memory_prompt
    mem_prompt, _mem_warnings = build_memory_prompt(workdir)
    if mem_prompt:
        parts.append(mem_prompt)

    return "\n\n".join(parts) if parts else ""


def _find_self_help_doc():
    """Locate uhu's own README.md (the app manual — NOT the user's project README).

    The manual lives in the repo root next to the ollama_agent package, so this
    works when running from source (pip install -e . / direct script) regardless
    of workdir. Non-editable installs don't package it → return None and the
    prompt falls back to the online docs.
    """
    candidate = Path(__file__).resolve().parent.parent / "README.md"
    return str(candidate) if candidate.is_file() else None


def build_self_help_section():
    """Prompt section for answering questions about uhu itself.

    Points the model at the manual's absolute path instead of duplicating the
    manual into the system prompt (which would burn context in every session —
    the file is read on demand via the normal FILE:/read_file flow).
    """
    readme = _find_self_help_doc()
    if readme:
        return (
            "SELF-HELP — answering questions about uhu itself:\n"
            f"- uhu's user manual (README.md) is at: {readme}\n"
            "- When the user asks anything about how to use uhu (what it is, installation, "
            "CLI options, slash commands, confirmation options, feedback loop, tools, "
            "skills, troubleshooting), READ that file first with a **FILE:** block "
            "(or the read_file tool), then answer from it. Never invent flags or "
            "commands — quote the manual.\n"
            "- Read the manual once per conversation; answer follow-up questions "
            "from what you already read.\n"
            "- DEFAULT TO WORKDIR: vague questions like \"tell me about this app\", "
            "\"what is this?\", \"how does it work?\" are ambiguous — they may be about "
            "uhu itself OR about the user's project in the working directory. By default, "
            "assume the user means the workdir project and study it as usual. Add a brief "
            "hint to your answer, e.g. \"(studying the project in the working directory — "
            "if you meant uhu, the coding agent itself, just say so and I'll cover it)\", "
            "so the user can disambiguate later. Only read uhu's manual when the user "
            "clearly means uhu or confirms it after your hint."
        )
    return (
        "SELF-HELP — answering questions about uhu itself:\n"
        "- The local user manual (README.md) is unavailable in this installation. "
        "If the user asks how to use uhu, point them to "
        "https://github.com/andreisminsk/uhu#readme and offer to fetch it with "
        "the web_fetch tool. Never invent flags or commands."
    )


def get_memory_warnings(workdir):
    """Get memory warnings for a workdir (separate so caller can print them)."""
    from .memory import build_memory_prompt
    _, warnings = build_memory_prompt(workdir)
    return warnings
