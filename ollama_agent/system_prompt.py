"""System prompt builder — extracted from session.py and persistence.py.

Centralizes system prompt assembly to eliminate duplication between
ChatSession.__init__ and PersistenceMixin.do_restore.
"""

from datetime import date

from .constants import (
    AGENT_SYSTEM_PROMPT, AGENT_TOOLS_RULES, AGENT_CALL_RULE,
    get_platform_info, get_platform_shell_guidance,
)


def build_system_prompt(workdir, agent=True, tools=False, skills=False):
    """Build the complete system prompt for a chat session.

    Assembles in order:
    1. Agent base prompt (with date and shell_lang placeholder replaced)
    2. Tool rules (if tools enabled)
    3. Call-and-wait rules (if tools or skills enabled)
    4. Platform shell guidance
    5. Tools system prompt (if tools enabled)
    6. Skills system prompt (if skills enabled)
    7. User name from config (if set)
    8. Permanent memory (project + agent)

    Returns the assembled system prompt string, or empty string if
    agent/tools/skills are all disabled and no memory/user_name exists.
    """
    parts = []

    if agent:
        system_prompt = f"Current date: {date.today().isoformat()}\n\n" + AGENT_SYSTEM_PROMPT
        info = get_platform_info()
        system_prompt = system_prompt.replace("{shell_lang}", info["shell_lang"])
        if tools:
            system_prompt += AGENT_TOOLS_RULES
        if tools or skills:
            system_prompt += AGENT_CALL_RULE
        parts.append(system_prompt + get_platform_shell_guidance())

    if tools:
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

    # Permanent memory (project + agent)
    from .memory import build_memory_prompt
    mem_prompt, _mem_warnings = build_memory_prompt(workdir)
    if mem_prompt:
        parts.append(mem_prompt)

    return "\n\n".join(parts) if parts else ""


def get_memory_warnings(workdir):
    """Get memory warnings for a workdir (separate so caller can print them)."""
    from .memory import build_memory_prompt
    _, warnings = build_memory_prompt(workdir)
    return warnings
