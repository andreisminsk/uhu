"""Tool registry and base class for agentic tools."""

from ._config import DEFAULT_CONFIG, CONFIG_FILENAME, load_config, get_config, save_config
from .web_fetch import WebFetchTool
from .web_search import WebSearchTool
from .image_analysis import ImageAnalysisTool
from .google_calendar import GoogleCalendarTool
from .google_search import GoogleSearchTool
from .llm_query import LlmQueryTool
from .fs import ReadFileTool, SearchInFilesTool, ListFilesTool, FindFileTool, PeekFileTool
from .fs import WriteFileTool, ReplaceInFileTool, CopyFileTool, MoveFileTool, MkdirTool
from .py_compile import PyCompileTool
from .file_link import FileLinkTool
from .run_command import RunCommandTool
from .env_info import EnvInfoTool
from .time_now import TimeNowTool
from .http_request import HttpRequestTool
from .git import GitTool
from .browser import BrowserTool
from .android_build import AndroidBuildTool
from .weather import WeatherTool
from .token_count import TokenCountTool
from .calculator import CalculatorTool
from .sleep import SleepTool
from .sys_info import SysInfoTool
from .llm_chat import LlmChatTool
from .ui_automation import UiAutomationTool
from .pytest_tool import PytestTool
from .npm_build import NpmBuildTool


# ── Tool base class ─────────────────────────────────────────────────────

class Tool:
    """Base class for all tools."""
    name = ""
    description = ""
    system_prompt = ""
    do_not_truncate_observations = False
    """If True, observations from this tool are never truncated in context."""

    def execute(self, params, workdir=None):
        raise NotImplementedError


def _flat_params_to_schema(name, description, params):
    """Convert the flat parameters format ({name: {type, description, required}})
    into a JSON Schema function definition for the /api/chat tools param."""
    params = params or {}
    properties = {}
    required = []
    for pname, pdef in params.items():
        if not isinstance(pdef, dict):
            continue
        # JSON Schema type guard (field-found 2026-11-08, mistral-large-4:cloud):
        # "float" is Python-ish, not JSON Schema — Ollama's wire validator
        # hard-rejects the whole tools array with 400 "Invalid tool schema".
        # Map common aliases so one bad declaration can't break the wire.
        t = pdef.get("type", "string")
        if t == "float":
            t = "number"
        prop = {"type": t}
        if pdef.get("description"):
            prop["description"] = pdef["description"]
        if pdef.get("enum"):
            prop["enum"] = list(pdef["enum"])
        if pdef.get("items"):
            prop["items"] = pdef["items"]
        properties[pname] = prop
        if pdef.get("required"):
            required.append(pname)
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


from .mcp import MCPTool  # noqa: E402 — must be after Tool class
from .model_test import ModelTestTool  # noqa: E402 — must be after Tool class

# ── Tool registry ───────────────────────────────────────────────────────

_registry = {}


def register(tool_instance):
    """Register a tool instance."""
    _registry[tool_instance.name] = tool_instance


def get(name):
    """Get a tool by name."""
    return _registry.get(name)


def all_tools():
    """Return all registered tool instances."""
    return list(_registry.values())


