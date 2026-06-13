---
name: newsfeed
triggers:
  - read news
  - news
  - headlines
  - what's happening
  - current events
  - news feed
  - latest news
description: Fetch and summarize news from RSS feeds. Triggered by "read news" or semantically similar phrases.
---

# News Feed

Fetch headlines from curated RSS feeds, deduplicate, and present a concise summary grouped by category.

## Scripts

- `scripts/fetch_news.py` — Fetches headlines from RSS feeds, outputs JSON
- `scripts/format_news.py` — Formats JSON output into readable summary

> All script paths are relative to this SKILL.md's directory.
> At runtime, they are automatically resolved to workdir-relative paths.

## Activation

Triggered when user says "read news" or any semantically similar phrase (headlines, latest news, current events, what's happening, etc.).

## Feeds

```python
FEEDS = {
    # Major News Outlets
    "BBC Top Stories":      "http://feeds.bbci.co.uk/news/rss.xml",
    "BBC World":            "http://feeds.bbci.co.uk/news/world/rss.xml",
    "NYT World":            "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "NYT Home Page":        "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "The Guardian World":   "https://www.theguardian.com/world/rss",
    "The Guardian Intl":    "https://www.theguardian.com/international/rss",
    "Al Jazeera":           "https://www.aljazeera.com/xml/rss/all.xml",
    "Sky News World":       "https://feeds.skynews.com/feeds/rss/world.xml",
    "NPR Top Stories":      "https://feeds.npr.org/1001/rss.xml",
    "NPR World":            "https://feeds.npr.org/1004/rss.xml",
    "Deutsche Welle":       "https://rss.dw.com/xml/rss-en-world",
    "France 24":            "https://www.france24.com/en/rss",
    "RFI English":          "https://www.rfi.fr/en/rss",

    # Tech News
    "Ars Technica":         "http://feeds.arstechnica.com/arstechnica/index",
    "Wired":                "https://www.wired.com/feed/rss",
    "TechCrunch":           "https://techcrunch.com/feed/",
    "The Verge":            "https://www.theverge.com/rss/index.xml",

    # Business / Finance
    "Financial Times":      "https://www.ft.com/rss/home",
    "Bloomberg Markets":    "https://feeds.bloomberg.com/markets/news.rss",

    # Science
    "NASA":                 "https://www.nasa.gov/rss/dyn/breaking_news.rss",
    "New Scientist":        "https://www.newscientist.com/feed/home/",
    "Science Daily":        "https://www.sciencedaily.com/rss/all.xml",
}
```

## Workflow

1. Run the fetch script: `python scripts/fetch_news.py`
   - Pass optional args: `--category <name>` to filter by category (news, tech, business, science)
   - Pass `--limit N` per feed (default 5)
   - Pass `--timeout N` seconds per feed request (default 10)
2. The script outputs JSON with headlines grouped by category.
3. To format the JSON into a readable summary, pipe or post-process with:
   `python scripts/format_news.py`
   Or run: `python scripts/fetch_news.py | python scripts/format_news.py`
4. Summarize the top stories concisely — group by category, highlight the most significant/overlapping stories across sources.
5. Present results in a compact format: bold headline, source tag, brief one-line summary if available.

## Output Format

Present like this (always include article link):

**🌍 World News**
• Headline text — *BBC, NPR* [link](url)
• Another headline — *Al Jazeera* [→](url)
• …

**💻 Tech**
• Headline — *Ars Technica* [→](url)
• …

**💰 Business**
• Headline — *FT* [→](url)

**🔬 Science**
• Headline — *NASA* [→](url)

Use **[→](url)** (bold arrow) format. The link is mandatory, never omit it.

## Customization

- User may ask for a specific category ("tech news", "science news") — filter accordingly.
- User may ask to read a specific story deeper — follow the link and summarize.
- User may ask to add/remove feeds — update the FEEDS dict in the script and SKILL.md.

## Pitfalls

- 
- Some RSS feeds may be blocked or return 403/429. The script handles errors gracefully per-feed.
- Feed XML structures vary — the script uses feedparser first, falls back to xml.etree.
- Don't try to fetch all feeds in a single curl — use the Python script for concurrent fetching.
- **Telegram output limit**: Full news summaries with links can exceed Telegram's ~4096 char limit. When generating long summaries (especially translated ones), check total length and truncate less important stories or split into multiple messages if needed. The 4-category format with ~5 stories each plus links is near the limit.
- **Translation**: When user asks for news in a specific language (e.g. "read news and translate to Russian"), translate the summaries but keep source names in English. Use the same category headers translated (🌍 Мировые новости, 💻 Технологии, 💰 Бизнес, 🔬 Наука).
