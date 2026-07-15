"""Shared constants and configuration."""

import sys

MODEL_TEMPERATURE = 0.0

AGENT_SYSTEM_PROMPT = (
    "Your name is 'uhu'.\n\n"
    "You are a concise coding assistant with file access.\n\n"
    "To WRITE a new file (or completely rewrite one), use this format:\n\n"
    "**WRITE:`hello.py`**\n"
    "```python\n"
    "print('hello')\n"
    "```\n"
    "**EOF:`hello.py`**\n\n"
    "To EDIT an existing file (preferred for small changes — saves context), use:\n\n"
    "**EDIT:`hello.py`**\n"
    "```search-replace\n"
    "<<<<<<< SEARCH\n"
    "old code to find\n"
    "=======\n"
    "new code to replace with\n"
    ">>>>>>> REPLACE\n"
    "```\n"
    "**EOF:`hello.py`**\n\n"
    "Multiple search/replace blocks are allowed in one EDIT.\n"
    "The SEARCH text must match the file exactly (whitespace matters).\n"
    "Use EDIT for modifying existing files — it saves context compared to rewriting.\n"
    "Use WRITE only for new files or complete rewrites.\n\n"
    "Prefer 3 or fewer WRITE/EDIT blocks per response for reviewability.\n"
    "If you must produce more, all will be executed — but smaller batches are easier to review.\n\n"
    "To READ a file into context (no write action), use **FILE:** with **EOF:**:\n\n"
    "**FILE:`README.md`**\n"
    "```markdown\n"
    "# Title\n"
    "Content here.\n"
    "```\n"
    "**EOF:`README.md`**\n\n"
    "The file content will be read from disk and injected into the conversation.\n"
    "The code block content is ignored — the actual file on disk is read.\n"
    "Use this to study existing files before editing them.\n\n"
    "To RUN a shell command, use this format:\n\n"
    "**RUN:**\n"
    "```{shell_lang}\n"
    "python hello.py\n"
    "```\n\n"
    "Supported RUN fence languages: bash, sh, shell, cmd, bat, powershell, ps1, pwsh. "
    "Use the appropriate language for the current platform.\n\n"
    "RULES:\n"
    "- Use **EDIT:** to modify existing files (preferred over WRITE for changes).\n"
    "- Use **WRITE:** only for new files or complete rewrites.\n"
    "- Use **FILE:** to read a file into context. Always close with **EOF:**.\n"
    "- Use **RUN:** only when you intend to execute a command.\n"
    "- Plain ```bash blocks without **RUN:** are treated as documentation, not commands.\n"
    "- NEVER omit **WRITE:**, **EDIT:**, or **EOF:** markers. Both are required.\n"
    "- NEVER omit **FILE:** or **EOF:** markers. Both are required.\n"
    "- If a file is accidentally overwritten, previous versions are saved in `.uhu/.cache/` with numeric suffixes (e.g. `README.1.md`).\n"
    "- The path in **WRITE:**/**EDIT:** and **EOF:** must match exactly.\n"
    "- The path in **FILE:** and **EOF:** must match exactly.\n"
    "- ALWAYS include the path in **EOF:** — never write bare **EOF:** without the path.\n"
    "- ALWAYS start **WRITE:**, **EDIT:**, **FILE:**, **RUN:**, **TOOL:**, **SKILL:**, and **EOF:** markers on a NEW LINE. Never place them inline after other text on the same line — they will be missed by the parser.\n"
    "- Use the full relative path (e.g. src/app.py, not just app.py).\n"
    "- Parent directories are created automatically — just use paths like src/app.py in WRITE.\n"
    "- To read a file, use **FILE:**`path` with **EOF:**`path`, or ask the user to /attach or /search it.\n"
    "- You may explain your changes briefly before or after the write/edit/run block.\n\n"
    "OUTPUT DISCIPLINE:\n"
    "- Be CONCISE. Do NOT produce long repetitive lists, enumerations, or descriptions.\n"
    "- Do NOT repeat the same instruction or explanation multiple times.\n"
    "- If you need to study multiple files, use FILE: blocks to read them — do NOT list their contents in prose.\n"
    "- Act with WRITE/EDIT/RUN/FILE blocks rather than describing what you would do.\n"
    "- Keep explanations under 200 words unless the user asks for detail.\n"
    "- If you catch yourself repeating content, STOP and take a different approach.\n\n"
    "FIRST INTERACTION:\n"
    "- When starting a fresh conversation with no prior context, briefly ask the user if they'd like guidance on using this agent.\n"
    "- If the user is interested, use list_files or find_file to discover available guide files in the project, then read and summarize them.\n"
    "- Keep the initial offer to 2-3 sentences. Do not repeat it in later messages.\n"
    "- If the user declines or jumps straight to a task, proceed without mentioning guides again."
)

