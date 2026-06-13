"""web_search tool — search the web using DuckDuckGo."""

import re
import urllib.parse
import urllib.request


class WebSearchTool:
    name = "web_search"
    description = "Search the web using DuckDuckGo"
    system_prompt = (
        "## web_search\n"
        "Searches the web using DuckDuckGo. Returns a list of results with titles, URLs, and snippets.\n"
        "Parameters (JSON object):\n"
        "- query (string, required): The search query\n"
        "- num_results (integer, optional, default 5): Number of results to return (max 10)"
    )

    def execute(self, params, workdir=None):
        query = params.get("query")
        if not query:
            return "[Error: 'query' parameter is required]"
        num_results = min(params.get("num_results", 5), 10)
        try:
            url = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": query})
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            results = _parse_ddg_lite(html, num_results)
            if not results:
                return f"[No results found for: {query}]"
            parts = [f"Search results for: {query}\n"]
            for i, r in enumerate(results, 1):
                parts.append(f"{i}. {r['title']}\n   URL: {r['url']}\n   {r['snippet']}\n")
            return "\n".join(parts)
        except Exception as e:
            return f"[Search error: {e}]"


def _parse_ddg_lite(html, max_results):
    """Parse DuckDuckGo Lite HTML results."""
    results = []
    # Match full <a> tags with class='result-link' (single or double quotes)
    link_pattern = re.compile(
        r"<a\s[^>]*class=['\"]result-link['\"][^>]*>(.*?)</a>"
        r"|<a\s[^>]*href=['\"]([^'\"]*)['\"][^>]*class=['\"]result-link['\"][^>]*>(.*?)</a>",
        re.DOTALL
    )
    snippet_pattern = re.compile(r"<td[^>]*class=['\"]result-snippet['\"][^>]*>(.*?)</td>", re.DOTALL)

    snippets = snippet_pattern.findall(html)

    for i, match in enumerate(link_pattern.finditer(html)):
        if i >= max_results:
            break
        # Group layout depends on which alternative matched
        # Alt1: class before href -> group(1)=title, no href captured
        # Alt2: href before class -> group(2)=url, group(3)=title
        # Since DDG Lite puts href before class, alt2 is the common case
        title_html = match.group(3) or match.group(1) or ""
        url_raw = match.group(2) or ""

        # If url_raw is empty (alt1), extract href from the full tag
        if not url_raw:
            href_match = re.search(r"href=['\"]([^'\"]*)['\"]", match.group(0))
            url_raw = href_match.group(1) if href_match else ""

        title = re.sub(r'<[^>]+>', '', title_html).strip()
        snippet = snippets[i].strip() if i < len(snippets) else ""
        snippet = re.sub(r'<[^>]+>', '', snippet).strip()

        # Extract actual URL from DDG redirect (uddg parameter)
        uddg_match = re.search(r'uddg=([^&]+)', url_raw)
        if uddg_match:
            url = urllib.parse.unquote(uddg_match.group(1))
        elif url_raw.startswith("//"):
            url = "https:" + url_raw
        else:
            url = url_raw

        results.append({"title": title, "url": url, "snippet": snippet})

    return results
