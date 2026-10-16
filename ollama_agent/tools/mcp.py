"""MCP (Model Context Protocol) client — discovers and invokes tools from MCP servers.

Supports three transport types:
- SSE: HTTP Server-Sent Events (url ending with /sse)
- Streamable HTTP: Direct POST (url not ending with /sse, e.g. HuggingFace)
- stdio: Subprocess communication (command field in config)

MCP servers are configured in .ollama_agent.json under "mcpServers".
Each server's tools are discovered at startup and registered as uhu tools
with prefixed names: mcp_<server>_<tool>.
"""

import json
import os
import shutil
import queue
import subprocess
from ..actions import agent_print
import threading
import uuid

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class MCPError(RuntimeError):
    """JSON-RPC error returned by an MCP server — reconnecting won't help."""


class MCPConnectionError(RuntimeError):
    """Transport/connection failure — a reconnect may restore the session."""


# ── MCP Tool wrapper ────────────────────────────────────────────────────

class MCPTool:
    """A uhu Tool backed by an MCP server tool."""

    def __init__(self, name, description, input_schema, server_name, transport, auto_approve=False, original_name=None):
        self.name = name
        self.description = description
        self.input_schema = input_schema or {}
        self.system_prompt = self._build_system_prompt()
        self.parameters = self._build_parameters()
        self.server_name = server_name
        self.transport = transport
        self.auto_approve = auto_approve
        self.original_name = original_name or name

    def _build_system_prompt(self):
        param_docs = ""
        if self.input_schema:
            props = self.input_schema.get("properties", {})
            required = self.input_schema.get("required", [])
            if props:
                lines = []
                for pname, pdef in props.items():
                    ptype = pdef.get("type", "any")
                    req = "required" if pname in required else "optional"
                    pdesc = pdef.get("description", "")
                    lines.append(f"- {pname} ({ptype}, {req}): {pdesc}")
                param_docs = "\n".join(lines)

        parts = [
            f"## {self.name}",
            self.description,
        ]
        if param_docs:
            parts.append("")
            parts.append("Parameters (JSON object):")
            parts.append(param_docs)
        parts.append("")
        parts.append(f"Invoke as: **TOOL:`{self.name}`**")
        parts.append("```json")
        if self.input_schema and self.input_schema.get("properties"):
            example = {}
            for pname in list(self.input_schema.get("properties", {}).keys())[:3]:
                example[pname] = "..."
            parts.append(json.dumps(example, ensure_ascii=False))
        else:
            parts.append("{}")
        parts.append("```")
        parts.append(f"**EOF:`{self.name}`**")
        return "\n".join(parts)

    def _build_parameters(self):
        """Build parameters dict from input_schema for compatibility with tool execution."""
        params = {}
        props = self.input_schema.get("properties", {})
        required = self.input_schema.get("required", [])
        for pname, pdef in props.items():
            params[pname] = {
                "type": pdef.get("type", "string"),
                "required": pname in required,
                "description": pdef.get("description", ""),
            }
        return params

    # Threshold: if text output exceeds this, save to file instead of inlining
    _LARGE_OUTPUT_THRESHOLD = 6000  # chars — well under MAX_TOOL_OBSERVATION_CHARS

    @staticmethod
    def _detect_extension(text, mime_type=""):
        """Guess file extension from content and MIME type."""
        if mime_type:
            mime_map = {
                "image/svg+xml": ".svg",
                "text/html": ".html",
                "text/xml": ".xml",
                "application/json": ".json",
                "text/csv": ".csv",
                "text/markdown": ".md",
                "text/plain": ".txt",
            }
            ext = mime_map.get(mime_type)
            if ext:
                return ext
        # Fallback: sniff content
        stripped = text.lstrip()
        if stripped.startswith("<svg") or stripped.startswith("<?xml") and "<svg" in stripped[:200]:
            return ".svg"
        if stripped.startswith("<!DOCTYPE html") or stripped.startswith("<html"):
            return ".html"
        if stripped.startswith("{") or stripped.startswith("["):
            return ".json"
        if stripped.startswith("#") or stripped.startswith("graph ") or stripped.startswith("sequenceDiagram"):
            return ".md"
        return ".txt"

    def _invoke_with_reconnect(self, params):
        """Call the tool; on connection loss, reconnect once and retry.

        JSON-RPC errors from the server (MCPError) are not retried — the
        transport is alive, the tool call itself simply failed.
        """
        try:
            return self.transport.call_tool(
                tool_name=self.original_name,
                arguments=params or {},
            )
        except MCPConnectionError as e:
            try:
                self.transport.reconnect()
            except Exception as re_err:
                raise MCPConnectionError(
                    f"connection lost ({e}); reconnect failed: {re_err}")
            return self.transport.call_tool(
                tool_name=self.original_name,
                arguments=params or {},
            )

    def execute(self, params, workdir=None):
        """Invoke the MCP tool and return the result."""
        try:
            result = self._invoke_with_reconnect(params)
            if isinstance(result, dict):
                content = result.get("content", [])
                if content:
                    parts = []
                    for item in content:
                        if isinstance(item, dict):
                            mime_type = item.get("mimeType", "")
                            if mime_type.startswith("image/") or mime_type == "application/octet-stream":
                                import base64
                                data = item.get("data", "")
                                ext = mime_type.split("/")[-1].replace("jpeg", "jpg")
                                if ext == "plain":
                                    ext = "txt"
                                filename = f"{self.name}_{len(parts)}.{ext}"
                                filepath = os.path.join(workdir, filename) if workdir else filename
                                try:
                                    binary = base64.b64decode(data)
                                    with open(filepath, "wb") as f:
                                        f.write(binary)
                                    parts.append(f"Image saved to: {filepath} ({len(binary)} bytes)")
                                except Exception as e:
                                    parts.append(f"[Binary data: {mime_type}, {len(data)} chars — save failed: {e}]")
                            else:
                                text = item.get("text", "")
                                if text:
                                    # Save large text output to file to avoid truncation
                                    if len(text) > self._LARGE_OUTPUT_THRESHOLD and workdir:
                                        ext = self._detect_extension(text, mime_type)
                                        filename = f"{self.name}_output{ext}"
                                        filepath = os.path.join(workdir, filename)
                                        try:
                                            with open(filepath, "w", encoding="utf-8") as f:
                                                f.write(text)
                                            parts.append(
                                                f"Output saved to: {filepath} ({len(text)} chars). "
                                                f"Use FILE: to read the full content."
                                            )
                                        except Exception as e:
                                            parts.append(f"[Failed to save output to {filepath}: {e}]")
                                            parts.append(text)
                                    else:
                                        parts.append(text)
                        elif isinstance(item, str):
                            if len(item) > self._LARGE_OUTPUT_THRESHOLD and workdir:
                                ext = self._detect_extension(item)
                                filename = f"{self.name}_output{ext}"
                                filepath = os.path.join(workdir, filename)
                                try:
                                    with open(filepath, "w", encoding="utf-8") as f:
                                        f.write(item)
                                    parts.append(
                                        f"Output saved to: {filepath} ({len(item)} chars). "
                                        f"Use FILE: to read the full content."
                                    )
                                except Exception as e:
                                    parts.append(f"[Failed to save output to {filepath}: {e}]")
                                    parts.append(item)
                            else:
                                parts.append(item)
                    return "\n".join(parts) if parts else json.dumps(result, indent=2)
                return json.dumps(result, indent=2)
            return str(result)
        except Exception as e:
            return f"[MCP tool error: {e}]"


