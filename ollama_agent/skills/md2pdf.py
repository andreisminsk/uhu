"""md2pdf skill — Convert Markdown files with linked images to self-contained PDFs.

Permanent (built-in) skill. Converts a .md file to a polished PDF, embedding
all locally-linked and remote images as base64 data URIs.
"""

import os
import re
import sys
import base64
import mimetypes

from .base import Skill


# ─── Unicode Font Setup ──────────────────────────────────────────────────

ARIAL_UNICODE_PATH = "/Library/Fonts/Arial Unicode.ttf"
UNICODE_FONT_AVAILABLE = os.path.isfile(ARIAL_UNICODE_PATH)

if UNICODE_FONT_AVAILABLE:
    FONT_FACE = f"""
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


def _embed_image(src_path, md_dir):
    """Convert an image file path to a base64 data URI."""
    if not os.path.isabs(src_path):
        full_path = os.path.normpath(os.path.join(md_dir, src_path))
    else:
        full_path = src_path

    if not os.path.isfile(full_path):
        import urllib.parse
        decoded = os.path.normpath(os.path.join(md_dir, urllib.parse.unquote(src_path)))
        if os.path.isfile(decoded):
            full_path = decoded
        else:
            stripped = re.sub(r'^\.\./+', '', src_path).lstrip('./')
            stripped_path = os.path.normpath(os.path.join(md_dir, stripped))
            if os.path.isfile(stripped_path):
                full_path = stripped_path
            else:
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
                    return None, f"Image not found: {full_path}"

    mime, _ = mimetypes.guess_type(full_path)
    if mime is None:
        mime = "image/png"

    try:
        with open(full_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{data}", None
    except Exception as e:
        return None, f"Error reading image {full_path}: {e}"


def _process_html_images(html, md_dir):
    """Find all <img> tags and embed local/remote images as base64 data URIs."""

    def replace_img(match):
        full_tag = match.group(0)
        src_match = re.search(r'src=["\']([^"\']+)["\']', full_tag)
        if not src_match:
            return full_tag

        src = src_match.group(1)

        if src.startswith("data:"):
            return full_tag

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
                return full_tag

        new_src, _err = _embed_image(src, md_dir)
        if new_src:
            return full_tag.replace(src_match.group(1), new_src)
        return full_tag

    return re.sub(r'<img\s[^>]*?>', replace_img, html, flags=re.IGNORECASE)


def md_to_pdf(md_path, pdf_path=None):
    """Convert a Markdown file to PDF, embedding all linked images.

    Returns (pdf_path, warnings_list).
    """
    import markdown
    import xhtml2pdf.pisa as pisa

    md_path = os.path.abspath(md_path)
    if not os.path.isfile(md_path):
        raise FileNotFoundError(f"Markdown file not found: {md_path}")

    md_dir = os.path.dirname(md_path)
    md_filename = os.path.basename(md_path)

    if pdf_path is None:
        pdf_path = os.path.splitext(md_path)[0] + ".pdf"
    pdf_path = os.path.abspath(pdf_path)

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    warnings = []

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

    img_count = html_body.count("<img")
    if img_count > 0:
        # Track warnings during image processing
        html_body = _process_html_images(html_body, md_dir)

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

    with open(pdf_path, "wb") as f:
        doc = pisa.CreatePDF(full_html, dest=f)

    if doc.err:
        warnings.append(f"{doc.err} error(s) during PDF generation")

    return pdf_path, warnings


class Md2PdfSkill(Skill):
    name = "md2pdf"
    description = "Convert Markdown files with linked images to self-contained PDFs"
    system_prompt = (
        "## md2pdf\n"
        "Convert a Markdown file to a polished PDF, embedding all locally-linked\n"
        "and remote images as base64 data URIs.\n"
        "Parameters (JSON object):\n"
        "- input (string, required): Path to the .md file to convert\n"
        "- output (string, optional): Output PDF path (default: <input>.pdf)\n"
        "\n"
        "When this skill is invoked, it converts the markdown file to PDF and\n"
        "reports the result. Dependencies: markdown, pymdown-extensions, xhtml2pdf.\n"
    )
    parameters = {
        "input": {"type": "string", "required": True, "description": "Path to the .md file to convert"},
        "output": {"type": "string", "required": False, "description": "Output PDF path (default: <input>.pdf)"},
    }

    def execute(self, params, workdir=None, session=None):
        md_input = params.get("input", "")
        pdf_output = params.get("output", "")

        if not md_input:
            return "[Skill error: 'input' parameter is required for md2pdf]"

        # Resolve relative to workdir
        full_md = os.path.join(workdir or ".", md_input) if not os.path.isabs(md_input) else md_input
        full_pdf = None
        if pdf_output:
            full_pdf = os.path.join(workdir or ".", pdf_output) if not os.path.isabs(pdf_output) else pdf_output

        if not os.path.isfile(full_md):
            return f"[Skill error: Markdown file not found: {md_input}]"

        # Check dependencies
        missing = []
        try:
            import markdown  # noqa: F401
        except ImportError:
            missing.append("markdown")
        try:
            import xhtml2pdf  # noqa: F401
        except ImportError:
            missing.append("xhtml2pdf")
        if missing:
            return (
                f"[Skill md2pdf invoked]\n"
                f"Input: {md_input}\n"
                f"⚠ Missing dependencies: {', '.join(missing)}\n"
                f"Install with: pip install {' '.join(missing)} pymdown-extensions\n"
                f"See requirements.txt for details."
            )

        try:
            result_path, warnings = md_to_pdf(full_md, full_pdf)
            size_kb = os.path.getsize(result_path) / 1024
            parts = [
                f"[Skill md2pdf invoked]",
                f"Input: {md_input}",
                f"Output: {result_path} ({size_kb:.1f} KB)",
            ]
            if warnings:
                parts.append(f"Warnings: {'; '.join(warnings)}")
            parts.append("Conversion complete.")
            return "\n".join(parts)
        except FileNotFoundError as e:
            return f"[Skill error: {e}]"
        except Exception as e:
            return f"[Skill error: Conversion failed: {e}]"
