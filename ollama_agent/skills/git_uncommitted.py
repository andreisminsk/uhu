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
        '- save_to (string, optional): If set, write the full report to this file path (avoids output truncation)\n'
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
        "save_to": {"type": "string", "required": False, "description": "If set, write the full report to this file path (avoids output truncation)"},
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
        save_to = params.get("save_to", "")

        uncommitted = []
        clean = []
        errors = []

        # Directories that are never git repos and are expensive to traverse.
        # Pruning these prevents timeouts when scanning from a high-level path
        # (e.g. C:\Users\andre) where AppData/node_modules/.cache dominate.
        SKIP_DIRS = {
            ".git", "node_modules", "__pycache__", ".cache", ".venv", "venv",
            "env", ".tox", ".mypy_cache", ".pytest_cache", ".next", ".nuxt",
            ".gradle", ".idea", ".vscode", "dist", "build", "target",
            "site-packages", ".npm", ".cargo", ".rustup", ".terraform",
            ".terraform", ".serverless", ".serverless_nextjs",
            # Windows-specific heavy dirs
            "AppData", "Application Data", "Local Settings",
            "Documents and Settings", "System Volume Information",
            "$Recycle.Bin", "WindowsApps", "Packages",
        }

        for root, dirs, files in os.walk(path):
            # Skip inside .git and prune heavy directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            # Depth limit
            if depth > 0:
                rel = os.path.relpath(root, path)
                if rel != "." and rel.count(os.sep) + 1 > depth:
                    dirs.clear()
                    continue

            if ".git" not in os.listdir(root):
                continue

            # Found a git repo — stop descending. Git repos don't contain
            # other git repos (submodules are managed separately via .git/modules),
            # so there's no point scanning deeper.
            dirs.clear()

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

        report = "\n".join(lines)

        # If save_to is specified, write the full report to that file.
        # This avoids truncation when the harness feeds the observation back
        # to the model — the file always contains the complete output.
        if save_to:
            if not os.path.isabs(save_to):
                save_to = os.path.join(workdir or ".", save_to)
            try:
                os.makedirs(os.path.dirname(save_to) or ".", exist_ok=True)
                with open(save_to, "w", encoding="utf-8") as f:
                    f.write(report)
                return f"[Skill git-uncompleted: full report saved to {save_to} ({len(report)} chars, {len(uncommitted)} repos with changes)]"
            except Exception as e:
                return f"[Skill error: Failed to write report to {save_to}: {e}]\n\n{report}"

        return report