# ── SSE Transport ───────────────────────────────────────────────────────

class SSETransport:
    """Communicate with an MCP server via HTTP SSE.

    Used for servers with /sse endpoint (e.g. mcp-imagineer).
    """

    def __init__(self, url, name, timeout=120, quiet=False, auth_token=None, headers=None):
        self.url = url.rstrip("/")
        self.name = name
        self.timeout = timeout
        self.quiet = quiet
        self.auth_token = auth_token
        self.extra_headers = headers or {}
        self.connect_timeout = 30 if self.url.startswith("https://") else 15
        self.message_url = None
        self._session = None
        self._initialized = False
        self._sse_thread = None
        self._sse_response = None
        self._response_queue = None
        self._endpoint_event = None

    def connect(self):
        if not HAS_REQUESTS:
            raise ImportError("requests library is required. Install with: pip install requests")

        import queue
        self._response_queue = queue.Queue()
        self._endpoint_event = threading.Event()

        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        if self.auth_token:
            self._session.headers["Authorization"] = f"Bearer {self.auth_token}"
        if self.extra_headers:
            self._session.headers.update(self.extra_headers)

        sse_url = self.url if self.url.endswith("/sse") else self.url + "/sse"

        try:
            self._sse_response = self._session.get(
                sse_url, stream=True, timeout=self.timeout,
                headers={"Accept": "text/event-stream"})
            self._sse_response.raise_for_status()
        except Exception as e:
            raise MCPConnectionError(f"MCP SSE: failed to connect to {sse_url}: {e}")

        self._sse_thread = threading.Thread(target=self._sse_reader, daemon=True)
        self._sse_thread.start()

        if not self._endpoint_event.wait(timeout=self.connect_timeout):
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(self.url)
            base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
            self.message_url = f"{base}/messages/"
            if not self.quiet:
                agent_print(f"[MCP] Warning: endpoint discovery timed out for {self.name}, trying {self.message_url}")

        init_result = self._send_request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "uhu", "version": "1.0"},
        })
        self._send_notification("notifications/initialized", {})
        self._initialized = True
        return init_result

    def _sse_reader(self):
        try:
            event_type = None
            for line in self._sse_response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if not self.message_url and not self.quiet:
                    agent_print(f"[MCP] SSE {self.name}: {line[:120]}")
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip()
                    if not data:
                        continue
                    if self.message_url is None and (event_type == "endpoint" or data.startswith("/") or data.startswith("http")):
                        if data.startswith("/"):
                            from urllib.parse import urlparse, urlunparse
                            parsed = urlparse(self.url)
                            self.message_url = urlunparse((parsed.scheme, parsed.netloc, data, "", "", ""))
                        else:
                            self.message_url = data
                        self._endpoint_event.set()
                        event_type = None
                        continue
                    try:
                        parsed = json.loads(data)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        parsed = None
                    if parsed is not None and not self._handle_server_message(parsed):
                        self._response_queue.put(parsed)
                    event_type = None
        except Exception:
            pass

    def list_tools(self):
        result = self._send_request("tools/list", {})
        if isinstance(result, dict):
            return result.get("tools", [])
        return []

    def call_tool(self, tool_name, arguments):
        return self._send_request("tools/call", {"name": tool_name, "arguments": arguments})

    def _send_request(self, method, params):
        request_id = str(uuid.uuid4())
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        try:
            response = self._session.post(self.message_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise MCPConnectionError(f"MCP request failed: {e}")

        try:
            data = response.json()
            if "result" in data:
                return data["result"]
            elif "error" in data:
                error = data["error"]
                raise MCPError(f"MCP error {error.get('code')}: {error.get('message')}")
        except (json.JSONDecodeError, ValueError):
            pass

        try:
            result = self._response_queue.get(timeout=self.timeout)
        except queue.Empty:
            raise MCPConnectionError(
                f"MCP server '{self.name}' did not respond within {self.timeout}s")
        if "result" in result:
            return result["result"]
        elif "error" in result:
            error = result["error"]
            raise MCPError(f"MCP error {error.get('code')}: {error.get('message')}")
        return result

    def _send_notification(self, method, params):
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self._session.post(self.message_url, json=payload, timeout=self.timeout)
        except Exception:
            pass

    def reconnect(self):
        """Re-establish the SSE stream after a connection loss."""
        self.close()
        return self.connect()

    def _handle_server_message(self, data):
        """Gracefully handle server-initiated requests/notifications.

        uhu implements no server→client features (sampling, roots,
        elicitation): pings are answered, any other server request gets a
        method-not-found error so the server can degrade gracefully, and
        notifications are ignored. Returns True when the message was
        server-initiated and must not be treated as a pending response.
        """
        method = data.get("method")
        if not method:
            return False
        req_id = data.get("id")
        if req_id is None:
            return True  # notification — nothing to answer
        if method == "ping":
            response = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        else:
            response = {"jsonrpc": "2.0", "id": req_id, "error": {
                "code": -32601,
                "message": f"Method '{method}' is not supported by the uhu client",
            }}
        if self.message_url:
            try:
                self._session.post(self.message_url, json=response, timeout=self.timeout)
            except Exception:
                pass
        return True

    def close(self):
        if self._session:
            self._session.close()


# ── Streamable HTTP Transport ───────────────────────────────────────────

class StreamableHTTPTransport:
    """Communicate with an MCP server via direct HTTP POST.

    Used by servers like HuggingFace that accept JSON-RPC directly at a single URL.
    """

    def __init__(self, url, name, timeout=120, quiet=False, headers=None):
        self.url = url.rstrip("/")
        self.name = name
        self.timeout = timeout
        self.quiet = quiet
        self.extra_headers = headers or {}
        self._session = None
        self._initialized = False
        self._session_id = None

    def connect(self):
        if not HAS_REQUESTS:
            raise ImportError("requests library is required. Install with: pip install requests")

        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        })
        if self.extra_headers:
            self._session.headers.update(self.extra_headers)

        init_result = self._initialize()
        self._send_notification("notifications/initialized", {})
        self._initialized = True
        return init_result

    def _initialize(self):
        """Send initialize request and capture session ID from response headers."""
        request_id = str(uuid.uuid4())
        payload = {"jsonrpc": "2.0", "id": request_id, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "uhu", "version": "1.0"},
        }}
        try:
            response = self._session.post(self.url, json=payload, timeout=self.timeout)
            if not response.ok:
                body = response.text[:500] if response.text else "(empty)"
                raise MCPConnectionError(f"HTTP {response.status_code} {response.reason} for url: {response.url}\nResponse: {body}")

            # Capture session ID from response header
            session_id = response.headers.get("Mcp-Session-Id")
            if session_id:
                self._session_id = session_id
                self._session.headers["Mcp-Session-Id"] = session_id

            content_type = response.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                return self._parse_sse_response(response.text)

            data = response.json()
            if "result" in data:
                return data["result"]
            elif "error" in data:
                error = data["error"]
                raise MCPError(f"MCP error {error.get('code')}: {error.get('message')}")
            return data
        except requests.exceptions.RequestException as e:
            raise MCPConnectionError(f"MCP request failed: {e}")

    def list_tools(self):
        result = self._send_request("tools/list", {})
        if isinstance(result, dict):
            return result.get("tools", [])
        return []

    def call_tool(self, tool_name, arguments):
        return self._send_request("tools/call", {"name": tool_name, "arguments": arguments})

    def _send_request(self, method, params):
        request_id = str(uuid.uuid4())
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        try:
            response = self._session.post(self.url, json=payload, timeout=self.timeout)
            if not response.ok:
                # Include response body in error for debugging
                body = response.text[:500] if response.text else "(empty)"
                raise MCPConnectionError(f"HTTP {response.status_code} {response.reason} for url: {response.url}\nResponse: {body}")
            content_type = response.headers.get("Content-Type", "")

            if "text/event-stream" in content_type:
                return self._parse_sse_response(response.text)

            data = response.json()
            if "result" in data:
                return data["result"]
            elif "error" in data:
                error = data["error"]
                raise MCPError(f"MCP error {error.get('code')}: {error.get('message')}")
            return data
        except requests.exceptions.RequestException as e:
            raise MCPConnectionError(f"MCP request failed: {e}")

    def _parse_sse_response(self, text):
        result = None
        for line in text.split("\n"):
            if line.startswith("data:"):
                data = line[5:].strip()
                if data:
                    try:
                        parsed = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if "method" in parsed:
                        # Server-initiated request/notification in the stream —
                        # uhu supports no server→client features; skip it and
                        # keep looking for our response.
                        continue
                    if "result" in parsed:
                        result = parsed["result"]
                    elif "error" in parsed:
                        error = parsed["error"]
                        raise MCPError(f"MCP error {error.get('code')}: {error.get('message')}")
        return result or {}

    def _send_notification(self, method, params):
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self._session.post(self.url, json=payload, timeout=self.timeout)
        except Exception:
            pass

    def reconnect(self):
        """Re-initialize the HTTP session (new Mcp-Session-Id is captured)."""
        self.close()
        return self.connect()

    def close(self):
        if self._session:
            self._session.close()


