"""git-uncommitted skill — scan directories for git repos with uncommitted changes."""

import os
import subprocess
import sys

from .base import Skill


class GitUncommittedSkill(Skill):
    name = "git-uncommitted"
    description = "Scan directories for git repos with uncommitted or unpushed changes"
    triggers = [
        "uncommitted", "git status", "git repos", "dirty repos",
        "uncommitted changes", "unpushed commits", "check git status",
        "which repos have changes", "pending changes",
    ]
    system_prompt = (
        '## git-uncommitted\n'
        'Scan directories for git repos with uncommitted or unpushed changes.\n'
        'Parameters (JSON object):\n'
        '- path (string, required): Root directory to scan\n'
        '- depth (integer, optional, default 0): Max subdirectory depth to recurse (0 = unlimited)\n'
        '- show_unpushed (boolean, optional, default true): Include repos with unpushed commits\n'
        '- show_clean (boolean, optional, default false): Also list clean git repos\n'
        'When this skill is invoked, it walks the directory tree looking for .git folders, '
        'then runs `git status --porcelain` and `git log --branches --not --remotes --oneline` '
        'in each repo to detect uncommitted changes and unpushed commits.\n'
        'Returns a structured report of repos needing attention.\n'
    )
    parameters = {
        "path": {"type": "string", "required": True, "description": "Root directory to scan"},
        "depth": {"type": "integer", "required": False, "description": "Max depth to recurse (0 = unlimited)"},
        "show_unpushed": {"type": "boolean", "required": False, "description": "Include repos with unpushed commits (default: true)"},
        "show_clean": {"type": "boolean", "required": False, "description": "Also list clean git repos (default: false)"},
    }

    def execute(self, params, workdir=None, session=None):
        path = params.get("path", "")
        if not path:
            path = workdir or "."
        elif not os.path.isabs(path):
            path = os.path.join(workdir or ".", path)

        if not os.path.isdir(path):
            return f"[Skill error: Directory not found: {path}]"

        depth = params.get("depth", 0)
        show_unpushed = params.get("show_unpushed", True)
        show_clean = params.get("show_clean", False)

        uncommitted = []
        clean = []
        errors = []

        for root, dirs, files in os.walk(path):
            # Skip inside .git directories
            dirs[:] = [d for d in dirs if d != ".git"]

            # Depth limit
            if depth > 0:
                rel = os.path.relpath(root, path)
                if rel != "." and rel.count(os.sep) + 1 > depth:
                    dirs.clear()
                    continue

            if ".git" not in os.listdir(root):
                continue

            rel_path = os.path.relpath(root, path)

            try:
                # Check for uncommitted changes
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                changes = result.stdout.strip().split("\n") if result.stdout.strip() else []

                # Check for unpushed commits
                unpushed = []
                if show_unpushed:
                    result2 = subprocess.run(
                        ["git", "log", "--branches", "--not", "--remotes", "--oneline"],
                        cwd=root,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    )
                    unpushed = result2.stdout.strip().split("\n") if result2.stdout.strip() else []

                if changes or unpushed:
                    uncommitted.append((rel_path, changes, unpushed))
                else:
                    clean.append(rel_path)

            except Exception as e:
                errors.append((rel_path, str(e)))

        # Build report
        lines = ["=" * 60]
        lines.append("GIT REPOS WITH UNCOMMITTED/UNPUSHED CHANGES:")
        lines.append("=" * 60)

        if uncommitted:
            for name, changes, unpushed in uncommitted:
                lines.append("")
                lines.append(f"\U0001f4c1 {name}")
                if changes:
                    lines.append(f"   Uncommitted ({len(changes)} file(s)):")
                    for c in changes:
                        lines.append(f"     {c}")
                if unpushed:
                    lines.append(f"   Unpushed ({len(unpushed)} commit(s)):")
                    for u in unpushed:
                        lines.append(f"     {u}")
        else:
            lines.append("  (none)")

        if show_clean:
            lines.append("")
            lines.append("=" * 60)
            lines.append(f"CLEAN GIT REPOS: {len(clean)}")
            lines.append("=" * 60)
            for c in clean:
                lines.append(f"  {c}")

        if errors:
            lines.append("")
            lines.append("=" * 60)
            lines.append(f"ERRORS: {len(errors)}")
            lines.append("=" * 60)
            for name, err in errors:
                lines.append(f"  {name}: {err}")

        return "\n".join(lines)
