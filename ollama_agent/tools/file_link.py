"""File link tool: generate file:// URLs for files."""

import os
from pathlib import Path


class FileLinkTool:
    """Generate file:// URLs for files in the working directory."""
    name = "file_link"
    description = "Generate a file:// URL for a file in the working directory."
    system_prompt = (
        "## file_link\n"
        "Generate a file:// URL for a file in the working directory.\n"
        "Parameters (JSON object):\n"
        "- path (string, required): Path to the file (relative to workdir or absolute)\n"
        "Use this to generate file:// URLs that can be used to reference files in the working directory.\n"
        "Example: file_link with path='README.md' returns 'file:///C:/Users/.../README.md'\n"
        "When presenting file:// URLs to the user, output the plain URL — do NOT wrap it in a markdown link like [url](url)."
    )
    parameters = {
        "path": {
            "type": "string",
            "description": "Path to the file (relative to workdir or absolute)",
            "required": True,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        path = params.get("path", "")

        if not path:
            return "Error: 'path' is required"

        # Resolve the full path
        full_path = os.path.join(workdir, path) if not os.path.isabs(path) else path

        # Normalize the path
        full_path = os.path.normpath(full_path)

        # Check if file exists
        if not os.path.isfile(full_path):
            return f"Error: File not found: {path}"

        # Convert to file:// URL.
        # On Windows, use the raw Unicode path (not percent-encoded) because
        # Windows terminals (cmd.exe, conhost, older Windows Terminal) do NOT
        # decode percent-encoding when opening file:// links — they pass the
        # raw string to the shell, so %D1%80... would look for a literal file
        # with that name, which doesn't exist. Windows file systems accept
        # Unicode natively, so the unencoded form works when clicked.
        # On Unix, use pathlib's as_uri() which percent-encodes per RFC 8089.
        if os.name == 'nt':
            # Build file:// URL manually, only encoding characters that are
            # truly unsafe in a URL (space, #, ?, %) but leaving Unicode as-is
            url_path = full_path.replace('\\', '/')
            # Prefix with / for drive letters (C:/ -> /C:/)
            if len(url_path) >= 2 and url_path[1] == ':':
                url_path = '/' + url_path
            # Encode only the minimal unsafe chars, keep Unicode intact
            for char, enc in [(' ', '%20'), ('#', '%23'), ('?', '%3F'), ('%', '%25')]:
                url_path = url_path.replace(char, enc)
            return 'file://' + url_path
        return Path(full_path).as_uri()
