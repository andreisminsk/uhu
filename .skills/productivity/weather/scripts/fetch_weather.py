#!/usr/bin/env python3
"""Fetch weather forecast from wttr.in and format as readable summary."""

import json
import sys
import urllib.request

# Fix Windows console encoding for emoji
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def fetch_weather(location, forecast=False):
    """Fetch weather data from wttr.in.
    
    Returns parsed JSON dict.
    """
    url = f"https://wttr.in/{location}?format=j1"
    headers = {"User-Agent": "curl/7.68.0", "Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def format_current(data):
    """Format current conditions as readable text."""
    c = data["current_condition"][0]
    area = data["nearest_area"][0]
    city = area["areaName"][0]["value"]
    country = area["country"][0]["value"]
    desc = c["weatherDesc"][0]["value"].strip()
    lines = [
        f"{city}, {country}",
        f"  Conditions: {desc}",
        f"  Temperature: {c['temp_C']}C / {c['temp_F']}F (feels {c['FeelsLikeC']}C / {c['FeelsLikeF']}F)",
        f"  Wind: {c['windspeedKmph']} km/h {c['winddir16Point']}",
        f"  Humidity: {c['humidity']}%",
        f"  Precipitation: {c['precipMM']} mm",
        f"  Pressure: {c['pressure']} hPa",
        f"  Visibility: {c['visibility']} km",
        f"  UV Index: {c['uvIndex']}",
    ]
    return "\n".join(lines)


def format_forecast(data, day_offset=1):
    """Format forecast for a specific day (0=today, 1=tomorrow, etc.)."""
    days = data.get("weather", [])
    if day_offset >= len(days):
        return f"Forecast not available for day offset {day_offset}"
    
    w = days[day_offset]
    astro = w["astronomy"][0]
    lines = [
        f"{w['date']} -- {'Today' if day_offset == 0 else 'Tomorrow' if day_offset == 1 else f'Day +{day_offset}'}",
        f"  High: {w['maxtempC']}C / {w['maxtempF']}F  |  Low: {w['mintempC']}C / {w['mintempF']}F  |  Avg: {w['avgtempC']}C",
        f"  Sun: {astro['sunrise']} - {astro['sunset']} ({w['sunHour']}h sun, UV {w['uvIndex']})",
        f"  Moon: {astro['moon_phase']} ({astro['moon_illumination']}% illuminated)",
        "",
        "  Hourly:",
    ]
    
    for h in w["hourly"]:
        time_str = h["time"].zfill(4)
        hour = f"{time_str[:2]}:{time_str[2:]}"
        desc = h["weatherDesc"][0]["value"].strip()
        rain = h.get("chanceofrain", "0")
        lines.append(
            f"    {hour}  {h['tempC']}C (feels {h['FeelsLikeC']}C)  {desc}  "
            f"rain:{rain}%  wind:{h['windspeedKmph']}km/h {h['winddir16Point']}  hum:{h['humidity']}%"
        )
    
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python fetch_weather.py <location> [--forecast] [--days N]")
        print("  location: city name or coordinates (e.g., 'Batumi', 'Minsk,Belarus')")
        print("  --forecast: show forecast (default: tomorrow)")
        print("  --days N: show N days of forecast (1-3, default: 1)")
        sys.exit(1)
    
    location = sys.argv[1]
    forecast = "--forecast" in sys.argv or "-f" in sys.argv
    days = 1
    for i, arg in enumerate(sys.argv):
        if arg == "--days" and i + 1 < len(sys.argv):
            days = int(sys.argv[i + 1])
    
    try:
        data = fetch_weather(location)
    except Exception as e:
        print(f"Error fetching weather: {e}")
        sys.exit(1)
    
    print(format_current(data))
    
    if forecast:
        print()
        start_day = 1 if days == 1 else 0
        for d in range(start_day, min(start_day + days, len(data.get("weather", [])))):
            print(format_forecast(data, day_offset=d))
            print()


if __name__ == "__main__":
    main()
