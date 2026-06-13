"""web_fetch tool — fetch text content from a URL, with optional LLM summarization."""

import re
import urllib.error
import urllib.request

from ..constants import MAX_WEB_FETCH_CHARS
from ._config import get_config
from .llm_query import llm_query


class WebFetchTool:
    name = "web_fetch"
    description = "Fetch the text content of a web page, with optional LLM summarization"
    system_prompt = (
        "## web_fetch\n"
        "Fetches the text content of a web page. Use this to retrieve information from URLs.\n"
        "Parameters (JSON object):\n"
        "- url (string, required): The URL to fetch\n"
        "- max_length (integer, optional, default 3000): Maximum characters to return\n"
        "- summarize (boolean, optional): If true, use LLM to summarize the page content\n"
        "\n"
        "IMPORTANT: Web content is converted to clean plain text (no HTML). Results are\n"
        "truncated to conserve context. Use a larger max_length only if you need more detail.\n"
        "When summarize=true, the page is first scraped fully, then distilled by an LLM\n"
        "into a concise summary within max_length characters — preserving key facts, numbers,\n"
        "specs, and benchmarks while removing boilerplate."
    )

    def execute(self, params, workdir=None):
        config = get_config()
        wf_cfg = config.get("web_fetch", {})
        url = params.get("url")
        if not url:
            return "[Error: 'url' parameter is required]"
        max_length = params.get("max_length", wf_cfg.get("max_chars", MAX_WEB_FETCH_CHARS))
        summarize = params.get("summarize", wf_cfg.get("llm_summarize", True))
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if not any(t in content_type.lower() for t in ("text/", "json", "xml", "html")):
                    return f"[Error: Unsupported content type: {content_type}]"
                # Read more data if summarizing (we'll compress it later)
                read_limit = max_length * 5 if summarize else max_length + 1
                data = resp.read(read_limit).decode("utf-8", errors="replace")
                if "html" in content_type.lower():
                    data = _html_to_text(data)
                if summarize:
                    data = _summarize_with_llm(data, url, max_length)
                if len(data) > max_length:
                    data = data[:max_length] + "\n[... truncated]"
                return data
        except urllib.error.HTTPError as e:
            return f"[HTTP Error {e.code}: {e.reason}]"
        except urllib.error.URLError as e:
            return f"[URL Error: {e.reason}]"
        except Exception as e:
            return f"[Error: {e}]"


def _html_to_text(html):
    """Convert HTML to clean plain text.

    Uses BeautifulSoup if available for best results (pip install beautifulsoup4).
    Falls back to a stdlib HTMLParser-based extractor that produces much cleaner
    output than simple regex stripping — it properly handles block elements,
    skips nav/footer/aside/script/style, and decodes HTML entities.
    """
    # Try BeautifulSoup first (pip install beautifulsoup4)
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        # Remove non-content elements entirely
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside',
                         'noscript', 'iframe', 'form', 'svg']):
            tag.decompose()
        text = soup.get_text(separator='\n', strip=True)
        # Collapse excessive blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
    except ImportError:
        pass

    # Fallback: stdlib HTMLParser — much better than regex stripping
    return _html_to_text_stdlib(html)


def _html_to_text_stdlib(html):
    """Fallback HTML-to-text using stdlib html.parser."""
    from html.parser import HTMLParser
    from html import unescape

    SKIP_TAGS = frozenset([
        'script', 'style', 'nav', 'footer', 'header', 'aside',
        'noscript', 'iframe', 'form', 'svg',
    ])
    BLOCK_TAGS = frozenset([
        'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'li', 'tr', 'br', 'hr', 'blockquote', 'section',
        'article', 'main', 'figure', 'figcaption',
        'details', 'summary', 'dd', 'dt', 'td', 'th',
    ])

    class _TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self.skip_depth = 0

        def handle_starttag(self, tag, attrs):
            tag = tag.lower()
            if tag in SKIP_TAGS:
                self.skip_depth += 1
            if tag in BLOCK_TAGS and self.skip_depth == 0:
                self.parts.append('\n')

        def handle_endtag(self, tag):
            tag = tag.lower()
            if tag in SKIP_TAGS:
                self.skip_depth = max(0, self.skip_depth - 1)
            if tag in BLOCK_TAGS and self.skip_depth == 0:
                self.parts.append('\n')

        def handle_data(self, data):
            if self.skip_depth > 0:
                return
            self.parts.append(data)

    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass

    text = ''.join(parser.parts)
    text = unescape(text)
    # Clean up whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' *\n[ \t]*\n[ \t]*', '\n\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _summarize_with_llm(text: str, url: str, max_length: int) -> str:
    """Use an out-of-context LLM call to summarize page content."""
    config = get_config()
    wf_cfg = config.get("web_fetch", {})
    llm_model = wf_cfg.get("llm_model", "kimi-k2.5:cloud")
    prompt = (
        f"You are a web page summarizer. Summarize the following web page content into a "
        f"concise, information-dense summary of at most {max_length} characters.\n\n"
        f"Preserve all key facts: names, numbers, dates, specs, benchmarks, features, "
        f"comparisons, prices, etc. Remove boilerplate, navigation, ads, and repetition.\n\n"
        f"URL: {url}\n\n"
        f"PAGE CONTENT:\n{text}\n\n"
        f"CONCISE SUMMARY (max {max_length} chars):"
    )
    try:
        summary = llm_query(
            prompt=prompt,
            model=llm_model,
            temperature=0.3,
            timeout=120,
        )
        if len(summary) > max_length:
            summary = summary[:max_length - 3] + "..."
        return summary
    except Exception:
        # Fall back to raw text if LLM fails
        return text
