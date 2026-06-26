"""code-review skill — review code for bugs, issues, and improvements."""

import os

from .base import Skill


class CodeReviewSkill(Skill):
    name = "code-review"
    description = "Review code for bugs, style issues, and improvement suggestions"
    triggers = ["review code", "code review", "check my code", "find bugs in", "code quality"]
    system_prompt = (
        "## code-review\n"
        "Review code for bugs, issues, and improvement suggestions.\n"
        "Parameters (JSON object):\n"
        "- path (string, required): File or directory to review\n"
        "- focus (string, optional, default \"all\"): Focus area — security, performance, style, correctness, all\n"
        "\n"
        "When this skill is invoked with file content, provide a structured review:\n"
        "1. Summary of the code's purpose\n"
        "2. Issues found (categorized by severity: critical/warning/info)\n"
        "3. Specific improvement suggestions with code examples\n"
        "4. Overall assessment\n"
    )
    parameters = {
        "path": {"type": "string", "required": True, "description": "File or directory to review"},
        "focus": {"type": "string", "required": False, "description": "Focus area: security, performance, style, correctness, all (default: all)"},
    }

    def execute(self, params, workdir=None, session=None):
        path = params.get("path", "")
        focus = params.get("focus", "all")
        if not path:
            return "[Skill error: 'path' parameter is required for code-review]"

        full_path = os.path.join(workdir or ".", path) if not os.path.isabs(path) else path

        if os.path.isfile(full_path):
            return self._review_file(path, full_path, focus)
        elif os.path.isdir(full_path):
            return self._review_directory(path, full_path, focus)
        else:
            return f"[Skill error: Path not found: {path}]"

    def _review_file(self, rel_path, full_path, focus):
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return f"[Skill error: Cannot read {rel_path}: {e}]"

        lines = content.count("\n") + 1
        ext = os.path.splitext(rel_path)[1].lower()
        return (
            f"[Skill code-review invoked]\n"
            f"Target: {rel_path} ({lines} lines, {ext})\n"
            f"Focus: {focus}\n"
            f"Content:\n{content}"
        )

    def _review_directory(self, rel_path, full_path, focus):
        from ..constants import SKIP_EXT
        files = []
        for root, _, fnames in os.walk(full_path):
            for fn in sorted(fnames):
                if os.path.splitext(fn)[1].lower() not in SKIP_EXT:
                    files.append(os.path.join(root, fn))
            if len(files) > 20:
                break

        if not files:
            return f"[Skill code-review: No readable files found in {rel_path}]"

        parts = [f"[Skill code-review invoked]", f"Target: {rel_path} ({len(files)} files)", f"Focus: {focus}", ""]
        for fpath in files[:20]:
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                frel = os.path.relpath(fpath, full_path)
                lines = content.count("\n") + 1
                parts.append(f"--- {frel} ({lines} lines) ---")
                # Cap per-file content for directory reviews
                max_chars = 5000
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n[... truncated]"
                parts.append(content)
                parts.append("")
            except Exception:
                pass

        return "\n".join(parts)
