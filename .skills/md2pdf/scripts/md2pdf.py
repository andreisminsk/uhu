#!/usr/bin/env python3
"""
md2pdf — Convert a Markdown file with linked images to a self-contained PDF.

Usage:
    python3 md2pdf.py <input.md> [output.pdf]

Features:
  - Converts Markdown → styled HTML → PDF
  - Embeds local images as base64 data URIs (handles relative & absolute paths)
  - Downloads remote http/https images and embeds them
  - Full Unicode support: Cyrillic, Georgian, CJK, etc. (uses system Arial Unicode)
  - Clean typography with good page margins
"""

import sys
import os
import re
import base64
import mimetypes
from pathlib import Path

import markdown
import xhtml2pdf.pisa as pisa


# ─── Unicode Font Setup ──────────────────────────────────────────────────
# macOS ships "Arial Unicode.ttf" in /Library/Fonts/ with full Unicode coverage
# (Latin, Cyrillic, Georgian, CJK, Arabic, etc.)
# xhtml2pdf requires @font-face src as plain file paths (not file:// URLs).
# The resulting PDF embeds font subsets, so it's self-contained.

ARIAL_UNICODE_PATH = "/Library/Fonts/Arial Unicode.ttf"
UNICODE_FONT_AVAILABLE = os.path.isfile(ARIAL_UNICODE_PATH)

# ─── CSS styling for the PDF ───────────────────────────────────────────────

# xhtml2pdf requires @font-face src as plain file paths (not file:// URLs)
# for TTF font loading. Arial Unicode MS covers Latin, Cyrillic, Georgian,
# CJK, Arabic, and most other scripts.

if UNICODE_FONT_AVAILABLE:
    FONT_FACE = f"""
/* Register Arial Unicode MS for full Unicode coverage (Cyrillic, Georgian, CJK, etc.) */
@font-face {{
    font-family: ArialUnicode;
    src: url("{ARIAL_UNICODE_PATH}");
}}
@font-face {{
    font-family: ArialUnicode;
    src: url("{ARIAL_UNICODE_PATH}");
    font-weight: bold;
}}
@font-face {{
    font-family: ArialUnicode;
    src: url("{ARIAL_UNICODE_PATH}");
    font-style: italic;
}}
@font-face {{
    font-family: ArialUnicode;
    src: url("{ARIAL_UNICODE_PATH}");
    font-weight: bold;
    font-style: italic;
}}
"""
    FONT_CSS = 'font-family: ArialUnicode, sans-serif;'
    MONO_CSS = 'font-family: ArialUnicode, "Menlo", "Courier New", monospace;'
else:
    FONT_FACE = ""
    FONT_CSS = 'font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;'
    MONO_CSS = 'font-family: "Menlo", "Courier New", monospace;'

PDF_CSS = f"""
{FONT_FACE}

@page {{
    size: A4;
    margin: 2.5cm;
}}
body {{
    {FONT_CSS}
    font-size: 11pt;
    line-height: 1.6;
    color: #222;
}}
h1 {{ font-size: 20pt; margin-top: 24pt; margin-bottom: 12pt; color: #111; {FONT_CSS} }}
h2 {{ font-size: 16pt; margin-top: 20pt; margin-bottom: 10pt; color: #222; {FONT_CSS} }}
h3 {{ font-size: 13pt; margin-top: 16pt; margin-bottom: 8pt; color: #333; {FONT_CSS} }}
h4 {{ font-size: 11pt; margin-top: 12pt; margin-bottom: 6pt; {FONT_CSS} }}
p  {{ margin-bottom: 8pt; }}
img {{
    max-width: 100%;
    margin: 10pt auto;
    display: block;
}}
code {{
    {MONO_CSS}
    font-size: 9pt;
    background: #f4f4f4;
    padding: 1pt 3pt;
    border-radius: 2pt;
}}
pre {{
    {MONO_CSS}
    font-size: 8.5pt;
    background: #f4f4f4;
    padding: 10pt;
    border-radius: 4pt;
    overflow-x: auto;
    line-height: 1.4;
}}
pre code {{
    background: none;
    padding: 0;
}}
blockquote {{
    border-left: 3pt solid #ccc;
    margin-left: 0;
    padding-left: 12pt;
    color: #555;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 10pt 0;
}}
th, td {{
    border: 0.5pt solid #ccc;
    padding: 6pt 10pt;
    text-align: left;
}}
th {{
    background: #f0f0f0;
    font-weight: bold;
}}
a {{ color: #0066cc; text-decoration: none; }}
hr {{ border: none; border-top: 0.5pt solid #ccc; margin: 16pt 0; }}
ul, ol {{ margin-bottom: 8pt; }}
li {{ margin-bottom: 4pt; }}
"""