def tools_system_prompt(enabled_names=None, workdir=None):
    """Build the system prompt section for enabled tools.
    Filters out tools that have 'enabled: false' in their config.
    """
    from ._config import load_config
    config = load_config(workdir)
    tools_config = config.get("tools", {})
    tools = all_tools() if enabled_names is None else [t for t in all_tools() if t.name in enabled_names]
    # Filter out tools explicitly disabled in config
    tools = [t for t in tools if tools_config.get(t.name, {}).get("enabled", True)]
    if not tools:
        return ""
    parts = [
        "You have access to the following tools. To invoke a tool, use this format:",
        "",
        "**TOOL:`read_file`**",
        "```json",
        '{"path": "src/app.py"}',
        "```",
        "**EOF:`read_file`**",
        "",
        "CRITICAL: The ```json block with parameters is REQUIRED — do NOT write bare **TOOL:** lines without a JSON block.",
        "The EOF path must match the tool name (e.g. **EOF:`read_file`**), NOT the file path being operated on.",
        "When asked to perform multiple operations, produce ALL tool calls in a single response — do not do them one at a time.",
        "Always use the full relative path for file operations (e.g. src/components/App.tsx, not just App.tsx).",
        "",
        "WHEN TO USE TOOLS:",
        "- If you are unsure about a fact, API, library, or current information — use web_search to look it up before answering.",
        "- If you need details from a specific URL or documentation page — use web_fetch to retrieve it.",
        "- Do NOT guess or fabricate information when you can search for the accurate answer.",
        "- Always prefer searching over providing potentially outdated or incorrect information.",
        "",
        "WEB TOOL LADDER — never fall back to curl/wget via run_command for fetching:",
        "- web_fetch: default for page and documentation content.",
        "- If the result ends with '[... truncated]' — retry web_fetch with a larger max_length. Do NOT switch tools.",
        "- http_request: APIs and raw HTTP — custom headers, POST/JSON bodies, status codes, structured output.",
        "- browser: only when web_fetch fails (HTTP error, unsupported content type, empty/JS-rendered content) or the page needs JS rendering, cookies, clicks, or screenshots.",
        "- curl/wget in run_command: LAST RESORT only — shell quoting breaks easily and output is unbounded.",
        "",
        "Available tools:",
        "",
    ]
    for t in tools:
        parts.append(t.system_prompt)
        parts.append("")
    parts.append("Use /attach-bin <path> to make the model aware of binary files (images, audio, etc.)")
    parts.append("before using image-analysis or other binary-handling tools.")
    return "\n".join(parts)


def tools_native_prompt(channel="tools"):
    """Compact tools section for native-tools mode (NATIVE-TOOLS-SWITCH-ARCH).

    Replaces the per-tool prose listing — schemas travel via the /api/chat
    tools param. Keeps only channel-agnostic guidance. channel="hybrid"
    adds the text-block preference for file content (transparency play).
    """
    parts = [
        "TOOLS: available via native tool calls — names, descriptions, and parameters "
        "are provided by the runtime. Invoke tools ONLY via tool calls, not text.\n"
        "WHEN TO USE TOOLS:\n"
        "- Unsure about a fact, API, library, or current information — web_search first.\n"
        "- Need details from a URL — web_fetch (retry with larger max_length if truncated; "
        "escalate to browser for JS-rendered pages; http_request for APIs/raw HTTP; "
        "curl/wget in run_command is a last resort).\n"
        "- When asked to perform multiple operations, emit ALL tool calls in a single response.\n"
        "- Use /attach-bin <path> to make the model aware of binary files (images, audio) "
        "before using image-analysis or other binary-handling tools.\n"
        "- For commands that may take longer than 30s, use job_submit; then sleep, job_list, job_result.\n"
    ]
    if channel == "hybrid":
        parts.append(
            "- File content: PREFER the text blocks — the transparent path (diffs, "
            "review, rollback, caching): READ with FILE:, CREATE with WRITE:, "
            "MODIFY with EDIT:. The file tools (read_file, write_file, "
            "replace_in_file) are available as BACKUP — use them when a text "
            "block fails or feels unnatural.\n"
        )
    else:
        parts.append(
            "- File content: read_file to study, write_file to create, replace_in_file to modify.\n"
        )
    return "".join(parts)


# Tools that duplicate the FILE/WRITE/EDIT text blocks (NATIVE-TOOLS-SWITCH-ARCH).
# Session 2 redefinition: hybrid mode INCLUDES them as backup — the
# "cornered model" re-reading of the two field cases showed mixing was caused
# by removing the native option while demanding text output, not by having
# both. Pre-tools-param field history: models switched fluently between
# WRITE blocks and write_file when both paths were available. The set is kept
# for reference/tests and any future exclusion policy.
_NATIVE_TEXT_DUPLICATES = frozenset({"read_file", "write_file", "replace_in_file"})


