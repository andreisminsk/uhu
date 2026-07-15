"""File executor — extracted from actions.py for testability.

Handles WRITE, EDIT, READ (FILE:) operations, file caching, and rollback.
"""

import os
from pathlib import Path

from .constants import SKIP_EXT
from .display import agent_print, tool_print
from .edit_utils import make_edit_summary, make_unified_diff
from .matching import find_match_in_content


class FileCache:
    """Manages file caching to .uhu/.cache/ with versioned copies."""

    def __init__(self, workdir, enabled=True):
        self.workdir = workdir
        self.enabled = enabled

    def cache(self, path, content):
        """Save a copy of file content to .uhu/.cache/ and return a file:// URL.

        Each cache write gets an incrementing numeric suffix before the extension
        (e.g. README.1.md, README.2.md) so multiple versions are preserved.
        Returns the file:// URL, or None if caching is disabled or fails.
        """
        if not self.enabled:
            return None
        cache_dir = os.path.join(self.workdir, ".uhu", ".cache")
        if os.path.isabs(path):
            try:
                rel_path = os.path.relpath(path, self.workdir)
            except ValueError:
                rel_path = os.path.basename(path)
        else:
            rel_path = path
        base, ext = os.path.splitext(rel_path)
        n = 1
        while True:
            suffixed_rel = f"{base}.{n}{ext}" if ext else f"{rel_path}.{n}"
            cache_path = os.path.join(cache_dir, suffixed_rel)
            if not os.path.exists(cache_path):
                break
            n += 1
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            return None
        return Path(cache_path).resolve().as_uri()


class RollbackManager:
    """Tracks pre-edit file snapshots and rolls back on failure."""

    def __init__(self, workdir):
        self.workdir = workdir
        self._snapshots = {}

    def save(self, path, content):
        """Save file content before modification. Only saves the first version."""
        if path not in self._snapshots:
            self._snapshots[path] = content

    def rollback(self, modified, created):
        """Restore files to pre-edit state and remove newly created files."""
        for path in modified:
            if path in self._snapshots:
                full_path = os.path.join(self.workdir, path) if not os.path.isabs(path) else path
                os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(self._snapshots[path])
        for path in created:
            full_path = os.path.join(self.workdir, path) if not os.path.isabs(path) else path
            if os.path.isfile(full_path):
                try:
                    os.remove(full_path)
                except OSError:
                    pass


