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
    do_not_truncate_observations = True
    description = (
        "Analyze an image file using a vision-capable model. "
        "Params: {\"path\": \"<file_path>\", \"prompt\": \"<optional question>\", \"model\": \"<optional model override>\"}"
    )
    system_prompt = (
        "## image-analysis\n"
        "Analyzes an image file using a vision-capable Ollama model.\n"
        "Parameters (JSON object):\n"
        "- path (string, required): Path to the image file (use /attach-bin first to make the model aware of it)\n"
        "- prompt (string, optional, default \"Describe this image in detail.\"): Question or instruction about the image\n"
        "- model (string, optional): Override the configured model (default from .ollama_agent.json)"
    )

    def _get_tool_config(self, workdir=None):
        """Load image_analysis config from .ollama_agent.json."""
        from ._config import load_config, DEFAULT_CONFIG
        config = load_config(workdir)
        tool_config = config.get("tools", {}).get("image_analysis", DEFAULT_CONFIG["tools"]["image_analysis"])
        base_url = tool_config.get("base_url", "http://localhost:11434/")
        model = tool_config.get("model", "gemma4:31b-cloud")
        api_type = tool_config.get("api_type", "ollama")
        return base_url, model, api_type

    def get_details(self, params, workdir=None):
        """Return extra info for confirmation details display."""
        base_url, model, api_type = self._get_tool_config(workdir)
        return f"  model: {model}\n  base_url: {base_url}\n  api_type: {api_type}"

    def execute(self, params, workdir=None):
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
        base_url, model, api_type = self._get_tool_config(workdir)
        # Allow per-call model override
        model = params.get("model") or model

        # Read and base64 encode the image
        try:
            with open(full_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            return f"[Error: Failed to read image: {e}]"

        # Load timeout from config
        from ._config import load_config, DEFAULT_CONFIG
        config = load_config(workdir)
        tool_config = config.get("tools", {}).get("image_analysis", DEFAULT_CONFIG["tools"]["image_analysis"])
        timeout = tool_config.get("timeout", 120)  # Default 120s timeout
        api_key = tool_config.get("api_key", "ollama")
        
        def _call_with_timeout():
            if api_type == "openai":
                # Use OpenAI-compatible API
                try:
                    from openai import OpenAI
                except ImportError:
                    raise RuntimeError("openai package required for OpenAI API. Run: pip install openai")
                
                # Ensure /v1 suffix
                api_base = base_url
                if not api_base.endswith("/v1"):
                    api_base = api_base.rstrip("/") + "/v1"
                
                client = OpenAI(base_url=api_base, api_key=api_key)
                
                # Build multimodal message for OpenAI API
                messages = [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{image_data}"
                            }
                        }
                    ]
                }]
                
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=4096,
                    timeout=timeout
                )
                return response.choices[0].message.content
            else:
                # Use native Ollama API
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
                return response["message"]["content"]
        
        # Execute with timeout using threading
        import threading
        result_holder = [None]
        error_holder = [None]
        done_event = threading.Event()
        
        def _worker():
            try:
                result_holder[0] = _call_with_timeout()
            except Exception as e:
                error_holder[0] = e
            finally:
                done_event.set()
        
        try:
            worker = threading.Thread(target=_worker, daemon=True)
            worker.start()
            
            if not done_event.wait(timeout=timeout):
                return f"[Error: Image analysis timed out after {timeout}s (model: {model}, api_type: {api_type})]"
            
            if error_holder[0]:
                raise error_holder[0]

            return f"[image-analysis | model: {model} | base_url: {base_url} | api_type: {api_type}]\n\n{result_holder[0]}"
            
        except KeyboardInterrupt:
            raise
        except Exception as e:
            return f"[Error: Image analysis failed (model: {model}, base_url: {base_url}, api_type: {api_type}): {e}]"
