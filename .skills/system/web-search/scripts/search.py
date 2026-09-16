"""
Web search using DuckDuckGo (ddgs package).
Usage: python search.py "your query" [--max N]
"""
import sys
import json
import argparse

sys.stdout.reconfigure(encoding='utf-8')


def search(query: str, max_results: int = 5) -> list[dict]:
    """Search DuckDuckGo and return results."""
    from ddgs import DDGS
    
    results = DDGS().text(query, max_results=max_results)
    return results


def main():
    parser = argparse.ArgumentParser(description="Search the web using DuckDuckGo")
    parser.add_argument("query", nargs="+", help="Search query (one or more words)")
    parser.add_argument("--max", type=int, default=5, help="Maximum number of results (default: 5)")
    args = parser.parse_args()
    args.query = " ".join(args.query)

    try:
        results = search(args.query, args.max)
        if not results:
            print("No results found.")
            return

        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            href = r.get("href", "No URL")
            body = r.get("body", "")
            print(f"--- Result {i} ---")
            print(f"Title: {title}")
            print(f"URL: {href}")
            print(f"Snippet: {body[:300]}")
            print()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
