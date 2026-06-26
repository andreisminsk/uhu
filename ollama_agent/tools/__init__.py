"""Tool registry and base class for agentic tools."""

from ._config import DEFAULT_CONFIG, CONFIG_FILENAME, load_config, get_config, save_config
from .web_fetch import WebFetchTool
from .web_search import WebSearchTool
from .image_analysis import ImageAnalysisTool
from .google_calendar import GoogleCalendarTool
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


# ── Tool base class ─────────────────────────────────────────────────────

class Tool:
    """Base class for all tools."""
    name = ""
    description = ""
    system_prompt = ""

    def execute(self, params, workdir=None):
        raise NotImplementedError


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


def tools_system_prompt(enabled_names=None):
    """Build the system prompt section for enabled tools."""
    tools = all_tools() if enabled_names is None else [t for t in all_tools() if t.name in enabled_names]
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
        "Available tools:",
        "",
    ]
    for t in tools:
        parts.append(t.system_prompt)
        parts.append("")
    parts.append("Use /attach-bin <path> to make the model aware of binary files (images, audio, etc.)")
    parts.append("before using image-analysis or other binary-handling tools.")
    return "\n".join(parts)


# Register built-in tools
register(WebFetchTool())
register(WebSearchTool())
register(ImageAnalysisTool())
register(GoogleCalendarTool())
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
register(ModelTestTool())
