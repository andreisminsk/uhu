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

        # Convert to file:// URL using pathlib, which correctly handles:
        # - URL encoding of spaces, #, ?, %, non-ASCII characters
        # - UNC paths on Windows (\\server\share → file://server/share)
        # - Platform-appropriate format (file:///C:/... on Windows, file:///... on Unix)
        return Path(full_path).as_uri()