def embed_image(src_path: str, md_dir: str) -> str:
    """Convert an image file path to a base64 data URI."""
    # Resolve path relative to the markdown file's directory
    if not os.path.isabs(src_path):
        full_path = os.path.normpath(os.path.join(md_dir, src_path))
    else:
        full_path = src_path

    if not os.path.isfile(full_path):
        # Try URL-decoded version (spaces in filenames)
        import urllib.parse
        decoded = os.path.normpath(os.path.join(md_dir, urllib.parse.unquote(src_path)))
        if os.path.isfile(decoded):
            full_path = decoded
        else:
            # Try stripping leading ../ and resolving relative to md_dir
            # (handles ../travel-images/ → travel-images/)
            stripped = re.sub(r'^\.\./+', '', src_path).lstrip('./')
            stripped_path = os.path.normpath(os.path.join(md_dir, stripped))
            if os.path.isfile(stripped_path):
                full_path = stripped_path
            else:
                # Walk up from md_dir looking for a matching relative path
                found = False
                check_dir = md_dir
                for _ in range(5):
                    parent = os.path.dirname(check_dir)
                    if parent == check_dir:
                        break
                    candidate = os.path.normpath(os.path.join(parent, src_path))
                    if os.path.isfile(candidate):
                        full_path = candidate
                        found = True
                        break
                    check_dir = parent
                if not found:
                    print(f"   WARNING: Image not found: {full_path} -- skipping")
                    return src_path

    mime, _ = mimetypes.guess_type(full_path)
    if mime is None:
        mime = "image/png"  # fallback

    try:
        with open(full_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{data}"
    except Exception as e:
        print(f"  WARNING: Error reading image {full_path}: {e}")
        return src_path


def process_html_images(html: str, md_dir: str) -> str:
    """Find all <img> tags and embed local images as base64 data URIs."""

    def replace_img(match):
        full_tag = match.group(0)
        src_match = re.search(r'src=["\']([^"\']+)["\']', full_tag)
        if not src_match:
            return full_tag

        src = src_match.group(1)

        # Skip already-embedded data URIs
        if src.startswith("data:"):
            return full_tag

        # Handle remote URLs — download and embed
        if src.startswith(("http://", "https://")):
            try:
                import urllib.request
                req = urllib.request.Request(src, headers={"User-Agent": "md2pdf/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    img_data = resp.read()
                content_type = resp.headers.get("Content-Type", "image/png")
                b64 = base64.b64encode(img_data).decode("ascii")
                new_src = f"data:{content_type};base64,{b64}"
                return full_tag.replace(src_match.group(1), new_src)
            except Exception as e:
                print(f"  WARNING: Failed to download {src}: {e}")
                return full_tag

        # Local file — embed as base64
        new_src = embed_image(src, md_dir)
        if new_src != src:
            return full_tag.replace(src_match.group(1), new_src)
        return full_tag

    return re.sub(r'<img\s[^>]*?>', replace_img, html, flags=re.IGNORECASE)


def md_to_pdf(md_path: str, pdf_path: str = None) -> str:
    """Convert a Markdown file to PDF, embedding all linked images."""
    md_path = os.path.abspath(md_path)
    if not os.path.isfile(md_path):
        raise FileNotFoundError(f"Markdown file not found: {md_path}")

    md_dir = os.path.dirname(md_path)
    md_filename = os.path.basename(md_path)

    if pdf_path is None:
        pdf_path = os.path.splitext(md_path)[0] + ".pdf"
    pdf_path = os.path.abspath(pdf_path)

    # Read markdown
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    print(f"Converting: {md_filename}")
    print(f"   Source: {md_path}")

    # Convert markdown to HTML (with extensions for tables, fenced code, etc.)
    html_body = markdown.markdown(
        md_text,
        extensions=[
            "tables",
            "fenced_code",
            "codehilite",
            "toc",
            "smarty",
            "attr_list",
            "md_in_html",
        ],
        extension_configs={
            "codehilite": {"css_class": "highlight", "guess_lang": True},
        },
    )

    # Process images — embed local & remote as base64
    img_count = html_body.count("<img")
    if img_count > 0:
        print(f"   Embedding {img_count} image(s)...")
    html_body = process_html_images(html_body, md_dir)

    # Build full HTML document
    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{PDF_CSS}</style>
</head>
<body>
{html_body}
</body>
</html>"""

    # Convert HTML → PDF
    font_info = "ArialUnicode (full Unicode: Cyrillic, Georgian, CJK)" if UNICODE_FONT_AVAILABLE else "Helvetica (Latin only — non-Latin chars may not render)"
    print(f"   Font: {font_info}")
    print(f"   Generating PDF...")
    with open(pdf_path, "wb") as f:
        doc = pisa.CreatePDF(full_html, dest=f)

    if doc.err:
        print(f"   WARNING: {doc.err} error(s) during PDF generation")

    size_kb = os.path.getsize(pdf_path) / 1024
    print(f"Done: {pdf_path} ({size_kb:.1f} KB)")
    return pdf_path


def main():
    if len(sys.argv) < 2:
        print("Usage: md2pdf <input.md> [output.pdf]")
        sys.exit(1)

    md_path = sys.argv[1]
    pdf_path = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        result = md_to_pdf(md_path, pdf_path)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()