# ── stdio Transport ─────────────────────────────────────────────────────

class StdioTransport:
    """Communicate with an MCP server via subprocess stdio."""

    def __init__(self, command, args=None, env=None, name="", timeout=120, quiet=False):
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.name = name
        self.timeout = timeout
        self.quiet = quiet
        self._process = None
        self._initialized = False
        self._request_id = 0
        self._lock = threading.Lock()

    def _resolve_command(self):
        """Resolve the command via PATH (handles npx → npx.cmd on Windows)."""
        if os.path.sep in self.command or os.path.isabs(self.command):
            return self.command
        return shutil.which(self.command) or self.command

    def connect(self):
        env = os.environ.copy()
        env.update(self.env)
        env["MCP_SERVER"] = self.name

        # No shell=True: with list argv it makes quoting fragile on Windows.
        # Resolve the command via PATH instead; .cmd/.bat shims (npx etc.) run
        # through an explicit `cmd /c`, everything else via CreateProcess with
        # proper list2cmdline quoting.
        resolved = self._resolve_command()
        cmd = [resolved] + self.args
        if os.name == "nt" and os.path.splitext(resolved)[1].lower() in (".cmd", ".bat"):
            cmd = ["cmd", "/c"] + cmd
        try:
            self._process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                shell=False)
        except OSError as e:
            raise MCPConnectionError(
                f"failed to start MCP server '{self.name}': {resolved}: {e}")

        init_result = self._send_request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "uhu", "version": "1.0"},
        })
        self._send_notification("notifications/initialized", {})
        self._initialized = True
        return init_result

    def list_tools(self):
        result = self._send_request("tools/list", {})
        if isinstance(result, dict):
            return result.get("tools", [])
        return []

    def call_tool(self, tool_name, arguments):
        return self._send_request("tools/call", {"name": tool_name, "arguments": arguments})

    def _send_request(self, method, params):
        with self._lock:
            self._request_id += 1
            request_id = self._request_id
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        return self._send_and_receive(payload)

    def _send_notification(self, method, params):
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self._write_line(json.dumps(payload))
        except Exception:
            pass

    def _send_and_receive(self, payload):
        if not self._process or self._process.poll() is not None:
            raise MCPConnectionError(f"MCP server '{self.name}' process is not running")
        self._write_line(json.dumps(payload))
        # Read until the response to OUR request arrives. Server-initiated
        # requests/notifications (sampling, roots, pings, log messages) are
        # answered or ignored inline — uhu supports no server→client features.
        for _ in range(64):
            response_line = self._process.stdout.readline()
            if not response_line:
                stderr = ""
                try:
                    stderr = self._process.stderr.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                raise MCPConnectionError(f"MCP server '{self.name}' closed connection. stderr: {stderr[:500]}")
            try:
                data = json.loads(response_line.decode("utf-8") if isinstance(response_line, bytes) else response_line)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise MCPConnectionError(f"MCP server '{self.name}' returned invalid JSON: {e}")
            if self._handle_server_message(data):
                continue
            if "result" in data:
                return data["result"]
            elif "error" in data:
                error = data["error"]
                raise MCPError(f"MCP error {error.get('code')}: {error.get('message')}")
            return data
        raise MCPConnectionError(
            f"MCP server '{self.name}' sent too many unsolicited messages")

    def _write_line(self, message):
        if self._process and self._process.stdin:
            self._process.stdin.write((message + "\n").encode("utf-8"))
            self._process.stdin.flush()

    def close(self):
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self._process = None

    def reconnect(self):
        """Restart the server process and re-initialize the session."""
        self.close()
        return self.connect()

    def _handle_server_message(self, data):
        """Gracefully handle server-initiated requests/notifications.

        uhu implements no server→client features (sampling, roots,
        elicitation): pings are answered, any other server request gets a
        method-not-found error so the server can degrade gracefully, and
        notifications are ignored. Returns True when the message was
        server-initiated and must not be treated as the pending response.
        """
        method = data.get("method")
        if not method:
            return False
        req_id = data.get("id")
        if req_id is None:
            return True  # notification — nothing to answer
        if method == "ping":
            self._write_response(req_id, result={})
        else:
            self._write_response(req_id, error={
                "code": -32601,
                "message": f"Method '{method}' is not supported by the uhu client",
            })
        return True

    def _write_response(self, req_id, result=None, error=None):
        payload = {"jsonrpc": "2.0", "id": req_id}
        if error is not None:
            payload["error"] = error
        else:
            payload["result"] = result if result is not None else {}
        try:
            self._write_line(json.dumps(payload))
        except Exception:
            pass


