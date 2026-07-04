"""graph-ai skill — Generate and render dependency diagrams from natural language.

Self-contained: all scripts live in ollama_agent/skills/graph-ai/.
Wraps the graphai-dsl toolchain:
  1. desc2dsl.py  — text description → .dsl file (LLM-powered, uses GRAPH.md prompt)
  2. dsl2image.py — .dsl → .png  (Pillow, algorithmic layout, styles: notebook/ancient/blueprint)
  3. dsl2html.py  — .dsl → .html (interactive, styles: notebook/ancient/blueprint/timeline/roadmap/fishbone)
  4. dsl2fishbone.py — fishbone/Ishikawa diagrams (auto-dispatched by dsl2html.py for style=fishbone)

Excluded by design: dsl2svg.py and dsl2aiimage.py (LLM-based layout/render paths).
"""

import os

from .base import Skill


# This skill's directory (contains all scripts, GRAPH.md, assets/)
_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_GRAPHAI_DIR = os.path.join(_SKILL_DIR, "graph-ai")


def _check_script(script_name):
    """Check if a script exists in the local graph-ai directory."""
    path = os.path.join(_GRAPHAI_DIR, script_name)
    return os.path.isfile(path), path


def _get_skill_config(workdir=None):
    """Load graph-ai config from .ollama_agent.json (skills section).

    Falls back to .env in the skill directory, then to built-in defaults.
    """
    defaults = {
        "model": "glm-5.1:cloud",
        "base_url": "http://localhost:11434",
        "api_key": "ollama-local",
        "max_tokens": 131072,
    }
    try:
        from ..tools._config import load_config
        config = load_config(workdir)
        skill_cfg = config.get("skills", {}).get("graph-ai", {})
        defaults.update(skill_cfg)
    except Exception:
        pass
    return defaults