def tools_schemas(enabled_names=None, workdir=None, channel="tools"):
    """Build the native tools array for /api/chat (NATIVE-TOOLS-SWITCH-ARCH).

    Same config filtering as tools_system_prompt: tools disabled in
    .ollama_agent.json are excluded. Tools whose schema can't be built are
    skipped (they stay reachable via the text channel). channel="hybrid"
    includes the file tools as BACKUP (text blocks preferred via prompt
    guidance — transparency: diffs, review, rollback); channel="tools"
    (single-channel native) also includes everything.
    """
    from ._config import load_config
    config = load_config(workdir)
    tools_config = config.get("tools", {})
    tools = all_tools() if enabled_names is None else [t for t in all_tools() if t.name in enabled_names]
    tools = [t for t in tools if tools_config.get(t.name, {}).get("enabled", True)]
    out = []
    for t in tools:
        # Duck-typed: most tool classes don't subclass Tool, so build the
        # schema from the flat parameters attribute directly. MCPTool also
        # exposes `parameters` (converted from its input_schema), so MCP
        # tools are included with their real schemas.
        try:
            s = _flat_params_to_schema(t.name, t.description, getattr(t, "parameters", None))
        except Exception:
            continue
        if isinstance(s, dict) and s.get("function", {}).get("name"):
            out.append(s)
    return out


# Tools that legitimately take no parameters (empty schema is correct).
# Anything else shipping an empty schema is a bug — the model would see a
# parameterless tool and guess (field case: py_compile's required 'action'
# was invisible, causing failed calls and channel-mixing recovery).
_PARAMLESS_TOOLS = {"sys_info", "job_list"}


def audit_tools_schemas(workdir=None):
    """Verify every registered tool ships a usable schema for native mode.

    Returns a list of warning strings for tools that take parameters but
    have no `parameters` attribute (prose-only docs). Session start prints
    them so the gap is visible instead of silently degrading the model's
    view. Parameterless tools are exempt via _PARAMLESS_TOOLS.
    """
    warnings = []
    for t in all_tools():
        params = getattr(t, "parameters", None)
        if params:
            continue
        if t.name in _PARAMLESS_TOOLS:
            continue
        # No parameters attribute and not known-parameterless — the tool
        # likely takes params documented only in prose.
        warnings.append(
            f"tool '{t.name}' has no parameters attribute — native schema "
            f"will be empty; add a parameters attribute (see py_compile.py)"
        )
    return warnings


# Register built-in tools
register(WebFetchTool())
register(WebSearchTool())
register(ImageAnalysisTool())
register(GoogleCalendarTool())
register(GoogleSearchTool())
register(LlmQueryTool())
register(ReadFileTool())
register(SearchInFilesTool())
register(ListFilesTool())
register(FindFileTool())
register(PeekFileTool())
register(PyCompileTool())
register(FileLinkTool())
register(WriteFileTool())
register(ReplaceInFileTool())
register(CopyFileTool())
register(MoveFileTool())
register(MkdirTool())
register(RunCommandTool())
register(EnvInfoTool())
register(TimeNowTool())
register(HttpRequestTool())
register(GitTool())
register(BrowserTool())
register(AndroidBuildTool())
register(WeatherTool())
register(TokenCountTool())
register(CalculatorTool())
register(SleepTool())
register(SysInfoTool())
register(LlmChatTool())
register(UiAutomationTool())
register(PytestTool())
register(NpmBuildTool())
from .jobs import JobSubmitTool, JobListTool, JobResultTool, JobCancelTool, JobLogTool

register(ModelTestTool())
register(JobSubmitTool())
register(JobListTool())
register(JobResultTool())
register(JobCancelTool())
register(JobLogTool())
