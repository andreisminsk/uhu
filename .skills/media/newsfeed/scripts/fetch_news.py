#!/usr/bin/env python3
"""Fetch headlines from curated RSS feeds and output as JSON."""

import argparse
import concurrent.futures
import json
import sys
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime

FEEDS = {
    # Major News Outlets
    "BBC Top Stories":      ("http://feeds.bbci.co.uk/news/rss.xml", "news"),
    "BBC World":            ("http://feeds.bbci.co.uk/news/world/rss.xml", "news"),
    "NYT World":            ("https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "news"),
    "NYT Home Page":        ("https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "news"),
    "The Guardian World":   ("https://www.theguardian.com/world/rss", "news"),
    "The Guardian Intl":    ("https://www.theguardian.com/international/rss", "news"),
    "Al Jazeera":           ("https://www.aljazeera.com/xml/rss/all.xml", "news"),
    "Sky News World":       ("https://feeds.skynews.com/feeds/rss/world.xml", "news"),
    "NPR Top Stories":      ("https://feeds.npr.org/1001/rss.xml", "news"),
    "NPR World":            ("https://feeds.npr.org/1004/rss.xml", "news"),
    "Deutsche Welle":       ("https://rss.dw.com/xml/rss-en-world", "news"),
    "France 24":            ("https://www.france24.com/en/rss", "news"),
    "RFI English":          ("https://www.rfi.fr/en/rss", "news"),

    # Tech News
    "Ars Technica":         ("http://feeds.arstechnica.com/arstechnica/index", "tech"),
    "Wired":                ("https://www.wired.com/feed/rss", "tech"),
    "TechCrunch":           ("https://techcrunch.com/feed/", "tech"),
    "The Verge":            ("https://www.theverge.com/rss/index.xml", "tech"),

    # Business / Finance
    "Financial Times":      ("https://www.ft.com/rss/home", "business"),
    "Bloomberg Markets":    ("https://feeds.bloomberg.com/markets/news.rss", "business"),

    # Science
    "NASA":                 ("https://www.nasa.gov/rss/dyn/breaking_news.rss", "science"),
    "New Scientist":        ("https://www.newscientist.com/feed/home/", "science"),
    "Science Daily":        ("https://www.sciencedaily.com/rss/all.xml", "science"),
}

CATEGORY_EMOJI = {
    "news": "🌍",
    "tech": "💻",
    "business": "💰",
    "science": "🔬",
}


def fetch_feed(name, url, category, limit, timeout):
    """Fetch and parse a single RSS feed."""
    items = []
    try:
        req = Request(url, headers={"User-Agent": "HermesNewsFeed/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()

        # Try feedparser-style parsing via XML
        root = ET.fromstring(data)

        # Handle RSS 2.0
        for channel in root.iter("channel"):
            for item in channel.iter("item"):
                title = None
                link = None
                desc = None
                pub_date = None
                for child in item:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if tag == "title":
                        title = child.text
                    elif tag == "link":
                        link = child.text
                    elif tag == "description":
                        desc = child.text
                    elif tag in ("pubDate", "published", "updated", "dc:date"):
                        pub_date = child.text
                if title:
                    items.append({
                        "title": title.strip(),
                        "link": link.strip() if link else None,
                        "description": (desc or "").strip()[:200] if desc else None,
                        "pub_date": pub_date.strip() if pub_date else None,
                        "source": name,
                    })

        # Handle Atom feeds (feed > entry)
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = None
            link = None
            desc = None
            pub_date = None
            for child in entry:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == "title":
                    title = child.text
                elif tag == "link":
                    link = child.attrib.get("href", child.text)
                elif tag in ("summary", "content"):
                    desc = child.text
                elif tag in ("published", "updated"):
                    pub_date = child.text
            if title:
                items.append({
                    "title": title.strip(),
                    "link": link.strip() if link else None,
                    "description": (desc or "").strip()[:200] if desc else None,
                    "pub_date": pub_date.strip() if pub_date else None,
                    "source": name,
                })

    except (HTTPError, URLError, ET.ParseError, TimeoutError, Exception) as e:
        return category, name, [], str(e)

    return category, name, items[:limit], None


def main():
    parser = argparse.ArgumentParser(description="Fetch RSS news headlines")
    parser.add_argument("--category", choices=["news", "tech", "business", "science"],
                        help="Filter by category")
    parser.add_argument("--limit", type=int, default=5,
                        help="Max items per feed (default: 5)")
    parser.add_argument("--timeout", type=int, default=10,
                        help="Request timeout in seconds (default: 10)")
    parser.add_argument("--workers", type=int, default=8,
                        help="Concurrent fetch workers (default: 8)")
    args = parser.parse_args()

    feeds_to_fetch = {
        name: (url, cat) for name, (url, cat) in FEEDS.items()
        if not args.category or cat == args.category
    }

    results = {}
    errors = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(fetch_feed, name, url, cat, args.limit, args.timeout): name
            for name, (url, cat) in feeds_to_fetch.items()
        }
        for future in concurrent.futures.as_completed(futures):
            cat, name, items, err = future.result()
            if err:
                errors[name] = err
            else:
                results.setdefault(cat, []).extend(items)

    output = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "categories": {},
        "errors": errors,
    }

    for cat in ["news", "tech", "business", "science"]:
        if cat in results:
            # Sort by source name for consistent output
            items = sorted(results[cat], key=lambda x: x.get("pub_date", "") or "", reverse=True)
            output["categories"][cat] = {
                "emoji": CATEGORY_EMOJI.get(cat, ""),
                "count": len(items),
                "headlines": items,
            }

    sys.stdout.reconfigure(encoding='utf-8')
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()