class GraphAiSkill(Skill):
    name = "graph-ai"
    description = "Generate dependency/ancestry/timeline/fishbone diagrams from natural language descriptions using the graphai-dsl toolchain"
    triggers = [
        "diagram", "dependency graph", "ancestry", "lineage", "fishbone",
        "ishikawa", "roadmap diagram", "timeline diagram", "draw diagram",
        "render diagram", "dependency tree", "visualize dependencies",
        "generate diagram", "graph diagram",
    ]

    system_prompt = """\
## graph-ai
Generate and render diagrams from natural language descriptions using the graphai-dsl toolchain.

CRITICAL — DO NOT WRITE DSL MANUALLY:
- When the user wants a diagram, you MUST invoke this skill (graph-ai) with a "description" parameter.
- The skill runs desc2dsl.py which uses an LLM to classify content, pick the best style, and structure the DSL correctly.
- Do NOT write .dsl files by hand — the desc2dsl.py script does this better (it knows the DSL syntax rules, style selection, and structure patterns from GRAPH.md).
- Only write/edit .dsl manually if the user explicitly asks to refine an existing diagram.
- After the skill generates the .dsl, use RUN blocks with the EXACT commands the skill provides to render PNG/HTML.

Parameters (JSON object):
- description (string, optional): Natural language text describing the diagram to create. Required for generating new diagrams.
- dsl_file (string, optional): Path to an existing .dsl file to render (skip generation).
- style (string, optional): Visual style — notebook, ancient, blueprint, timeline, roadmap, fishbone (default: auto-selected by desc2dsl based on content)
- format (string, optional): Output format — png, html, or both (default: both)
- output (string, optional): Output file BASE NAME only (no path, no directory) — e.g. "my-diagram". The skill automatically places all output files in the project working directory. Do NOT include a full path — just the name.
- title (string, optional): Diagram title (default: auto-selected by style)

### Toolchain Overview

All scripts are bundled inside this skill at: ollama_agent/skills/graph-ai/
They are self-contained and do NOT require an external graphai-dsl installation.

1. **desc2dsl.py** — THE FUNDAMENTAL SCRIPT. Converts a natural language description into a .dsl file using an LLM (Ollama). Uses GRAPH.md as the system prompt to classify content type, choose the best visual style, and structure the DSL.
   ```
   python <skill_dir>/desc2dsl.py <input.txt> [-o output.dsl] [-m model] [--base-url URL] [--api-key KEY] [--prompt "focus guidance"]
   ```
   - Input: a .txt file with the description, or '-' for stdin
   - Output: a .dsl file (default: same name as input with .dsl extension)
   - The LLM classifies content (dependency, ancestry, comparison, timeline, cause-effect) and picks the style automatically
   - You can pass --prompt to add focus guidance (e.g. "Structure based on use case table")

2. **dsl2image.py** — Renders .dsl to PNG using Pillow with algorithmic layout. Supports styles: notebook, ancient, blueprint.
   ```
   python <skill_dir>/dsl2image.py <input.dsl> [output.png] [--style notebook|ancient|blueprint] [--dsl]
   ```
   - output.png is a POSITIONAL argument (not -o)
   - --style overrides the DSL style= directive
   - --dsl treats input as inline DSL text instead of a file path

3. **dsl2html.py** — Renders .dsl to interactive self-contained HTML. Supports ALL styles: notebook, ancient, blueprint, timeline, roadmap, fishbone.
   ```
   python <skill_dir>/dsl2html.py <input.dsl> [output.html] [--style notebook|ancient|blueprint|timeline|roadmap|fishbone] [--dsl]
   ```
   - output.html is a POSITIONAL argument (not -o)
   - HTML output includes hover highlighting, copy/download buttons, and embedded CSS/SVG
   - For style=fishbone, automatically dispatches to dsl2fishbone.py

4. **dsl2fishbone.py** — Fishbone (Ishikawa) diagram renderer. Normally auto-dispatched by dsl2html.py, but can be called directly.

### DSL Syntax Reference

```
# Style directive (first line, optional)
style=notebook|ancient|blueprint|timeline|roadmap|fishbone

# Title directive (optional)
title=My Diagram

# Hierarchical edge: A flows into B (solid arrow, drives layout)
ID "Label" -> Child1, Child2, Child3

# Leaf node (no children)
ID "Label"

# Free connector (dashed arrow, no layout effect)
ID "Label" --> OtherID
ID --> OtherID1, OtherID2

# Focus marker (highlights with ★)
*ID "Label" -> Child1, Child2

# Annotation (hover tooltip in HTML)
ID "Label" | "Tooltip text"

# Comments
# This is a comment
```

Rules:
- ID: alphanumeric + underscore (F1, ROGNEDE, FC_HW)
- Label: double quotes, concise (<40 chars recommended)
- Every referenced ID must have its own declaration line
- A -> B means A flows into B (ancestor → descendant, root → dependent)
- Roots/foundations at top, leaves/descendants at bottom
- Only one focus node per diagram (marked with *)

### Visual Styles

| Style | Best For | Output | Background |
|-------|----------|--------|------------|
| notebook (default) | Technical dependencies | PNG+HTML | Graph paper, pencil sketch |
| ancient | Genealogy, history, lineage | PNG+HTML | Parchment, brown ink |
| blueprint | Architecture, system design | PNG+HTML | Dark blue, technical drawing |
| timeline | Sequences, chronologies | HTML only | Horizontal timeline, alternating cards |
| roadmap | Comparisons, categorizations | HTML only | Horizontal spine, 60° branching |
| fishbone | Root-cause analysis (Ishikawa) | HTML only | Dot grid, diagonal bones |

### Workflow

**Step 1: Generate DSL from description**
- Write the user's description to a .txt file in the WORKDIR (not the skill directory)
- Run: `python <skill_dir>/desc2dsl.py <workdir>/description.txt -o <workdir>/diagram.dsl`
- The LLM auto-classifies content and picks the best style
- Review the generated .dsl file — verify node IDs, labels, and structure
- If the structure needs adjustment, edit the .dsl file directly or re-run with --prompt guidance

**Step 2: Render the diagram**
- For PNG: `python <skill_dir>/dsl2image.py <workdir>/diagram.dsl <workdir>/diagram.png` (notebook/ancient/blueprint only)
- For HTML: `python <skill_dir>/dsl2html.py <workdir>/diagram.dsl <workdir>/diagram.html` (all styles)
- For both: run both commands
- Use --style to override the style in the .dsl file

**Step 3: Present results**
- Show the generated .dsl content to the user
- Provide file:// links to the rendered PNG and/or HTML files
- If the diagram needs refinement, edit the .dsl and re-render

### Ollama Configuration

The desc2dsl.py script reads Ollama config from .ollama_agent.json under `skills.graph-ai`:
```json
"skills": {
    "graph-ai": {
        "model": "glm-5.1:cloud",
        "base_url": "http://localhost:11434",
        "api_key": "ollama-local",
        "max_tokens": 131072
    }
}
```
These values are passed to desc2dsl.py via CLI flags (-m, --base-url, --api-key).
Falls back to .env in the skill directory, then to built-in defaults.

### Important Notes

- desc2dsl.py is the entry point — it produces the .dsl source file that all other scripts consume
- The .dsl file is human-readable and editable — encourage users to refine it
- timeline, roadmap, and fishbone styles are HTML-only (dsl2image.py does not support them)
- dsl2html.py auto-dispatches to dsl2fishbone.py for fishbone style
- All scripts accept inline DSL with --dsl flag (input is DSL text, not a file path)
- ALL output files (.txt, .dsl, .png, .html) must be created in the WORKDIR, never in the skill directory
- The skill directory path is provided in the execution output — use it for all script invocations
"""

    parameters = {
        "description": {"type": "string", "required": False, "description": "Natural language text describing the diagram to create"},
        "dsl_file": {"type": "string", "required": False, "description": "Path to existing .dsl file to render (skip generation)"},
        "style": {"type": "string", "required": False, "description": "Visual style: notebook, ancient, blueprint, timeline, roadmap, fishbone"},
        "format": {"type": "string", "required": False, "description": "Output format: png, html, or both (default: both)"},
        "output": {"type": "string", "required": False, "description": "Output file path without extension"},
        "title": {"type": "string", "required": False, "description": "Diagram title"},
    }

    def execute(self, params, workdir=None, session=None):
        # Check if the local graph-ai directory exists
        if not os.path.isdir(_GRAPHAI_DIR):
            return (
                f"[Skill graph-ai invoked]\n"
                f"ERROR: graph-ai skill directory not found at: {_GRAPHAI_DIR}\n"
                f"The skill scripts should be bundled at ollama_agent/skills/graph-ai/"
            )

        # Check which scripts are available
        scripts = ["desc2dsl.py", "dsl2image.py", "dsl2html.py", "dsl2fishbone.py"]
        available = []
        missing = []
        for s in scripts:
            exists, _ = _check_script(s)
            if exists:
                available.append(s)
            else:
                missing.append(s)

        # Load Ollama config from .ollama_agent.json (skills.graph-ai section)
        cfg = _get_skill_config(workdir)
        model = cfg["model"]
        base_url = cfg["base_url"]
        api_key = cfg["api_key"]
        max_tokens = cfg["max_tokens"]

        # Check for prompt files
        graph_md = os.path.join(_GRAPHAI_DIR, "GRAPH.md")
        graph_md_exists = os.path.isfile(graph_md)

        # Parse params
        description = params.get("description", "")
        dsl_file = params.get("dsl_file", "")
        style = params.get("style", "")
        fmt = params.get("format", "both")
        output = params.get("output", "")
        title = params.get("title", "")

        # Resolve workdir for output files — ALWAYS in workdir, ignore any directory in `output`
        wd = os.path.abspath(workdir or os.getcwd())
        # Strip any path from output, keep only the basename (force workdir)
        base_name = os.path.basename(output) if output else "diagram"
        if not base_name or base_name == ".":
            base_name = "diagram"
        txt_path = os.path.join(wd, base_name + ".txt")
        dsl_path = os.path.join(wd, base_name + ".dsl")
        png_path = os.path.join(wd, base_name + ".png")
        html_path = os.path.join(wd, base_name + ".html")

        # Short path aliases for readability
        d_desc = os.path.join(_GRAPHAI_DIR, "desc2dsl.py")
        d_img = os.path.join(_GRAPHAI_DIR, "dsl2image.py")
        d_html = os.path.join(_GRAPHAI_DIR, "dsl2html.py")

        parts = [
            f"[Skill graph-ai invoked]",
            f"Skill scripts directory: {_GRAPHAI_DIR}",
            f"Working directory (for outputs): {wd}",
            f"Available scripts: {', '.join(available)}" if available else "No scripts found!",
        ]
        if missing:
            parts.append(f"Missing scripts: {', '.join(missing)}")
        parts.append(f"Ollama model: {model}")
        parts.append(f"Ollama base URL: {base_url}")
        parts.append(f"GRAPH.md prompt: {'found' if graph_md_exists else 'NOT found (desc2dsl.py needs this!)'}")
        parts.append("")
        parts.append("IMPORTANT: All script paths below are ABSOLUTE and ready to use. Do NOT search for scripts.")
        parts.append("Use RUN blocks with these exact commands. Output files go to the working directory.")
        parts.append("")

        # Build the workflow guidance
        if description:
            parts.append("=== WORKFLOW: Generate diagram from description ===")
            parts.append(f"Step 1. Write the description to: {txt_path}")
            parts.append(f"Step 2. Generate .dsl file — RUN this exact command:")
            cmd = f'python "{d_desc}" "{txt_path}" -o "{dsl_path}" -m {model} --base-url {base_url} --api-key {api_key}'
            parts.append(f"   {cmd}")
            if style:
                parts.append(f"   (style will be auto-selected; override with --prompt if needed)")
            parts.append(f"Step 3. Read and review the generated .dsl file: {dsl_path}")
            parts.append(f"Step 4. Render to PNG and/or HTML — RUN these exact commands:")
            if fmt in ("png", "both"):
                png_cmd = f'python "{d_img}" "{dsl_path}" "{png_path}"'
                if style:
                    png_cmd += f" --style {style}"
                parts.append(f"   {png_cmd}")
            if fmt in ("html", "both"):
                html_cmd = f'python "{d_html}" "{dsl_path}" "{html_path}"'
                if style:
                    html_cmd += f" --style {style}"
                parts.append(f"   {html_cmd}")
            parts.append(f"Step 5. Present the .dsl content and file:// links to rendered outputs")
            parts.append("")
            parts.append(f"Description to process:")
            parts.append(description)
        elif dsl_file:
            parts.append("=== WORKFLOW: Render existing .dsl file ===")
            full_dsl = dsl_file if os.path.isabs(dsl_file) else os.path.join(wd, dsl_file)
            dsl_exists = os.path.isfile(full_dsl)
            parts.append(f"DSL file: {full_dsl} ({'found' if dsl_exists else 'NOT found!'})")
            if dsl_exists:
                try:
                    with open(full_dsl, "r", encoding="utf-8", errors="replace") as f:
                        dsl_content = f.read()
                    parts.append("")
                    parts.append("=== DSL CONTENT ===")
                    parts.append(dsl_content)
                    parts.append("=== END DSL ===")
                    parts.append("")
                except Exception as e:
                    parts.append(f"Error reading .dsl file: {e}")
            parts.append("")
            # Output paths for rendering — ALWAYS in workdir, ignore any directory in `output`
            render_base_name = os.path.basename(output) if output else os.path.splitext(os.path.basename(full_dsl))[0]
            if not render_base_name or render_base_name == ".":
                render_base_name = os.path.splitext(os.path.basename(full_dsl))[0]
            render_base = os.path.join(wd, render_base_name)
            render_png = render_base + ".png" if fmt in ("png", "both") else None
            render_html = render_base + ".html" if fmt in ("html", "both") else None
            parts.append(f"RUN these exact commands to render:")
            if render_png:
                png_cmd = f'python "{d_img}" "{full_dsl}" "{render_png}"'
                if style:
                    png_cmd += f" --style {style}"
                parts.append(f"   {png_cmd}")
            if render_html:
                html_cmd = f'python "{d_html}" "{full_dsl}" "{render_html}"'
                if style:
                    html_cmd += f" --style {style}"
                parts.append(f"   {html_cmd}")
        else:
            parts.append("=== READY ===")
            parts.append("Provide a 'description' to generate a new diagram, or a 'dsl_file' to render an existing one.")
            parts.append("The model should ask the user what they want to diagram.")

        parts.append("")
        parts.append(f"Style requested: {style or 'auto (desc2dsl will choose)'}")
        parts.append(f"Format requested: {fmt}")
        if title:
            parts.append(f"Title: {title}")
        if output:
            parts.append(f"Output base path: {output}")

        return "\n".join(parts)
