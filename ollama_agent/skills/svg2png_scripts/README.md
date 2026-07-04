# svg2png

Convert SVG files to high-resolution PNG images with automatic backend selection.

## Features

- **Multiple backends** with automatic detection and fallback:
  - **cairosvg** — best quality, requires Cairo native library
  - **playwright** — excellent quality, browser-based (Chromium SVG engine)
  - **svglib** — pure Python fallback, no native dependencies
  - **inkscape** — best quality, requires Inkscape installed
- **High-resolution output** via scale factor, explicit dimensions, or DPI
- **Batch conversion** — process multiple files, directories, or glob patterns
- **SVG sanitization** — strips problematic CSS that crashes pure-Python backends
- **Cross-platform** — works on Windows, macOS, and Linux

## Installation

```bash
pip install svg2png.py  # or just run directly
```

### Backend dependencies (install at least one)

| Backend | Install command | Native deps? |
|---------|----------------|--------------|
| playwright (recommended) | `pip install playwright && playwright install chromium` | Bundled Chromium |
| cairosvg | `pip install cairosvg` | Cairo native library |
| svglib | `pip install svglib reportlab Pillow pypdfium2` | None (pure Python) |
| inkscape | Install [Inkscape](https://inkscape.org/) and add to PATH | Inkscape binary |

Check available backends:

```bash
python svg2png.py --list-backends
```

## Usage

```bash
# Basic conversion (2x scale by default)
python svg2png.py logo.svg

# Ultra high-res (4x scale)
python svg2png.py logo.svg -s 4

# Specific width (height auto-scaled proportionally)
python svg2png.py logo.svg -w 2048

# Specific height (width auto-scaled proportionally)
python svg2png.py logo.svg --height 1080

# Print quality (300 DPI)
python svg2png.py logo.svg -d 300

# Custom output filename
python svg2png.py logo.svg -o high-res.png

# Batch convert all SVGs in current directory
python svg2png.py *.svg

# Convert all SVGs in a folder (recursive)
python svg2png.py assets/

# Force a specific backend
python svg2png.py logo.svg -b playwright
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-o, --output` | Output PNG path (single file only) | `<input>.png` |
| `-s, --scale` | Scale factor | `2` |
| `-w, --width` | Output width in pixels | — |
| `--height` | Output height in pixels | — |
| `-d, --dpi` | DPI for output | — |
| `-b, --backend` | Force backend: `cairosvg`, `playwright`, `svglib`, `inkscape` | auto |
| `-q, --quiet` | Suppress output except errors | off |
| `--list-backends` | Show available backends and exit | — |

## Backend priority

When no backend is forced, the script selects the first available in this order:

1. **cairosvg** — highest quality, fastest for simple SVGs
2. **playwright** — excellent quality, handles complex SVGs (CSS, animations, filters)
3. **svglib** — pure Python fallback, sanitizes CSS that would otherwise crash
4. **inkscape** — excellent quality, requires Inkscape binary

## How it works

### Playwright backend

Renders the SVG in a headless Chromium browser using `device_scale_factor` for high-resolution output. The browser's native SVG engine handles all SVG features — CSS, gradients, filters, animations — producing pixel-perfect results matching what you'd see in Chrome.

### svglib backend

Pure Python pipeline: SVG → svglib → reportlab PDF → pypdfium2 → PNG. Includes a sanitization step that strips `<style>` blocks and fixes `stroke-dasharray:0` values that would crash the parser. Lower fidelity than browser-based rendering but requires no native dependencies.

## Examples

```bash
# Convert a Mermaid diagram to high-res PNG
python svg2png.py flowchart.svg -s 3

# Generate print-ready 300 DPI output
python svg2png.py logo.svg -d 300 -o logo_print.png

# Batch convert a folder of icons to 4x resolution
python svg2png.py icons/ -s 4
```

## License

MIT
