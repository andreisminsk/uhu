---
name: weather
version: 1.3
description: Weather forecast for any city or coordinates via wttr.in
triggers:
  - weather
  - forecast
  - temperature
  - "what's the weather"
  - "how's the weather"
---

# Weather Skill

Get current weather and forecast for any city or coordinates.

## Usage

When the user asks about weather (in any language), extract the city name or coordinates.

## Steps

1. **Extract location** from the user's message:
   - City name (e.g., "Batumi", "Minsk", "Lisbon")
   - Coordinates as lat,lon (e.g., "41.6,41.6")
   - If no location given, ask the user

2. **Run the weather script** to fetch and format the forecast:
   ```
   python scripts/fetch_weather.py "Batumi" --forecast
   ```
   For multi-day forecast:
   ```
   python scripts/fetch_weather.py "Batumi" --forecast --days 3
   ```

3. **Present the result** to the user in a clear, readable format.
   The script output is already formatted — you can present it directly or add a brief summary.

## Scripts

- `scripts/fetch_weather.py` — Fetches and formats weather data from wttr.in API

> All script paths are relative to this SKILL.md's directory.
> At runtime, they are automatically resolved to workdir-relative paths.

## Important

- ALWAYS use the script — do NOT use curl, http_request, or any other method to fetch weather data
- The script handles all API calls, JSON parsing, and formatting
- It works cross-platform (no curl dependency)
- If the script fails, report the error to the user