# Rules appended to the system prompt when tools are enabled.
# These reference TOOL: blocks and specific tool names, so they must
# only be included when the tools system prompt is also present.
AGENT_TOOLS_RULES = (
    "\n\nTOOL RULES:\n"
    "- Use **TOOL:**`read_file`/`search_in_files`/`list_files`/`find_file`/`peek_file` instead of **RUN:** for file operations — they work identically on all platforms and avoid shell quoting issues.\n"
    "- Use **TOOL:**`py_compile` instead of **RUN:** `python -c '...'` for syntax checks, import tests, and quick Python expressions — it is auto-approvable and cross-platform.\n"
    "- NEVER use **RUN:** `python -c '...'` for syntax checks or import tests — use **TOOL:**`py_compile` instead.\n"
    "- For **TOOL:** blocks, the EOF path is the tool name (e.g. **EOF:`read_file`**), NOT the file path being operated on.\n"
    "- If unsure of a file path, use find_file or search_in_files first.\n"
)

# Rule appended when either tools or skills are enabled — both use
# the TOOL:/SKILL: call-and-wait pattern.
AGENT_CALL_RULE = (
    "\n\nCALL RULES:\n"
    "- When you issue a **TOOL:** or **SKILL:** call, STOP your response after the call. "
    "Do NOT write analysis or conclusions that depend on the tool/skill result — you don't have it yet. Wait for the result in the next turn.\n"
)

SKIP_EXT = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
    '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
    '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv', '.ogg', '.flac',
    '.exe', '.dll', '.so', '.dylib', '.o', '.obj', '.pyc', '.pyo', '.class',
    '.woff', '.woff2', '.ttf', '.eot',
    '.db', '.sqlite', '.sqlite3',
}

SAFE_SHELL_COMMANDS_UNIX = {
    # Directory listing and navigation
    'ls', 'tree', 'pwd', 'cd',
    # File viewing
    'cat', 'head', 'tail', 'less', 'more',
    # File info and comparison
    'file', 'stat', 'wc', 'diff', 'cmp',
    # Search and find
    'find', 'grep', 'rg', 'ag', 'ack',
    # Identity and system info
    'which', 'whoami', 'hostname', 'uname',
    # Environment display
    'env', 'printenv',
    # Text processing (read-only in practice)
    'sort', 'uniq',
}

SAFE_SHELL_COMMANDS_WINDOWS = {
    # Directory listing and navigation
    'dir', 'tree', 'cd',
    # File viewing
    'type', 'more',
    # File info and comparison
    'fc', 'comp',
    # Search and find
    'findstr', 'rg', 'ag',
    # Identity and system info
    'where', 'whoami', 'hostname', 'ver',
    # Environment display
    'set', 'print',
}

# Select the appropriate set for the current platform
from .platform import terminal as _terminal
SAFE_SHELL_COMMANDS = _terminal.safe_commands

# Commands that are ALWAYS blocked — never executed, even with auto-approve.
# These are destructive and have no legitimate use in an agentic coder workflow.
BLOCKED_COMMANDS_UNIX = {
    'shutdown', 'reboot', 'poweroff', 'halt', 'init 0', 'init 6',
    'mkfs', 'mkfs.ext4', 'mkfs.ntfs', 'mkfs.vfat', 'mkfs.fat',
    'dd if=', 'rm -rf /', 'rm -rf /*',
}
BLOCKED_COMMANDS_WINDOWS = {
    'shutdown', 'format', 'del /s /q c:', 'del /s /q C:',
    'rmdir /s /q c:', 'rmdir /s /q C:',
}
BLOCKED_COMMANDS = _terminal.blocked_commands

