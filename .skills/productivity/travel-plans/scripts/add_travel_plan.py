#!/usr/bin/env python3
"""Add a travel plan entry to TRAVELPLANS.md with annotation and image.

Usage:
    python add_travel_plan.py "Dadiani Palace in Zugdidi" --date 2026-06-13
    python add_travel_plan.py "Palace in Samegrelo" --date 2026-06-13 --search "Dadiani Palace Zugdidi"

The script:
1. Searches for the place using DuckDuckGo
2. Fetches a summary from Wikipedia
3. Downloads an image from Wikimedia Commons
4. Appends a formatted entry to TRAVELPLANS.md
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.parse
from datetime import datetime


def search_place(query):
    """Search DuckDuckGo for a place and return top results."""
    url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1"
    req = urllib.request.Request(url, headers={"User-Agent": "uhu-travel/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    
    results = []
    # Abstract
    if data.get("AbstractText"):
        results.append({
            "title": data.get("AbstractTitle", ""),
            "text": data["AbstractText"],
            "url": data.get("AbstractURL", ""),
            "source": data.get("AbstractSource", ""),
        })
    # Related topics
    for topic in (data.get("RelatedTopics") or []):
        if isinstance(topic, dict) and topic.get("Text"):
            results.append({
                "title": topic.get("Text", "")[:80],
                "text": topic.get("Text", ""),
                "url": topic.get("FirstURL", ""),
                "source": "",
            })
    return results


def fetch_wikipedia_summary(title):
    """Fetch a summary from Wikipedia."""
    # Try English Wikipedia API
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
    req = urllib.request.Request(url, headers={"User-Agent": "uhu-travel/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {
            "title": data.get("title", ""),
            "extract": data.get("extract", ""),
            "thumbnail": data.get("thumbnail", {}).get("source", ""),
            "page_url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        }
    except Exception:
        return None


def download_image(url, filepath):
    """Download an image to a local file."""
    req = urllib.request.Request(url, headers={"User-Agent": "uhu-travel/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        with open(filepath, "wb") as f:
            f.write(resp.read())
    return filepath


def slugify(text):
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text[:50]


def main():
    parser = argparse.ArgumentParser(description="Add a travel plan entry")
    parser.add_argument("place", help="Place name or description")
    parser.add_argument("--date", help="Date in YYYY-MM-DD format (default: today)")
    parser.add_argument("--search", help="Custom search query (default: place name)")
    parser.add_argument("--file", default="TRAVELPLANS.md", help="Target file (default: TRAVELPLANS.md)")
    parser.add_argument("--image-dir", default="travel-images", help="Image directory (default: travel-images)")
    args = parser.parse_args()
    
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    search_query = args.search or args.place
    slug = slugify(args.place)
    
    print(f"Searching for: {search_query}")
    
    # Step 1: Search for the place
    results = search_place(search_query)
    annotation = ""
    image_url = ""
    wiki_title = ""
    
    if results:
        annotation = results[0].get("text", "")
        print(f"Found: {results[0].get('title', 'unknown')}")
    
    # Step 2: Try Wikipedia for a better summary and image
    # Extract likely Wikipedia title from search results
    for r in results:
        url = r.get("url", "")
        if "wikipedia.org" in url:
            wiki_title = url.split("/")[-1].replace("_", " ")
            break
    
    if not wiki_title and results:
        # Try the place name as a Wikipedia title
        wiki_title = args.place
    
    if wiki_title:
        print(f"Fetching Wikipedia summary: {wiki_title}")
        wiki_data = fetch_wikipedia_summary(wiki_title)
        if wiki_data and wiki_data.get("extract"):
            annotation = wiki_data["extract"]
            image_url = wiki_data.get("thumbnail", "")
            print(f"Got Wikipedia summary ({len(annotation)} chars)")
            if image_url:
                print(f"Found image: {image_url[:80]}...")
    
    if not annotation:
        annotation = f"Travel destination: {args.place}"
        print("No detailed annotation found, using placeholder.")
    
    # Step 3: Download image
    image_path = ""
    if image_url:
        img_dir = os.path.join(args.image_dir, f"{date}-{slug}")
        os.makedirs(img_dir, exist_ok=True)
        ext = image_url.rsplit(".", 1)[-1].split("?")[0]
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            ext = "jpg"
        img_file = os.path.join(img_dir, f"{slug}.{ext}")
        try:
            download_image(image_url, img_file)
            image_path = f"{args.image_dir}/{date}-{slug}/{slug}.{ext}"
            print(f"Downloaded image: {image_path}")
        except Exception as e:
            print(f"Could not download image: {e}")
            image_path = ""
    
    # Step 4: Append entry to TRAVELPLANS.md
    time_str = datetime.now().strftime("%H:%M")
    entry = f"\n## {date} {time_str}\n{args.place}\n\n"
    entry += f"**Annotation:** {annotation}\n"
    if image_path:
        entry += f"\n![{args.place}]({image_path})\n"
    
    with open(args.file, "a", encoding="utf-8") as f:
        f.write(entry)
    
    print(f"\nEntry added to {args.file}")
    print(f"---")
    print(entry.strip())


if __name__ == "__main__":
    main()
