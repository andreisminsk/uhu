---
name: travel-plans
version: 2.0
description: Append travel plan entries with images to TRAVELPLANS.md, triggered by travel-related keywords or links.
triggers:
  - travel
  - travel plan
  - travel plans
  - add travel
---

# Travel Plans

Append travel plan entries to `TRAVELPLANS.md` with rich annotations and downloaded images.

## Steps

1. **Extract the place name** from the user's message
2. **Run the travel plan script** to search, annotate, and download:
   
   ```
   python scripts/add_travel_plan.py "Place Name" --date YYYY-MM-DD
   ```
   
   For a custom search query (if the place name is ambiguous):
   
   ```
   python scripts/add_travel_plan.py "Palace in Samegrelo" --search "Dadiani Palace Zugdidi Georgia"
   ```
3. **Review the output** — the script prints the annotation and image path
4. **Present the result** to the user in a clear format

## Scripts

- `scripts/add_travel_plan.py` — Searches DuckDuckGo, fetches Wikipedia summary, downloads thumbnail, appends to TRAVELPLANS.md

> All script paths are relative to this SKILL.md's directory.
> At runtime, they are automatically resolved to workdir-relative paths.

## What the script does

- Searches DuckDuckGo for the place
- Fetches a summary from Wikipedia API
- Downloads a thumbnail image from Wikipedia/Wikimedia
- Appends a formatted entry to TRAVELPLANS.md

## Important

- ALWAYS use the script — do NOT manually browse Wikipedia or download images
- The script uses Wikipedia's REST API (no browser needed, no 403 errors)
- If the script fails, report the error to the user
- Do NOT use curl for image downloads (Wikimedia blocks it)