# Commands that always require explicit user confirmation, even with auto-approve.
# These are potentially destructive but may have legitimate uses.
WARNING_COMMANDS_UNIX = {
    'rm', 'rmdir', 'chmod', 'chown', 'kill', 'killall',
    'apt', 'apt-get', 'yum', 'dnf', 'brew', 'pip uninstall',
    'npm uninstall', 'git push', 'git reset --hard', 'git clean',
    'systemctl', 'service',
}
WARNING_COMMANDS_WINDOWS = {
    'del', 'rmdir', 'taskkill', 'sc', 'net', 'netsh',
    'pip uninstall', 'npm uninstall',
    'git push', 'git reset --hard', 'git clean',
}
WARNING_COMMANDS = _terminal.warning_commands

# Tools that are always auto-approved (read-only, no side effects, no network calls).
# These skip the confirmation prompt entirely, similar to safe shell commands.
SAFE_TOOLS = {
    'file_link',        # Generates a file:// URL — no I/O, no side effects
    'read_file',        # Reads a file — read-only
    'search_in_files',  # Searches files — read-only
    'list_files',       # Lists directory — read-only
    'find_file',        # Finds files — read-only
    'peek_file',        # Head/tail of a file — read-only
    'env_info',         # Returns environment info — read-only, no side effects
    'time_now',         # Returns current date/time/timezone — read-only, no side effects
    'mkdir',            # Creates directories — low risk, easily reversible
    'git',              # Read-only git operations (status, diff, log) — no writes
    'calculator',       # Pure math evaluation — no I/O, no side effects
    'token_count',      # Counts tokens in text/files — read-only, no side effects
    'py_compile',       # Check Python syntax, import modules, or run Python expressions 
    'job_list',         # Lists jobs — read-only, no side effects
    'job_result',       # Gets job result — read-only, no side effects
    'job_log',          # Gets job log — read-only, no side effects
}

# ANSI terminal color codes
ANSI_RESET = "\033[0m"
ANSI_LIGHT_GRAY = "\033[37m"
ANSI_AGENT = "\033[93m"  # Bright yellow — used for agent action output
ANSI_TOOL = "\033[97;2;3m"  # Dim bright white italic — used for tool/file read output

# MIME type mapping for binary file reference
MIME_TYPES = {
    # Images
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
    '.gif': 'image/gif', '.bmp': 'image/bmp', '.ico': 'image/x-icon',
    '.webp': 'image/webp', '.svg': 'image/svg+xml',
    '.tiff': 'image/tiff', '.tif': 'image/tiff',
    # Audio
    '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg',
    '.flac': 'audio/flac', '.aac': 'audio/aac', '.m4a': 'audio/mp4',
    '.wma': 'audio/x-ms-wma',
    # Video
    '.mp4': 'video/mp4', '.avi': 'video/x-msvideo', '.mov': 'video/quicktime',
    '.mkv': 'video/x-matroska', '.webm': 'video/webm',
    # Documents
    '.pdf': 'application/pdf',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.ppt': 'application/vnd.ms-powerpoint',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    # Archives
    '.zip': 'application/zip', '.tar': 'application/x-tar',
    '.gz': 'application/gzip', '.bz2': 'application/x-bzip2',
    '.xz': 'application/x-xz', '.7z': 'application/x-7z-compressed',
    '.rar': 'application/vnd.rar',
}

IMAGE_MIME_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/bmp',
    'image/webp', 'image/tiff', 'image/x-icon',
}

# ── Job system constants ──────────────────────────────────────────────
MAX_CONCURRENT_JOBS = 3
MAX_JOB_LOG_LINES = 1000
JOB_NOTIFICATION_PREFIX = "[JOB"

# ── Context conservation limits ───────────────────────────────────────
# The LLM context window is a finite, expensive resource. Large dumps of
# raw data (HTML, verbose tool output, skill reference content) can easily
# consume the entire context, degrading model performance.
# These limits prevent context bloat by truncating observations.

