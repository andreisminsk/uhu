"""plan skill — create a development plan for a feature or project."""

import os

from .base import Skill


class PlanSkill(Skill):
    name = "plan"
    description = "Create a structured development plan for a feature or project"
    system_prompt = (
        "## plan\n"
        "Create a structured development plan for a feature or project.\n"
        "Parameters (JSON object):\n"
        "- description (string, required): What to build or implement\n"
        "- scope (string, optional, default \"feature\"): Scope — feature, project, module, refactor\n"
        "- path (string, optional): Directory of relevant existing code to consider\n"
        "\n"
        "When this skill is invoked, create a development plan:\n"
        "1. Understand the goal from the description and any existing code context\n"
        "2. Break the work into clear, ordered steps\n"
        "3. For each step: describe what to do, which files to create/modify, and dependencies\n"
        "4. Identify risks, edge cases, and testing needs\n"
        "5. Estimate relative complexity for each step\n"
        "6. Present the plan in a clear, actionable format\n"
    )
    parameters = {
        "description": {"type": "string", "required": True, "description": "What to build or implement"},
        "scope": {"type": "string", "required": False, "description": "Scope: feature, project, module, refactor (default: feature)"},
        "path": {"type": "string", "required": False, "description": "Directory of relevant existing code"},
    }

    def execute(self, params, workdir=None, session=None):
        description = params.get("description", "")
        scope = params.get("scope", "feature")
        path = params.get("path", "")

        if not description:
            return "[Skill error: 'description' parameter is required for plan]"

        parts = [
            f"[Skill plan invoked]",
            f"Description: {description}",
            f"Scope: {scope}",
        ]

        # If a path is given, gather context from the directory
        if path:
            full_path = os.path.join(workdir or ".", path) if not os.path.isabs(path) else path
            if os.path.isdir(full_path):
                from ..constants import SKIP_EXT
                context_parts = []
                file_count = 0
                for root, _, fnames in os.walk(full_path):
                    for fn in sorted(fnames):
                        if file_count >= 10:
                            break
                        fpath = os.path.join(root, fn)
                        if os.path.splitext(fn)[1].lower() not in SKIP_EXT:
                            try:
                                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                                    content = f.read()
                                frel = os.path.relpath(fpath, full_path)
                                max_chars = 2000
                                if len(content) > max_chars:
                                    content = content[:max_chars] + "\n[... truncated]"
                                context_parts.append(f"--- {frel} ---\n{content}")
                                file_count += 1
                            except Exception:
                                pass
                    if file_count >= 10:
                        break

                if context_parts:
                    parts.append(f"Context from {path} ({file_count} files):")
                    parts.append("")
                    parts.extend(context_parts)
                else:
                    parts.append(f"Context: No readable files found in {path}")
            elif os.path.isfile(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    parts.append(f"Context from {path}:")
                    parts.append(content)
                except Exception as e:
                    parts.append(f"Context: Cannot read {path}: {e}")

        return "\n".join(parts)