# ── MCP Manager ─────────────────────────────────────────────────────────

class MCPManager:
    """Manages connections to MCP servers and registers their tools."""

    def __init__(self, workdir=None, quiet=False):
        self.workdir = workdir
        self.quiet = quiet
        self.transports = []
        self.tools = []

    def load_and_connect(self):
        """Load MCP server configs and connect to each one in parallel."""
        from ._config import load_config
        config = load_config(self.workdir)
        mcp_servers = config.get("mcpServers", {})

        if not mcp_servers:
            return []

        results = {}
        errors = {}
        server_configs = {}

        def _connect_server(server_name, server_config):
            try:
                transport = self._create_transport(server_name, server_config)
                if transport is None:
                    errors[server_name] = "No 'url' or 'command' field"
                    return
                transport.connect()
                tools = transport.list_tools()
                results[server_name] = (transport, tools)
                server_configs[server_name] = server_config
            except Exception as e:
                errors[server_name] = str(e)

        threads = []
        for server_name, server_config in mcp_servers.items():
            if server_config.get("enabled", True) is False:
                if not self.quiet:
                    agent_print(f"[MCP] Skipping {server_name} (disabled)")
                continue
            if not self.quiet:
                agent_print(f"[MCP] Connecting to {server_name}...")
            t = threading.Thread(target=_connect_server, args=(server_name, server_config))
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=60)

        for server_name, (transport, tools) in results.items():
            if not self.quiet:
                agent_print(f"[MCP] Connected to {server_name}")
                agent_print(f"[MCP] Discovered {len(tools)} tool(s) from {server_name}")

            for tool_def in tools:
                original_name = tool_def.get("name", "")
                description = tool_def.get("description", "")
                input_schema = tool_def.get("inputSchema", {})
                clean_server = server_name.removeprefix("mcp-").removeprefix("mcp_")
                prefixed_name = f"mcp_{clean_server.replace('-', '_')}_{original_name.replace('-', '_')}"

                mcp_tool = MCPTool(
                    name=prefixed_name,
                    description=description,
                    input_schema=input_schema,
                    server_name=server_name,
                    transport=transport,
                    auto_approve=server_configs.get(server_name, {}).get("auto_approve", False),
                    original_name=original_name,
                )
                self.tools.append(mcp_tool)

            self.transports.append(transport)

        for server_name, error in errors.items():
            if not self.quiet:
                agent_print(f"[MCP] Failed to connect to {server_name}: {error}")

        return self.tools

    def _resolve_auth(self, name, config):
        """Resolve an auth token for an MCP server (mercury pattern).

        Precedence: auth_token_env (env var NAME) > auth_token (inline, deprecated).
        Returns (token, warning) — token may be None.
        """
        env_name = config.get("auth_token_env")
        if env_name:
            token = os.environ.get(env_name)
            if not token:
                return None, (f"[MCP] {name}: env var '{env_name}' not set "
                              f"(add it to ~/.uhu/.secrets/.env) — server may fail to authenticate")
            return token, None
        token = config.get("auth_token")
        if token:
            return token, (f"[MCP] {name}: inline 'auth_token' is deprecated — "
                           f"use \"auth_token_env\": \"<ENV_VAR_NAME>\" instead")
        return None, None

    def _create_transport(self, name, config):
        """Create the appropriate transport for a server config."""
        if "url" in config:
            url = config["url"]
            auth_token, warn = self._resolve_auth(name, config)
            if warn and not self.quiet:
                agent_print(warn)
            headers = dict(config.get("headers") or {})
            # StreamableHTTP has no auth_token param — inject as Bearer header
            if auth_token and "Authorization" not in headers and not url.rstrip("/").endswith("/sse"):
                headers["Authorization"] = f"Bearer {auth_token}"
                auth_token = None
            if url.rstrip("/").endswith("/sse"):
                return SSETransport(
                    url=config["url"], name=name,
                    timeout=config.get("timeout", 120), quiet=self.quiet,
                    auth_token=auth_token, headers=headers,
                )
            else:
                return StreamableHTTPTransport(
                    url=config["url"], name=name,
                    timeout=config.get("timeout", 120), quiet=self.quiet,
                    headers=headers,
                )
        elif "command" in config:
            return StdioTransport(
                command=config["command"], args=config.get("args", []),
                env=config.get("env", {}), name=name,
                timeout=config.get("timeout", 120), quiet=self.quiet,
            )
        else:
            if not self.quiet:
                agent_print(f"[MCP] Skipping {name}: no 'url' or 'command' field")
            return None

    def close_all(self):
        """Close all MCP server connections."""
        for transport in self.transports:
            try:
                transport.close()
            except Exception:
                pass
        self.transports.clear()
