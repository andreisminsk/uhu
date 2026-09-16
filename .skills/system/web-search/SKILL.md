---
name: web-search
description: Search the web using DuckDuckGo via the ddgs Python package. Bypasses IP-blocked built-in web_search tool.
triggers:
  - search the web
  - web search
  - search online
  - look up
  - find online
  - google
  - search for
  - look up online
  - find on the internet
  - search ddg
  - duckduckgo
---

# Web Search (ddgs)

Search the web using DuckDuckGo via the `ddgs` Python package. Use this when the built-in `web_search` tool is blocked by CAPTCHA or rate limiting.

## When to Use

- When the built-in `web_search` tool returns a CAPTCHA block error
- When you need current pricing, news, or real-time information
- When `web_fetch` fails to retrieve content from a page

## Scripts

- `scripts/search.py` — Runs a DuckDuckGo text search and returns results

## Workflow

1. Run the search script: `python scripts/search.py "your query" --max 5`
2. The script outputs structured results with title, URL, and snippet
3. If you need more detail from a result, use `web_fetch` with the URL
4. Present the findings to the user

## Commands

```bash
# Basic search (default 5 results)
python scripts/search.py "NVIDIA DGX Spark price"

# More results
python scripts/search.py "Mac Studio M4 Ultra review" --max 10

# Search for specific content types
python scripts/search.py "site:ebay.com Mac Studio 384GB" --max 5
```

## Output Format

Present search results in a clean format:

**[Title](URL)**
> Snippet text...

## Guidelines

- Always use `python scripts/search.py` — never call `ddgs` directly in a one-liner (PowerShell quoting issues)
- If the script fails, check that `ddgs` is installed: `pip install ddgs`
- For pricing research, combine search results with `web_fetch` on specific product pages
- For technical documentation, follow the URL to get full content
- The script handles UTF-8 encoding automatically
