"""Cross-platform filesystem tools: read_file, search_in_files, list_files, find_file, peek_file,
write_file, replace_in_file, copy_file, move_file, mkdir."""

import fnmatch
import os
import re
import shutil
import sys

from ._config import DEFAULT_CONFIG
from ..actions import agent_print


class FilesystemTool:
    """Base class for filesystem tools with shared helpers."""
    name = ""
    description = ""
    parameters = {}

    def __init__(self, config=None):
        self.config = config or DEFAULT_CONFIG

    def execute(self, params, workdir=".", **kwargs):
        raise NotImplementedError


def _resolve_path(path, workdir):
    """Resolve a file path, searching by basename if not found directly.

    If the given path doesn't exist, searches the project tree for a file
    with the same basename. Returns (resolved_path, is_fuzzy) tuple.
    """
    full_path = os.path.join(workdir, path) if not os.path.isabs(path) else path
    if os.path.isfile(full_path):
        return full_path, False

    # Search by basename
    basename = os.path.basename(path)
    skip_dirs = {'.git', '__pycache__', 'node_modules', '.cache', '.uhu', 'build', '.gradle', 'venv', '.venv'}
    for root, dirs, files in os.walk(workdir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        if basename in files:
            found = os.path.join(root, basename)
            return found, True

    return full_path, False


class ReadFileTool(FilesystemTool):
    """Read a file's contents. Cross-platform replacement for cat/type/head/tail."""
    name = "read_file"
    description = "Read the contents of a file. Use instead of cat/type/head/tail commands."
    system_prompt = (
        "## read_file\n"
        "Read a file's contents. Cross-platform replacement for cat/type/head/tail.\n"
        "Parameters (JSON object):\n"
        "- path (string, required): Path to the file (relative to workdir or absolute)\n"
        "- offset (integer, optional, default 1): Line number to start reading from (1-based)\n"
        "- limit (integer, optional, default 2000): Maximum number of lines to read\n"
        "Use this instead of RUN with cat/type/head/tail — it works identically on all platforms."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Path to the file (relative to workdir or absolute)",
            "required": True,
        },
        "offset": {
            "type": "integer",
            "description": "Line number to start reading from (1-based, default 1)",
            "required": False,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of lines to read (default 2000)",
            "required": False,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        path = params.get("path", "")
        offset = max(1, int(params.get("offset", 1)))
        limit = min(5000, int(params.get("limit", 2000)))

        full_path, fuzzy = _resolve_path(path, workdir)
        if not os.path.isfile(full_path):
            return f"Error: File not found: {path}"
        if fuzzy:
            resolved = os.path.relpath(full_path, workdir)
            agent_print(f"[Auto-resolved: {path} -> {resolved}]")

        ext = os.path.splitext(path)[1].lower()
        if ext in {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
                    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
                    '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
                    '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv', '.ogg', '.flac',
                    '.exe', '.dll', '.so', '.dylib', '.o', '.obj', '.pyc', '.pyo', '.class',
                    '.woff', '.woff2', '.ttf', '.eot',
                    '.db', '.sqlite', '.sqlite3'}:
            return f"Error: Binary file ({ext}), use /attach-bin for binary files"

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return f"Error reading file: {e}"

        total_lines = len(lines)
        selected = lines[offset - 1: offset - 1 + limit]
        content = "".join(selected)

        if offset > 1 or len(selected) < total_lines:
            end_line = offset - 1 + len(selected)
            header = f"[File: {path} | Lines {offset}-{end_line} of {total_lines}]\n"
        else:
            header = f"[File: {path} | {total_lines} lines]\n"

        max_chars = min(DEFAULT_CONFIG.get("max_read_file_chars", 50000), 100000)
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n[... truncated, {len(content)} chars total]"

        return header + content


class SearchInFilesTool(FilesystemTool):
    """Search for a regex pattern across files. Cross-platform replacement for grep/findstr."""
    name = "search_in_files"
    description = "Search for a regex pattern in files. Use instead of grep/findstr."
    system_prompt = (
        "## search_in_files\n"
        "Search for a regex pattern across files. Cross-platform replacement for grep/findstr.\n"
        "Parameters (JSON object):\n"
        "- pattern (string, required): Regex pattern to search for\n"
        "- path (string, optional, default '.'): File or directory to search in\n"
        "- glob (string, optional, default '*'): File glob filter, e.g. '*.py' or '*.py:*.js' (colon-separated)\n"
        "- max_results (integer, optional, default 50): Maximum matching lines to return (max 200)\n"
        "Use this instead of RUN with grep/findstr/rg — it works identically on all platforms."
    )
    parameters = {
        "pattern": {
            "type": "string",
            "description": "Regex pattern to search for",
            "required": True,
        },
        "path": {
            "type": "string",
            "description": "File or directory to search in (default: workdir)",
            "required": False,
        },
        "glob": {
            "type": "string",
            "description": "File glob filter, e.g. '*.py' or '*.py:*.js' (colon-separated, default: all files)",
            "required": False,
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of matching lines to return (default: 50)",
            "required": False,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        pattern = params.get("pattern", "")
        search_path = params.get("path", ".")
        glob_filter = params.get("glob", "*")
        max_results = min(200, int(params.get("max_results", 50)))

        if not pattern:
            return "Error: 'pattern' is required"

        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"Error: Invalid regex: {e}"

        full_path = os.path.join(workdir, search_path) if not os.path.isabs(search_path) else search_path

        # Parse glob patterns (colon-separated)
        globs = [g.strip() for g in glob_filter.split(":") if g.strip()] if glob_filter else ["*"]

        skip_dirs = {'.git', '.svn', '__pycache__', 'node_modules', '.cache', '.uhu', '.bak',
                     'venv', '.venv', 'env', '.env', '.tox', 'dist', 'build', '.mypy_cache',
                     '.pytest_cache', '.eggs', 'egg-info'}

        skip_ext = {'.pyc', '.pyo', '.exe', '.dll', '.so', '.dylib', '.o', '.obj',
                    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
                    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
                    '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
                    '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv', '.ogg', '.flac',
                    '.db', '.sqlite', '.sqlite3', '.woff', '.woff2', '.ttf', '.eot'}

        matches = []
        files_searched = 0

        def _search_file(fpath):
            nonlocal files_searched
            rel = os.path.relpath(fpath, workdir)
            ext = os.path.splitext(fpath)[1].lower()
            if ext in skip_ext:
                return
            # Check glob
            if globs != ["*"]:
                matched = any(fnmatch.fnmatch(os.path.basename(fpath), g) for g in globs)
                if not matched:
                    return
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if rx.search(line):
                            matches.append(f"{rel}:{lineno}: {line.rstrip()}")
                            if len(matches) >= max_results:
                                return
                files_searched += 1
            except Exception:
                pass

        if os.path.isfile(full_path):
            _search_file(full_path)
        elif os.path.isdir(full_path):
            for root, dirs, files in os.walk(full_path):
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                for fn in sorted(files):
                    if len(matches) >= max_results:
                        break
                    _search_file(os.path.join(root, fn))
                if len(matches) >= max_results:
                    break
        else:
            return f"Error: Path not found: {search_path}"

        if not matches:
            return f"No matches for '{pattern}' in {search_path} ({files_searched} files searched)"

        total = len(matches)
        header = f"[Found {total} match(es) in {files_searched} file(s) for '{pattern}' in {search_path}]"
        if total >= max_results:
            header += f" (showing first {max_results})"
        return header + "\n" + "\n".join(matches)


class ListFilesTool(FilesystemTool):
    """List directory contents. Cross-platform replacement for dir/ls/tree."""
    name = "list_files"
    description = "List files and directories. Use instead of dir/ls/tree commands."
    system_prompt = (
        "## list_files\n"
        "List files and directories. Cross-platform replacement for dir/ls/tree.\n"
        "Parameters (JSON object):\n"
        "- path (string, optional, default '.'): Directory path to list\n"
        "- recursive (boolean, optional, default false): List recursively (like tree)\n"
        "- glob (string, optional, default '*'): Filter by glob pattern, e.g. '*.py'\n"
        "Use this instead of RUN with dir/ls/tree — it works identically on all platforms."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Directory path to list (default: workdir)",
            "required": False,
        },
        "recursive": {
            "type": "boolean",
            "description": "List recursively (like tree). Default: false (top-level only)",
            "required": False,
        },
        "glob": {
            "type": "string",
            "description": "Filter by glob pattern, e.g. '*.py' (default: show all)",
            "required": False,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        search_path = params.get("path", ".")
        recursive = params.get("recursive", False)
        glob_filter = params.get("glob", "*")

        full_path = os.path.join(workdir, search_path) if not os.path.isabs(search_path) else search_path

        if not os.path.isdir(full_path):
            if os.path.isfile(full_path):
                return f"Error: '{search_path}' is a file, not a directory. Use read_file to read it."
            return f"Error: Directory not found: {search_path}"

        globs = [g.strip() for g in glob_filter.split(":") if g.strip()] if glob_filter and glob_filter != "*" else None

        skip_dirs = {'.git', '__pycache__', 'node_modules', '.cache', '.uhu', '.bak',
                     'venv', '.venv', '.tox', '.mypy_cache', '.pytest_cache'}

        lines = []
        file_count = 0
        dir_count = 0

        def _list_dir(dir_path, prefix=""):
            nonlocal file_count, dir_count
            try:
                entries = sorted(os.listdir(dir_path))
            except PermissionError:
                lines.append(f"{prefix}[Permission denied]")
                return

            dirs_here = []
            files_here = []
            for name in entries:
                full = os.path.join(dir_path, name)
                if os.path.isdir(full):
                    if os.path.basename(full) not in skip_dirs:
                        dirs_here.append(name)
                else:
                    if globs:
                        if any(fnmatch.fnmatch(name, g) for g in globs):
                            files_here.append(name)
                    else:
                        files_here.append(name)

            for name in files_here:
                lines.append(f"{prefix}{name}")
                file_count += 1
            for name in dirs_here:
                lines.append(f"{prefix}{name}/")
                dir_count += 1
                if recursive:
                    _list_dir(os.path.join(dir_path, name), prefix="  " + prefix)

        _list_dir(full_path)

        if not lines:
            return f"[Empty directory: {search_path}]"

        header = f"[{search_path}] {dir_count} dir(s), {file_count} file(s)"
        result = header + "\n" + "\n".join(lines)

        max_chars = 10000
        if len(result) > max_chars:
            result = result[:max_chars] + f"\n[... truncated, {len(lines)} entries total]"

        return result


class FindFileTool(FilesystemTool):
    """Find files by name pattern. Cross-platform replacement for find/dir /s /b."""
    name = "find_file"
    description = "Find files by name pattern. Use instead of find/dir /s /b for locating files."
    system_prompt = (
        "## find_file\n"
        "Find files by name pattern. Cross-platform replacement for find/dir /s /b.\n"
        "Parameters (JSON object):\n"
        "- pattern (string, required): Glob pattern to match file names (e.g. '*.py', 'test_*.py')\n"
        "- path (string, optional, default '.'): Directory to search in\n"
        "- max_results (integer, optional, default 50): Maximum number of results (max 200)\n"
        "Use this instead of RUN with find/dir /s /b — it works identically on all platforms."
    )
    parameters = {
        "pattern": {
            "type": "string",
            "description": "Glob pattern to match file names (e.g. '*.py', 'test_*.py')",
            "required": True,
        },
        "path": {
            "type": "string",
            "description": "Directory to search in (default: workdir)",
            "required": False,
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of results (default: 50)",
            "required": False,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        pattern = params.get("pattern", "*")
        search_path = params.get("path", ".")
        max_results = min(200, int(params.get("max_results", 50)))

        full_path = os.path.join(workdir, search_path) if not os.path.isabs(search_path) else search_path

        if not os.path.isdir(full_path):
            return f"Error: Directory not found: {search_path}"

        skip_dirs = {'.git', '__pycache__', 'node_modules', '.cache', '.uhu', '.bak',
                     'venv', '.venv', '.tox', '.mypy_cache', '.pytest_cache'}

        results = []
        for root, dirs, files in os.walk(full_path):
            dirs[:] = [d for d in sorted(dirs) if d not in skip_dirs]
            for fn in sorted(files):
                if fnmatch.fnmatch(fn, pattern):
                    rel = os.path.relpath(os.path.join(root, fn), workdir)
                    results.append(rel)
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break

        if not results:
            return f"No files matching '{pattern}' found in {search_path}"

        header = f"[Found {len(results)} file(s) matching '{pattern}' in {search_path}]"
        return header + "\n" + "\n".join(results)


class PeekFileTool(FilesystemTool):
    """Show head and tail of a file. Cross-platform replacement for head/tail."""
    name = "peek_file"
    description = "Show the beginning and end of a file. Use instead of head/tail commands."
    system_prompt = (
        "## peek_file\n"
        "Show the beginning and end of a file. Cross-platform replacement for head/tail.\n"
        "Parameters (JSON object):\n"
        "- path (string, required): Path to the file\n"
        "- head (integer, optional, default 20): Number of lines from the start\n"
        "- tail (integer, optional, default 20): Number of lines from the end\n"
        "Use this instead of RUN with head/tail — it works identically on all platforms."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Path to the file",
            "required": True,
        },
        "head": {
            "type": "integer",
            "description": "Number of lines to show from the start (default 20)",
            "required": False,
        },
        "tail": {
            "type": "integer",
            "description": "Number of lines to show from the end (default 20)",
            "required": False,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        path = params.get("path", "")
        head_n = max(1, int(params.get("head", 20)))
        tail_n = max(1, int(params.get("tail", 20)))

        full_path, fuzzy = _resolve_path(path, workdir)
        if not os.path.isfile(full_path):
            return f"Error: File not found: {path}"
        if fuzzy:
            resolved = os.path.relpath(full_path, workdir)
            agent_print(f"[Auto-resolved: {path} -> {resolved}]")

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return f"Error reading file: {e}"

        total = len(lines)
        if total <= head_n + tail_n + 5:
            content = "".join(lines)
            return f"[File: {path} | {total} lines]\n{content}"

        head_lines = lines[:head_n]
        tail_lines = lines[-tail_n:]
        hidden = total - head_n - tail_n

        result = f"[File: {path} | {total} lines, showing {head_n} head + {tail_n} tail]\n"
        result += "".join(head_lines)
        result += f"\n... ({hidden} lines hidden) ...\n"
        result += "".join(tail_lines)
        return result


class WriteFileTool(FilesystemTool):
    """Create or overwrite a file with the given content."""
    name = "write_file"
    description = "Create or overwrite a file with the given content. Auto-creates parent directories."
    system_prompt = (
        "## write_file\n"
        "Create or overwrite a file with the given content. Auto-creates parent directories.\n"
        "Parameters (JSON object):\n"
        "- path (string, required): Path to the file (relative to workdir or absolute)\n"
        "- content (string, required): Content to write to the file\n"
        "- append (boolean, optional, default false): If true, append to the file instead of overwriting\n"
        "Use this instead of RUN: for file creation — it's cross-platform and avoids shell quoting issues."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Path to the file (relative to workdir or absolute)",
            "required": True,
        },
        "content": {
            "type": "string",
            "description": "Content to write to the file",
            "required": True,
        },
        "append": {
            "type": "boolean",
            "description": "If true, append to the file instead of overwriting",
            "required": False,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        path = params.get("path", "")
        content = params.get("content", "")
        append = params.get("append", False)

        if not path:
            return "Error: 'path' is required"
        if content is None:
            return "Error: 'content' is required"

        full_path = os.path.join(workdir, path) if not os.path.isabs(path) else path

        try:
            os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
            mode = "a" if append else "w"
            with open(full_path, mode, encoding="utf-8") as f:
                f.write(content)
            lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            action = "Appended to" if append else "Wrote"
            return f"{action}: {path} ({lines} lines)"
        except Exception as e:
            return f"Error writing file: {e}"


class ReplaceInFileTool(FilesystemTool):
    """Replace exact string matches in a file."""
    name = "replace_in_file"
    description = "Replace one or more exact string matches in a file. Preferred over write_file for small edits."
    system_prompt = (
        "## replace_in_file\n"
        "Replace one or more exact string matches in a file. Preferred over write_file for small edits — saves context.\n"
        "Parameters (JSON object):\n"
        "- path (string, required): Path to the file (relative to workdir or absolute)\n"
        "- replacements (array of objects, required): Each object has:\n"
        "  - search (string): The exact text to find (whitespace matters)\n"
        "  - replace (string): The text to replace it with\n"
        "All replacements are applied sequentially. If any search text is not found, no changes are made.\n"
        "Example:\n"
        "**TOOL:`replace_in_file`**\n"
        "```json\n"
        "{\"path\": \"src/app.py\", \"replacements\": [{\"search\": \"old_function\", \"replace\": \"new_function\"}]}\n"
        "```\n"
        "**EOF:`replace_in_file`**\n"
        "Use this instead of EDIT: blocks when working in tools-only mode."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Path to the file (relative to workdir or absolute)",
            "required": True,
        },
        "replacements": {
            "type": "array",
            "description": "Array of {search, replace} objects",
            "required": True,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        path = params.get("path", "")
        replacements = params.get("replacements", [])

        if not path:
            return "Error: 'path' is required"
        if not replacements:
            return "Error: 'replacements' is required and must be non-empty"

        full_path, fuzzy = _resolve_path(path, workdir)
        if not os.path.isfile(full_path):
            return f"Error: File not found: {path}"
        if fuzzy:
            resolved = os.path.relpath(full_path, workdir)
            agent_print(f"[Auto-resolved: {path} -> {resolved}]")

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return f"Error reading file: {e}"

        applied = 0
        failures = []
        new_content = content

        for i, rep in enumerate(replacements):
            search = rep.get("search", "")
            replace = rep.get("replace", "")
            if search not in new_content:
                preview = search[:80].replace("\n", "\\n")
                failures.append(f"  {i+1}. Not found: ...{preview}...")
                continue
            count = new_content.count(search)
            if count > 1:
                failures.append(f"  {i+1}. Found {count} matches — search text must be unique: ...{search[:60].replace(chr(10), chr(92)+'n')}...")
                continue
            new_content = new_content.replace(search, replace, 1)
            applied += 1

        if not applied:
            return "Error: No replacements applied.\nFailures:\n" + "\n".join(failures)

        if failures:
            # Partial success — write what we can
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return f"Partially applied: {applied} replacement(s) applied, {len(failures)} failed.\nFailures:\n" + "\n".join(failures)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        total_lines = new_content.count("\n") + 1
        return f"Replaced: {path} ({applied} replacement(s) applied, {total_lines} lines)"


class CopyFileTool(FilesystemTool):
    """Copy a file or directory."""
    name = "copy_file"
    description = "Copy a file or directory. Creates destination parent directories automatically."
    system_prompt = (
        "## copy_file\n"
        "Copy a file or directory. Creates destination parent directories automatically.\n"
        "Parameters (JSON object):\n"
        "- source (string, required): Source path (relative to workdir or absolute)\n"
        "- destination (string, required): Destination path (relative to workdir or absolute)\n"
        "- overwrite (boolean, optional, default false): If true, overwrite existing destination"
    )
    parameters = {
        "source": {
            "type": "string",
            "description": "Source path (relative to workdir or absolute)",
            "required": True,
        },
        "destination": {
            "type": "string",
            "description": "Destination path (relative to workdir or absolute)",
            "required": True,
        },
        "overwrite": {
            "type": "boolean",
            "description": "If true, overwrite existing destination",
            "required": False,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        source = params.get("source", "")
        destination = params.get("destination", "")
        overwrite = params.get("overwrite", False)

        if not source:
            return "Error: 'source' is required"
        if not destination:
            return "Error: 'destination' is required"

        full_source = os.path.join(workdir, source) if not os.path.isabs(source) else source
        full_dest = os.path.join(workdir, destination) if not os.path.isabs(destination) else destination

        if not os.path.exists(full_source):
            return f"Error: Source not found: {source}"
        if os.path.exists(full_dest) and not overwrite:
            return f"Error: Destination already exists: {destination} (use overwrite: true to replace)"

        try:
            os.makedirs(os.path.dirname(full_dest) or ".", exist_ok=True)
            if os.path.isdir(full_source):
                if os.path.exists(full_dest):
                    shutil.rmtree(full_dest)
                shutil.copytree(full_source, full_dest)
                return f"Copied directory: {source} → {destination}"
            else:
                shutil.copy2(full_source, full_dest)
                size = os.path.getsize(full_dest)
                return f"Copied: {source} → {destination} ({size} bytes)"
        except Exception as e:
            return f"Error copying: {e}"


class MoveFileTool(FilesystemTool):
    """Move or rename a file or directory."""
    name = "move_file"
    description = "Move or rename a file or directory. Creates destination parent directories automatically."
    system_prompt = (
        "## move_file\n"
        "Move or rename a file or directory. Creates destination parent directories automatically.\n"
        "Parameters (JSON object):\n"
        "- source (string, required): Source path (relative to workdir or absolute)\n"
        "- destination (string, required): Destination path (relative to workdir or absolute)\n"
        "- overwrite (boolean, optional, default false): If true, overwrite existing destination"
    )
    parameters = {
        "source": {
            "type": "string",
            "description": "Source path (relative to workdir or absolute)",
            "required": True,
        },
        "destination": {
            "type": "string",
            "description": "Destination path (relative to workdir or absolute)",
            "required": True,
        },
        "overwrite": {
            "type": "boolean",
            "description": "If true, overwrite existing destination",
            "required": False,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        source = params.get("source", "")
        destination = params.get("destination", "")
        overwrite = params.get("overwrite", False)

        if not source:
            return "Error: 'source' is required"
        if not destination:
            return "Error: 'destination' is required"

        full_source = os.path.join(workdir, source) if not os.path.isabs(source) else source
        full_dest = os.path.join(workdir, destination) if not os.path.isabs(destination) else destination

        if not os.path.exists(full_source):
            return f"Error: Source not found: {source}"
        if os.path.exists(full_dest) and not overwrite:
            return f"Error: Destination already exists: {destination} (use overwrite: true to replace)"

        try:
            os.makedirs(os.path.dirname(full_dest) or ".", exist_ok=True)
            if os.path.exists(full_dest) and overwrite:
                if os.path.isdir(full_dest):
                    shutil.rmtree(full_dest)
                else:
                    os.remove(full_dest)
            shutil.move(full_source, full_dest)
            return f"Moved: {source} → {destination}"
        except Exception as e:
            return f"Error moving: {e}"


class MkdirTool(FilesystemTool):
    """Create a directory, including any missing parent directories."""
    name = "mkdir"
    description = "Create a directory, including any missing parent directories."
    system_prompt = (
        "## mkdir\n"
        "Create a directory, including any missing parent directories.\n"
        "Parameters (JSON object):\n"
        "- path (string, required): Directory path to create (relative to workdir or absolute)\n"
        "Use this instead of RUN: mkdir — it's cross-platform and avoids shell quoting issues."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Directory path to create (relative to workdir or absolute)",
            "required": True,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        path = params.get("path", "")
        if not path:
            return "Error: 'path' is required"

        full_path = os.path.join(workdir, path) if not os.path.isabs(path) else path

        if os.path.isdir(full_path):
            return f"Directory already exists: {path}"

        try:
            os.makedirs(full_path, exist_ok=True)
            return f"Created directory: {path}"
        except Exception as e:
            return f"Error creating directory: {e}"


# Tool registry
TOOLS = {
    "read_file": ReadFileTool,
    "search_in_files": SearchInFilesTool,
    "list_files": ListFilesTool,
    "find_file": FindFileTool,
    "peek_file": PeekFileTool,
    "write_file": WriteFileTool,
    "replace_in_file": ReplaceInFileTool,
    "copy_file": CopyFileTool,
    "move_file": MoveFileTool,
    "mkdir": MkdirTool,
}
