"""google_search tool — search the web using Google Custom Search API."""

import json
import os
import urllib.parse
import urllib.request

_GOOGLE_DEPS_ERROR = (
    "Google Search dependencies not installed. "
    "Run: pip install google-api-python-client google-auth"
)


def _get_search_service(api_key, cx):
    """Build and return an authenticated Google Custom Search service object."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        # Custom Search API uses API key auth, not service account
        service = build("customsearch", "v1", developerKey=api_key)
        return service, None
    except ImportError:
        return None, _GOOGLE_DEPS_ERROR
    except Exception as e:
        return None, f"[Error: Failed to initialize Google Search: {e}]"


class GoogleSearchTool:
    name = "google_search"
    description = (
        "Search the web using Google Custom Search API. "
        "Parameters: {\"query\": \"search terms\", \"num_results\": 5}"
    )
    system_prompt = (
        "## google_search\n"
        "Searches the web using Google Custom Search API. Returns a list of results with titles, URLs, and snippets.\n"
        "Parameters (JSON object):\n"
        "- query (string, required): The search query\n"
        "- num_results (integer, optional, default 5): Number of results to return (max 10)"
    )

    def execute(self, params, workdir=None):
        from ._config import load_config, DEFAULT_CONFIG

        # Load config
        config = load_config(workdir)
        search_config = config.get("tools", {}).get("google_search", DEFAULT_CONFIG["tools"].get("google_search", {}))
        api_key = search_config.get("api_key", "")
        cx = search_config.get("cx", "")

        if not api_key or not cx:
            return (
                "[Error: Google Search not configured. "
                "Add 'google_search' with 'api_key' and 'cx' to .ollama_agent.json under tools. "
                "Get your API key from https://console.cloud.google.com/apis/credentials "
                "and create a Programmable Search Engine at https://programmablesearchengine.google.com/]"
            )

        query = params.get("query")
        if not query:
            return "[Error: 'query' parameter is required]"
        num_results = min(params.get("num_results", 5), 10)

        # Try google-api-python-client first, fall back to urllib
        try:
            from googleapiclient.discovery import build
            service = build("customsearch", "v1", developerKey=api_key)
            result = service.cse().list(
                q=query,
                cx=cx,
                num=num_results
            ).execute()

            items = result.get("items", [])
            if not items:
                return f"[No results found for: {query}]"

            parts = [f"Search results for: {query}\n"]
            for i, item in enumerate(items, 1):
                title = item.get("title", "")
                url = item.get("link", "")
                snippet = item.get("snippet", "")
                parts.append(f"{i}. {title}\n   URL: {url}\n   {snippet}\n")
            return "\n".join(parts)

        except ImportError:
            # Fallback: use urllib with the REST API directly
            return self._search_urllib(api_key, cx, query, num_results)
        except Exception as e:
            error_str = str(e)
            if "403" in error_str:
                return "[Error: Google Search API returned 403 Forbidden. Check your API key and that the Custom Search API is enabled in GCP.]"
            if "429" in error_str:
                return "[Error: Google Search API quota exceeded. The free tier allows 100 queries/day.]"
            return f"[Search error: {e}]"

    def _search_urllib(self, api_key, cx, query, num_results):
        """Fallback search using urllib (no google-api-python-client needed)."""
        try:
            params = urllib.parse.urlencode({
                "key": api_key,
                "cx": cx,
                "q": query,
                "num": num_results
            })
            url = f"https://www.googleapis.com/customsearch/v1?{params}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "ollama-agent/1.0"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            items = data.get("items", [])
            if not items:
                return f"[No results found for: {query}]"

            parts = [f"Search results for: {query}\n"]
            for i, item in enumerate(items, 1):
                title = item.get("title", "")
                url = item.get("link", "")
                snippet = item.get("snippet", "")
                parts.append(f"{i}. {title}\n   URL: {url}\n   {snippet}\n")
            return "\n".join(parts)
        except urllib.error.HTTPError as e:
            if e.code == 403:
                return "[Error: Google Search API returned 403 Forbidden. Check your API key and that the Custom Search API is enabled in GCP.]"
            if e.code == 429:
                return "[Error: Google Search API quota exceeded. The free tier allows 100 queries/day.]"
            return f"[Search error: HTTP {e.code} — {e.read().decode('utf-8', errors='replace')[:200]}]"
        except Exception as e:
            return f"[Search error: {e}]"
