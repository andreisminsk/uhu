---
name: md2pdf
description: Convert Markdown files with linked images to self-contained PDFs
version: 1.0.0
triggers:
  - md2pdf
  - markdown to pdf
  - convert md to pdf
  - md file to pdf
tools:
  - terminal
  - file
---

# md2pdf — Markdown to PDF Converter

Convert a `.md` file to a polished PDF, embedding all locally-linked and remote images as base64 data URIs.

## Quick Start

```bash
python scripts/md2pdf.py <input.md> [output.pdf]
```

- If `output.pdf` is omitted, generates `<input>.pdf` next to the source file.
- All local image paths resolve **relative to the .md file's directory**.
- Remote images (http/https URLs) are downloaded and embedded automatically.

## Scripts

- `scripts/md2pdf.py` — Converts Markdown to PDF with embedded images

> All script paths are relative to this SKILL.md's directory.
> At runtime, they are automatically resolved to workdir-relative paths.

## How It Works

1. **Markdown → HTML** via `markdown` library with extensions (tables, fenced code, codehilite, TOC, smarty, attr_list)
2. **Image embedding** — finds all `<img src="...">` and:
   - Local paths → reads file, converts to `data:image/...;base64,...`
   - Remote URLs → downloads, then base64-encodes
   - Already data-URIs → skipped
3. **HTML → PDF** via `xhtml2pdf` (pisa) with clean A4 typography

## Dependencies

Installed at skill creation:
- `markdown` (Python Markdown → HTML)
- `pymdown-extensions` (extra markdown features)
- `xhtml2pdf` (HTML → PDF, pure Python, no system deps)

No system-level dependencies needed (unlike weasyprint which requires pango/gobject).

## Output Styling

The PDF uses clean A4 layout:
- 2.5cm margins, 11pt base font
- Syntax-highlighted code blocks
- Proper table styling
- Images centered, max-width 100%
- Clickable links in blue

## Examples

```bash
# Basic usage
python3 .skills/md2pdf/scripts/md2pdf.py report.md

# Custom output path
python3 .skills/md2pdf/scripts/md2pdf.py notes.md /tmp/notes.pdf

# File with images in subfolder
python3 .skills/md2pdf/scripts/md2pdf.py docs/README.md
# Images like ./images/diagram.png resolve relative to docs/
```

## Unicode Support

Uses **Arial Unicode MS** (`/Library/Fonts/Arial Unicode.ttf`) for full Unicode coverage — Cyrillic, Georgian, CJK, Arabic, etc. Registered via `@font-face` with a local file path (xhtml2pdf requires plain paths, not `file://` or `data:` URIs for fonts). Falls back to Helvetica on systems without Arial Unicode.

## Pitfalls

- **xhtml2pdf font registration**: Must use `@font-face` with plain local file paths (`url("/Library/Fonts/Arial Unicode.ttf")`), NOT `file://` URIs or base64 data URIs — xhtml2pdf silently falls back to Helvetica otherwise.
- **Large images**: base64 embedding increases PDF size. Very large images (10MB+) may slow conversion.
- **Animated GIFs**: only first frame is captured (xhtml2pdf limitation).
- **SVG images**: limited xhtml2pdf SVG support; convert to PNG first if issues.
- **Complex HTML/CSS**: xhtml2pdf has limited CSS support. Flexbox/grid won't work.
- **Special characters**: ensure markdown is UTF-8 encoded.
- **Broken image paths**: warnings are printed but conversion continues; missing images show as empty boxes.