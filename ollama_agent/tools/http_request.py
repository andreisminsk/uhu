"""HTTP request tool: make GET/POST/PUT/DELETE requests with structured output."""

import json


class HttpRequestTool:
    """Make HTTP requests and return structured responses."""
    name = "http_request"
    description = "Make HTTP requests (GET, POST, PUT, DELETE) and return structured responses."
    system_prompt = (
        "## http_request\n"
        "Make HTTP requests and return structured responses.\n"
        "Parameters (JSON object):\n"
        "- url (string, required): The URL to request\n"
        "- method (string, optional, default GET): HTTP method — GET, POST, PUT, PATCH, DELETE\n"
        "- headers (object, optional): Request headers as key-value pairs\n"
        "- body (string, optional): Request body (for POST/PUT/PATCH)\n"
        "- json_body (object, optional): Request body as JSON (for POST/PUT/PATCH) — overrides body\n"
        "- timeout (integer, optional, default 30): Timeout in seconds\n"
        "- max_length (integer, optional, default 5000): Maximum response body length to return\n"
        "Use this for API testing and HTTP operations. Avoids shell quoting issues with curl."
    )
    parameters = {
        "url": {
            "type": "string",
            "description": "The URL to request",
            "required": True,
        },
        "method": {
            "type": "string",
            "description": "HTTP method: GET, POST, PUT, PATCH, DELETE (default GET)",
            "required": False,
        },
        "headers": {
            "type": "object",
            "description": "Request headers as key-value pairs",
            "required": False,
        },
        "body": {
            "type": "string",
            "description": "Request body (for POST/PUT/PATCH)",
            "required": False,
        },
        "json_body": {
            "type": "object",
            "description": "Request body as JSON (overrides body)",
            "required": False,
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds (default 30)",
            "required": False,
        },
        "max_length": {
            "type": "integer",
            "description": "Maximum response body length to return (default 5000)",
            "required": False,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        url = params.get("url", "")
        method = params.get("method", "GET").upper()
        headers = params.get("headers", {})
        body = params.get("body", "")
        json_body = params.get("json_body")
        timeout = params.get("timeout", 30)
        max_length = params.get("max_length", 5000)

        if not url:
            return "Error: 'url' is required"

        try:
            import httpx
        except ImportError:
            return "Error: httpx is not installed. Install it with: pip install httpx"

        # Build request kwargs — set a browser-like User-Agent if none provided
        default_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        req_headers = headers or {}
        if "User-Agent" not in {k.title() for k in req_headers}:
            req_headers.setdefault("User-Agent", default_ua)
        request_kwargs = {
            "timeout": timeout,
            "headers": req_headers,
        }

        if json_body is not None:
            request_kwargs["json"] = json_body
        elif body:
            request_kwargs["content"] = body

        try:
            with httpx.Client() as client:
                response = client.request(method, url, **request_kwargs)
        except httpx.TimeoutException:
            return f"Error: Request timed out after {timeout}s"
        except httpx.ConnectError as e:
            return f"Error: Connection failed: {e}"
        except Exception as e:
            return f"Error: {e}"

        # Build result
        result_parts = []
        result_parts.append(f"Status: {response.status_code} {response.reason_phrase}")

        # Headers
        important_headers = {}
        for key in ("content-type", "content-length", "location", "set-cookie"):
            for k, v in response.headers.items():
                if k.lower() == key:
                    important_headers[k] = v
        if important_headers:
            header_lines = [f"  {k}: {v}" for k, v in important_headers.items()]
            result_parts.append("Headers:\n" + "\n".join(header_lines))

        # Body
        body_text = response.text
        content_type = response.headers.get("content-type", "")

        # Try to pretty-print JSON
        if "json" in content_type or body_text.strip().startswith(("{", "[")):
            try:
                parsed = json.loads(body_text)
                body_text = json.dumps(parsed, indent=2, ensure_ascii=False)
            except (json.JSONDecodeError, ValueError):
                pass

        if len(body_text) > max_length:
            body_text = body_text[:max_length] + f"\n... [truncated, {len(response.text)} chars total]"

        result_parts.append(f"Body:\n{body_text}")

        return "\n".join(result_parts)
