"""doc-gen skill — generate documentation for code."""

import os

from .base import Skill


class DocGenSkill(Skill):
    name = "doc-gen"
    description = "Generate documentation for source code"
    triggers = ["generate docs", "write documentation", "document this", "docstrings", "readme"]
    system_prompt = (
        "## doc-gen\n"
        "Generate documentation for source code.\n"
        "Parameters (JSON object):\n"
        "- path (string, required): Source file or directory to document\n"
        "- format (string, optional, default \"docstring\"): Output format — docstring, readme, api-docs\n"
        "- style (string, optional, default \"google\"): Docstring style — google, numpy, sphinx, rustdoc\n"
        "\n"
        "When this skill is invoked with file content, generate documentation:\n"
        "1. For docstring format: Add or improve docstrings to functions and classes\n"
        "2. For readme format: Create a README.md with usage, API, and examples\n"
        "3. For api-docs format: Generate API reference documentation\n"
        "4. Use the specified docstring style conventions\n"
        "5. Write documentation using EDIT or WRITE blocks\n"
    )
    parameters = {
        "path": {"type": "string", "required": True, "description": "Source file or directory to document"},
        "format": {"type": "string", "required": False, "description": "Output format: docstring, readme, api-docs (default: docstring)"},
        "style": {"type": "string", "required": False, "description": "Docstring style: google, numpy, sphinx, rustdoc (default: google)"},
    }

    def execute(self, params, workdir=None, session=None):
        path = params.get("path", "")
        fmt = params.get("format", "docstring")
        style = params.get("style", "google")
        if not path:
            return "[Skill error: 'path' parameter is required for doc-gen]"

        full_path = os.path.join(workdir or ".", path) if not os.path.isabs(path) else path

        if os.path.isfile(full_path):
            return self._document_file(path, full_path, fmt, style)
        elif os.path.isdir(full_path):
            return self._document_directory(path, full_path, fmt, style)
        else:
            return f"[Skill error: Path not found: {path}]"

    def _document_file(self, rel_path, full_path, fmt, style):
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return f"[Skill error: Cannot read {rel_path}: {e}]"

        lines = content.count("\n") + 1
        return (
            f"[Skill doc-gen invoked]\n"
            f"Target: {rel_path} ({lines} lines)\n"
            f"Format: {fmt}\n"
            f"Style: {style}\n"
            f"Content:\n{content}"
        )

    def _document_directory(self, rel_path, full_path, fmt, style):
        from ..constants import SKIP_EXT
        files = []
        for root, _, fnames in os.walk(full_path):
            for fn in sorted(fnames):
                if os.path.splitext(fn)[1].lower() not in SKIP_EXT:
                    files.append(os.path.join(root, fn))
            if len(files) > 15:
                break

        if not files:
            return f"[Skill doc-gen: No readable files found in {rel_path}]"

        parts = [f"[Skill doc-gen invoked]", f"Target: {rel_path} ({len(files)} files)", f"Format: {fmt}", f"Style: {style}", ""]
        for fpath in files[:15]:
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                frel = os.path.relpath(fpath, full_path)
                lines = content.count("\n") + 1
                max_chars = 3000
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n[... truncated]"
                parts.append(f"--- {frel} ({lines} lines) ---")
                parts.append(content)
                parts.append("")
            except Exception:
                pass

        return "\n".join(parts)