class FileExecutor:
    """Executes WRITE, EDIT, READ operations with confirmation and caching.

    Args:
        workdir: Working directory for file operations.
        ctx_size: Context window size (for read truncation).
        cache: FileCache instance.
        rollback: RollbackManager instance.
        confirm_fn: Callback for confirmation prompts.
        show_diff: Whether to show diffs automatically.
        log_fn: Optional callback for logging (role, message).
    """

    def __init__(self, workdir, ctx_size=4096, cache=None, rollback=None,
                 confirm_fn=None, show_diff=False, log_fn=None):
        self.workdir = workdir
        self.ctx_size = ctx_size
        self.cache = cache or FileCache(workdir)
        self.rollback = rollback or RollbackManager(workdir)
        self._confirm = confirm_fn
        self.show_diff = show_diff
        self._log = log_fn or (lambda role, msg: None)

    def _full_path(self, path):
        if os.path.isabs(path):
            return path
        return os.path.join(self.workdir, path)

    def execute_write(self, action):
        """Execute a WRITE action."""
        path = action["path"]
        lines = action["code"].count("\n") + 1
        full_path = self._full_path(path)
        diff_text = None
        new_content = action["code"]
        if not new_content.endswith("\n"):
            new_content += "\n"
        if os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    old_content = f.read()
                diff_text = make_unified_diff(path, old_content, new_content)
            except Exception:
                pass
        else:
            diff_text = make_unified_diff(path, "", new_content)
        if self._confirm and not self._confirm(
            f"[WRITE] {path} ({lines} lines)", path=path, diff_text=diff_text
        ):
            agent_print("[Skipped]\n")
            return None
        try:
            os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            file_url = self.cache.cache(path, new_content)
            obs = f"[Wrote: {path} ({lines} lines)]"
            display_msg = obs
            if file_url:
                display_msg += f" (cached: {file_url})"
            agent_print(display_msg + "\n")
            return obs
        except Exception as e:
            msg = f"[Write failed: {e}]"
            agent_print(msg + "\n")
            return msg

    def execute_edit(self, action):
        """Execute an EDIT action with search/replace blocks."""
        path = action["path"]
        edits = action["edits"]
        full_path = self._full_path(path)

        if not os.path.isfile(full_path):
            basename = os.path.basename(path)
            suggestion = ""
            for root, dirs, files in os.walk(self.workdir):
                dirs[:] = [d for d in dirs if d not in
                           {'.git', '__pycache__', 'node_modules', '.cache', '.uhu', 'build', '.gradle'}]
                if basename in files:
                    found = os.path.relpath(os.path.join(root, basename), self.workdir)
                    suggestion = f" Did you mean {found!r}?"
                    break
            msg = f"[EDIT FAILED: {path} does not exist. Use WRITE for new files.{suggestion}]"
            agent_print(msg + "\n")
            return msg

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                original_content = f.read()
        except Exception as e:
            msg = f"[EDIT FAILED: cannot read {path}: {e}]"
            agent_print(msg + "\n")
            return msg

        if not edits:
            msg = f"[EDIT FAILED: {path} — no valid search/replace blocks found]"
            agent_print(msg + "\n")
            return msg

        current_content = original_content
        edits_applied = []
        failures = []

        for search_text, replace_text in edits:
            match = find_match_in_content(current_content, search_text)
            if match is None:
                failures.append(search_text)
                continue
            start, end, quality = match
            file_lines = current_content.split('\n')
            new_lines = file_lines[:start] + replace_text.split('\n') + file_lines[end:]
            current_content = '\n'.join(new_lines)
            edits_applied.append((start, end, quality, search_text, replace_text))

        if not edits_applied:
            snippet_lines = original_content.split('\n')[:20]
            snippet = '\n'.join(snippet_lines)
            if len(snippet_lines) < len(original_content.split('\n')):
                snippet += f"\n... ({len(original_content.split(chr(10)))} lines total)"
            msg = f"[EDIT FAILED: {path} — search text not found]\nFile content:\n{snippet}"
            agent_print(msg + "\n")
            return msg

        if failures:
            failed_snippets = []
            for i, f_text in enumerate(failures):
                preview = f_text[:80].replace('\n', '\\n')
                failed_snippets.append(f"  {i+1}. ...{preview}...")
            msg = (
                f"[EDIT FAILED: {path} — {len(failures)} of {len(edits)} search block(s) not found. "
                f"File left unchanged.]\n"
                f"Missing search blocks:\n" + '\n'.join(failed_snippets)
            )
            agent_print(msg + "\n")
            return msg

        summary = make_edit_summary(path, edits_applied)
        agent_print(summary)

        diff_text = make_unified_diff(path, original_content, current_content)
        if self.show_diff:
            from .display import show_diff_colored
            show_diff_colored(diff_text)

        if self._confirm and not self._confirm(
            f"Apply {len(edits_applied)} edit(s) to {path}?", path=path, diff_text=diff_text
        ):
            agent_print("[Skipped]\n")
            return None

        try:
            # Cache the original content before overwriting
            file_url = self.cache.cache(path, original_content)
            os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(current_content)
            total_lines = current_content.count('\n') + 1
            obs = f"[Edited: {path} ({len(edits_applied)} change(s) applied, {total_lines} lines)]"
            if file_url:
                obs += f" (cached: {file_url})"
            if failures:
                warning = f"\n[WARNING: {len(failures)} search block(s) not found]"
                obs += warning
            agent_print(obs + "\n")
            return obs
        except Exception as e:
            msg = f"[Edit failed: {e}]"
            agent_print(msg + "\n")
            return msg

    def execute_read(self, action):
        """Execute a FILE: read action."""
        path = action["path"]
        full_path = self._full_path(path)
        if not os.path.isfile(full_path):
            msg = f"[READ FAILED: {path} does not exist]"
            agent_print(msg + "\n")
            return msg
        ext = os.path.splitext(path)[1].lower()
        if ext in SKIP_EXT:
            msg = f"[READ FAILED: {path} — binary/skipped extension ({ext})]"
            agent_print(msg + "\n")
            return msg
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            msg = f"[READ FAILED: {path}: {e}]"
            agent_print(msg + "\n")
            return msg
        lines_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        file_url = self.cache.cache(path, content)
        max_chars = min(self.ctx_size // 2, 200000)
        truncated = ""
        if len(content) > max_chars:
            content = content[:max_chars]
            truncated = " (truncated)"
        url_info = f", cached: {file_url}" if file_url else ""
        agent_print(f"[Read: {path} ({lines_count} lines{truncated}{url_info})]")
        max_display_lines = 200
        content_lines = content.split('\n')
        if len(content_lines) > max_display_lines:
            for line in content_lines[:max_display_lines]:
                tool_print(line)
            tool_print(f"... ({len(content_lines) - max_display_lines} more lines)")
        else:
            tool_print(content)
        tool_print()
        obs = f"[File: {path}]\n{content}"
        self._log("system", f"[Read: {path} ({lines_count} lines{truncated}{url_info})]")
        return obs