# Maximum characters for a single observation added to conversation context.
# Observations larger than this are truncated with a note showing original size.
# This limit applies to WRITE, EDIT, RUN, and other short-status observations.
MAX_OBSERVATION_CHARS = 4000

# Maximum characters for READ (FILE:) observations in context.
# File reads contain source code that the agent needs to analyze completely.
# Truncating these prevents the agent from understanding the code it's working with.
# The console display is limited separately (200 lines) to prevent terminal flooding,
# but the model must receive the full content to do its job effectively.
MAX_READ_OBSERVATION_CHARS = 70000

# Maximum characters for skill observations in context.
# Skills are intermediate/automated workflows; their output is printed to the
# terminal in full, so the context copy can be aggressively shortened.
MAX_SKILL_OBSERVATION_CHARS = 8000

# Maximum characters for tool observations in context.
# Tools like image-analysis produce detailed output that the model needs in
# full to reason accurately. Unlike skills, there is no way to re-fetch a tool
# result, so truncating too aggressively loses critical information.
MAX_TOOL_OBSERVATION_CHARS = 8000

# Maximum characters for web_fetch results (web pages tend to be very large).
# This is the default max_length parameter for the web_fetch tool.
MAX_WEB_FETCH_CHARS = 3000

# ── LLM Query / Web Fetch settings are now in .ollama_agent.json ──────
# See DEFAULT_CONFIG in ollama_agent/tools/__init__.py for defaults.
# Override via .ollama_agent.json in workdir or home directory.

# Maximum total characters for all observations combined in one action round.
# Prevents a single round of actions from consuming too much context.
# Set high enough to accommodate full file reads (the agent needs complete
# source code to do analysis and editing). Short observations (WRITE/EDIT/RUN
# status messages) are tiny; the bulk comes from FILE: reads which are
# already capped per-file by MAX_READ_OBSERVATION_CHARS.
MAX_TOTAL_OBSERVATION_CHARS = 120000

# Maximum characters printed to console for tool/skill results.
# Tool output (especially web_fetch) can be huge — this prevents megabytes of
# HTML/script from flooding the terminal. The full result still goes into the
# observation (truncated for context by MAX_SKILL_OBSERVATION_CHARS), but only
# this many chars are shown on screen.
MAX_CONSOLE_DISPLAY_CHARS = 2000

# Maximum number of WRITE/EDIT actions executed in a single batch.
# When the model produces many file changes at once, this limit forces a pause
# after MAX_BATCH_WRITES files, giving the user a chance to review progress
# before continuing. The feedback loop will call the model again to produce
# the remaining changes. This prevents accidental mass overwrites.
MAX_BATCH_WRITES = 3

# Loop detection thresholds
MAX_IDENTICAL_ACTION_REPEATS = 3   # Skip execution after this many identical action repeats across rounds
LOOP_NUDGE_THRESHOLD = 2           # Add loop warning nudge after this many repeats

# Command category classification for broader loop detection.
# Commands in the same category are considered "similar" for loop detection.
# E.g., "dir", "dir /b", "Get-ChildItem" are all "file_listing" commands.
RUN_COMMAND_CATEGORIES = {
    'file_listing': {
        'dir', 'ls', 'tree', 'find', 'locate', 'where', 'which', 'command',
        'get-childitem', 'gci', 'dir.exe',
    },
    'file_reading': {
        'type', 'cat', 'less', 'more', 'head', 'tail', 'bat',
    },
    'file_search': {
        'findstr', 'grep', 'rg', 'ag', 'ack', 'select-string', 'sls',
    },
}

# Consecutive empty/failed RUN commands before nudging the model to try FILE: instead
MAX_CONSECUTIVE_EMPTY_RUN = 3

# Maximum number of feedback loop rounds (model call → action execution → model call)
MAX_FEEDBACK_ROUNDS = 3


def get_platform_info():
    """Return a dict with platform-specific info: shell_lang, platform_label, shell_label."""
    return {
        'shell_lang': _terminal.shell_lang,
        'platform_label': _terminal.platform_label,
        'shell_label': _terminal.shell_label,
    }


def get_platform_shell_guidance():
    """Return platform-specific shell and command guidance for the system prompt."""
    return _terminal.shell_guidance()
