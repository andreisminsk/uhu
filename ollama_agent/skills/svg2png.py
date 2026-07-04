"""svg2png skill — Convert SVG files to high-resolution PNG images.

Self-contained: the svg2png.py script is bundled inside this skill at
ollama_agent/skills/svg2png/svg2png.py.

Supports multiple backends with automatic detection and fallback:
  1. cairosvg  (best quality, requires Cairo native library)
  2. playwright (browser-based, excellent quality, handles complex SVG)
  3. svglib+reportlab+pypdfium2 (pure Python, no native deps)
  4. inkscape CLI (if Inkscape is installed)
"""

import os
import subprocess
import sys

from .base import Skill


# This skill's directory (contains the bundled svg2png.py script)
_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_SCRIPT_DIR = os.path.join(_SKILL_DIR, "svg2png_scripts")
_SCRIPT_PATH = os.path.join(_SCRIPT_DIR, "svg2png.py")


class Svg2PngSkill(Skill):
    name = "svg2png"
    description = ("Convert SVG files to high-resolution PNG images with "
                   "automatic backend selection (cairosvg, playwright, "
                   "svglib, inkscape)")
    triggers = [
        "convert svg", "svg to png", "svg2png", "svg 2 png",
        "render svg", "svg image", "export svg", "high-res svg",
        "svg high resolution", "svg to image",
    ]

    system_prompt = """\
## svg2png
Convert SVG files to high-resolution PNG images with automatic backend selection.

CRITICAL — DO NOT REIMPLEMENT SVG CONVERSION:
- When the user wants to convert an SVG to PNG, you MUST invoke this skill (svg2png).
- The skill runs the bundled svg2png.py script which handles backend detection,
  sanitization, scaling, and output automatically.
- Do NOT write your own SVG-to-PNG conversion code — the bundled script is more robust.

Parameters (JSON object):
- input (string, required): Path to the SVG file (or directory/glob) to convert.
- output (string, optional): Output PNG path. Defaults to <input>.png. Only valid for single-file input.
- scale (integer, optional, default 2): Scale factor for output resolution (e.g. 4 for ultra high-res).
- width (integer, optional): Output width in pixels (height auto-scaled proportionally).
- height (integer, optional): Output height in pixels (width auto-scaled proportionally).
- dpi (integer, optional): DPI for output (e.g. 300 for print quality).
- backend (string, optional): Force a specific backend — cairosvg, playwright, svglib, inkscape. Default: auto-select best available.
- list_backends (boolean, optional, default false): If true, list available backends and exit (input ignored).

### Backend Priority
When no backend is forced, the script selects the first available in this order:
1. cairosvg — highest quality, fastest for simple SVGs (needs Cairo native lib)
2. playwright — excellent quality, handles complex SVG (CSS, animations, filters)
3. svglib — pure Python fallback, sanitizes CSS that would otherwise crash
4. inkscape — excellent quality, requires Inkscape binary

### Workflow
1. Invoke the skill with the input SVG path and desired options.
2. The skill runs the bundled script and returns its output.
3. Present the result to the user — mention the output path, backend used, and file size.
4. If conversion fails, suggest installing a backend (see README.md in the skill directory).

### Examples
- Convert a single SVG at 4x scale: {"input": "diagram.svg", "scale": 4}
- Convert with specific width: {"input": "logo.svg", "width": 2048}
- Print quality 300 DPI: {"input": "logo.svg", "dpi": 300, "output": "logo_print.png"}
- Batch convert a folder: {"input": "icons/", "scale": 4}
- Force playwright backend: {"input": "flowchart.svg", "backend": "playwright"}
- List available backends: {"input": "", "list_backends": true}
"""

    parameters = {
        "input": {
            "type": "string",
            "required": True,
            "description": "Path to the SVG file (or directory/glob) to convert",
        },
        "output": {
            "type": "string",
            "required": False,
            "description": "Output PNG path (single file only). Default: <input>.png",
        },
        "scale": {
            "type": "integer",
            "required": False,
            "description": "Scale factor (default: 2)",
        },
        "width": {
            "type": "integer",
            "required": False,
            "description": "Output width in pixels",
        },
        "height": {
            "type": "integer",
            "required": False,
            "description": "Output height in pixels",
        },
        "dpi": {
            "type": "integer",
            "required": False,
            "description": "DPI for output (e.g. 300 for print quality)",
        },
        "backend": {
            "type": "string",
            "required": False,
            "description": "Force backend: cairosvg, playwright, svglib, inkscape (default: auto)",
        },
        "list_backends": {
            "type": "boolean",
            "required": False,
            "description": "If true, list available backends and exit (default: false)",
        },
    }

    def execute(self, params, workdir=None, session=None):
        if not os.path.isfile(_SCRIPT_PATH):
            return f"[Skill error: svg2png.py script not found at {_SCRIPT_PATH}]"

        # Build command-line arguments
        cmd = [sys.executable, _SCRIPT_PATH]

        if params.get("list_backends"):
            cmd.append("--list-backends")
            return self._run_script(cmd, workdir)

        input_path = params.get("input", "")
        if not input_path:
            return "[Skill error: 'input' parameter is required for svg2png]"

        # Resolve input path relative to workdir
        if workdir and not os.path.isabs(input_path):
            input_full = os.path.join(workdir, input_path)
            if os.path.exists(input_full):
                input_path = input_full
        cmd.append(input_path)

        output = params.get("output")
        if output:
            # Resolve output path relative to workdir
            if workdir and not os.path.isabs(output):
                output = os.path.join(workdir, output)
            cmd.extend(["-o", output])

        scale = params.get("scale")
        if scale is not None:
            cmd.extend(["-s", str(int(scale))])

        width = params.get("width")
        if width is not None:
            cmd.extend(["-w", str(int(width))])

        height = params.get("height")
        if height is not None:
            cmd.extend(["--height", str(int(height))])

        dpi = params.get("dpi")
        if dpi is not None:
            cmd.extend(["-d", str(int(dpi))])

        backend = params.get("backend")
        if backend:
            cmd.extend(["-b", str(backend)])

        return self._run_script(cmd, workdir)

    def _run_script(self, cmd, workdir=None):
        """Run the svg2png.py script and return its output."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=workdir or _SCRIPT_DIR,
            )
            parts = []
            if result.stdout:
                parts.append(result.stdout.strip())
            if result.stderr:
                parts.append(f"[stderr]\n{result.stderr.strip()}")
            if result.returncode != 0 and not parts:
                parts.append(f"[Skill error: svg2png.py exited with code {result.returncode}]")
            elif result.returncode != 0:
                parts.append(f"[exit code: {result.returncode}]")
            return "\n".join(parts) if parts else "[svg2png completed with no output]"
        except subprocess.TimeoutExpired:
            return "[Skill error: svg2png.py timed out after 120s]"
        except Exception as e:
            return f"[Skill error: svg2png.py execution failed: {e}]"
