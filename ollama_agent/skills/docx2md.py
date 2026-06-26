"""docx2md skill — convert DOCX files to clean AI-ready Markdown."""

import os
import re
from pathlib import Path
from urllib.parse import unquote

from .base import Skill


def _clean_md(text: str) -> str:
    """Clean converted Markdown for AI ingestion."""
    # Unwrap Outlook safe links
    def unwrap(m):
        u = re.search(r'\?url=([^&]+)', m.group(0))
        return unquote(u.group(1)) if u else m.group(0)

    text = re.sub(r'https?://[^\s/]+\.safelinks\.protection\.outlook\.com/\?[^\s)]+', unwrap, text)

    # Remove 'From <...>' lines
    text = re.sub(r'From\s*<\*?https?://[^>]+\*?>\s*\n?', '', text)

    # Remove outlook mail URLs in markdown links
    text = re.sub(r'\[([^\]]*?)\]\(https?://outlook\.office\.com/mail/[^)]+\)', r'\1', text)

    # Remove bare angle-bracket mail URLs
    text = re.sub(r'<\*?https?://outlook\.office\.com/mail/[^>]+\*?>', '', text)

    # Clean remaining angle-bracket URLs
    text = re.sub(r'<(https?://[^>]+)>', r'\1', text)

    # Remove base64 images
    text = re.sub(r'!\[[^\]]*\]\(data:image/[^)]+\)', '', text)

    # Remove markdown table pipes and dividers
    text = re.sub(r'^\s*\|\s*---\s*\|\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\|\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\|\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*\|$', '', text, flags=re.MULTILINE)

    # Mark page boundaries: title + date + time pattern
    text = re.sub(
        r'(?:^|\n)([^\n]+)\n\n((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+\w+\s+\d{1,2},\s+\d{4})\n\n(\d{1,2}:\d{2}\s*(?:AM|PM))\n',
        r'\n\n---\n<!-- PAGE: \1 -->\n## \1\n\2\n\n\3\n',
        text
    )

    # Remove multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip() + '\n'


class Docx2MdSkill(Skill):
    name = "docx2md"
    description = "Convert DOCX (Word) files to clean AI-ready Markdown — use this whenever a user wants to convert, transform, or read a .docx file as Markdown"
    triggers = ["convert docx", "docx to markdown", "docx to md", "word to markdown", "convert word document", "docx file", ".docx", "convert to md", "convert to markdown", "docx conversion", "word document to markdown"]
    system_prompt = (
        "## docx2md\n"
        "Convert a DOCX file to clean AI-ready Markdown.\n"
        "Parameters (JSON object):\n"
        "- input (string, required): Path to the .docx file to convert\n"
        "- output (string, optional): Output .md path (default: <input>.md)\n"
        "\n"
        "When this skill is invoked, it converts the DOCX file to Markdown and "
        "reports the result. The conversion cleans up Outlook safe links, removes "
        "base64 images, strips table pipes, and marks page boundaries.\n"
        "\n"
        "Dependencies: markitdown (pip install markitdown)\n"
    )
    parameters = {
        "input": {"type": "string", "required": True, "description": "Path to the .docx file to convert"},
        "output": {"type": "string", "required": False, "description": "Output .md path (default: <input>.md)"},
    }

    def execute(self, params, workdir=None, session=None):
        docx_input = params.get("input", "")
        md_output = params.get("output", "")

        if not docx_input:
            return "[Skill error: 'input' parameter is required for docx2md]"

        # Resolve relative to workdir
        full_input = os.path.join(workdir or ".", docx_input) if not os.path.isabs(docx_input) else docx_input
        full_input = os.path.normpath(full_input)

        if not os.path.isfile(full_input):
            return f"[Skill error: File not found: {full_input}]"

        # Determine output path
        if md_output:
            full_output = os.path.join(workdir or ".", md_output) if not os.path.isabs(md_output) else md_output
        else:
            full_output = os.path.splitext(full_input)[0] + ".md"
        full_output = os.path.normpath(full_output)

        try:
            from markitdown import MarkItDown
        except ImportError:
            return (
                "[Skill error: markitdown is not installed. "
                "Install it with: pip install markitdown]"
            )

        try:
            md = MarkItDown()
            result = md.convert(str(full_input))
            cleaned = _clean_md(result.text_content)

            # Ensure output directory exists
            os.makedirs(os.path.dirname(full_output) or ".", exist_ok=True)
            Path(full_output).write_text(cleaned, encoding="utf-8")

            return (
                f"Converted {docx_input} -> {md_output or os.path.basename(full_output)} "
                f"({len(cleaned)} chars)"
            )
        except Exception as e:
            return f"[Skill error: Conversion failed: {e}]"
