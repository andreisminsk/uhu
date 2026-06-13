"""image-analysis tool — analyze images using a vision-capable Ollama model."""

import base64
import os

from ..constants import MIME_TYPES

# Image MIME types this tool can handle
IMAGE_MIME_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/bmp',
    'image/webp', 'image/tiff', 'image/x-icon',
}


class ImageAnalysisTool:
    name = "image-analysis"
    description = (
        "Analyze an image file using a vision-capable model. "
        "Params: {\"path\": \"<file_path>\", \"prompt\": \"<optional question>\"}"
    )
    system_prompt = (
        "## image-analysis\n"
        "Analyzes an image file using a vision-capable Ollama model.\n"
        "Parameters (JSON object):\n"
        "- path (string, required): Path to the image file (use /attach-bin first to make the model aware of it)\n"
        "- prompt (string, optional, default \"Describe this image in detail.\"): Question or instruction about the image"
    )

    def execute(self, params, workdir=None):
        from ._config import load_config, DEFAULT_CONFIG

        path = params.get("path", params.get("file", ""))
        prompt = params.get("prompt", "Describe this image in detail.")

        if not path:
            return "[Error: 'path' parameter is required for image-analysis]"

        # Resolve path relative to workdir
        full_path = os.path.join(workdir or ".", path) if not os.path.isabs(path) else path
        full_path = os.path.normpath(full_path)

        if not os.path.isfile(full_path):
            return f"[Error: File not found: {full_path}]"

        # Validate image type
        ext = os.path.splitext(full_path)[1].lower()
        mime = MIME_TYPES.get(ext, "")
        if mime not in IMAGE_MIME_TYPES:
            supported = ", ".join(sorted(IMAGE_MIME_TYPES))
            return f"[Error: Not an image file (got {mime or 'unknown'} for {ext}). Supported MIME types: {supported}]"

        # Check file size (max 20MB)
        size = os.path.getsize(full_path)
        max_size = 20 * 1024 * 1024
        if size > max_size:
            return f"[Error: Image too large ({size / (1024*1024):.1f} MB). Maximum: 20 MB]"

        # Load config
        config = load_config(workdir)
        tool_config = config.get("tools", {}).get("image_analysis", DEFAULT_CONFIG["tools"]["image_analysis"])
        base_url = tool_config.get("base_url", "http://localhost:11434/")
        model = tool_config.get("model", "gemma4:31b-cloud")

        # Read and base64 encode the image
        try:
            with open(full_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            return f"[Error: Failed to read image: {e}]"

        # Call Ollama vision model
        try:
            from ollama import Client
            client = Client(host=base_url)
            response = client.chat(
                model=model,
                messages=[{
                    "role": "user",
                    "content": prompt,
                    "images": [image_data]
                }]
            )
            result = response["message"]["content"]
            return result
        except Exception as e:
            return f"[Error: Image analysis failed (model: {model}, base_url: {base_url}): {e}]"
