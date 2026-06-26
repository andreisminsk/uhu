"""Weather tool — fetch weather forecasts using wttr.in JSON API."""

import json
import urllib.error
import urllib.parse
import urllib.request

from ..constants import MAX_OBSERVATION_CHARS

_WTTR_DOMAINS = ["wttr.in", "wttr.is"]


def _fetch_json(location, params_str, timeout=15):
    """Try wttr.in domains in order, return parsed JSON or raise."""
    errors = []
    for domain in _WTTR_DOMAINS:
        url = f"https://{domain}/{urllib.parse.quote(location)}?format=j1"
        if params_str:
            url += "&" + params_str
        req = urllib.request.Request(url, headers={
            "User-Agent": "curl/7.88.1",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read().decode("utf-8", errors="replace")
                return json.loads(data)
        except Exception as e:
            errors.append(f"{domain}: {e}")
            continue
    raise RuntimeError("; ".join(errors))


def _format_current(cc):
    """Format current_condition entry into a readable string."""
    desc = cc.get("weatherDesc", [{}])[0].get("value", "?")
    temp_c = cc.get("temp_C", "?")
    temp_f = cc.get("temp_F", "?")
    feels_c = cc.get("FeelsLikeC", "?")
    feels_f = cc.get("FeelsLikeF", "?")
    humidity = cc.get("humidity", "?")
    wind_kmph = cc.get("windspeedKmph", "?")
    wind_dir = cc.get("winddir16Point", "?")
    visibility = cc.get("visibility", "?")
    pressure = cc.get("pressure", "?")
    uv = cc.get("uvIndex", "?")
    precip = cc.get("precipMM", "?")
    cloud = cc.get("cloudcover", "?")
    return (
        f"  {desc}\n"
        f"  Temperature: {temp_c}°C ({temp_f}°F)\n"
        f"  Feels like: {feels_c}°C ({feels_f}°F)\n"
        f"  Humidity: {humidity}%\n"
        f"  Wind: {wind_kmph} km/h {wind_dir}\n"
        f"  Visibility: {visibility} km\n"
        f"  Pressure: {pressure} hPa\n"
        f"  UV index: {uv}\n"
        f"  Precipitation: {precip} mm\n"
        f"  Cloud cover: {cloud}%"
    )


def _format_forecast(day):
    """Format a weather forecast day entry."""
    date = day.get("date", "?")
    max_c = day.get("maxtempC", "?")
    min_c = day.get("mintempC", "?")
    avg_c = day.get("avgtempC", "?")
    sun_hours = day.get("sunHour", "?")
    uv = day.get("uvIndex", "?")
    desc = day.get("hourly", [{}])[0].get("weatherDesc", [{}])[0].get("value", "?")
    lines = [
        f"  {date}: {desc}",
        f"    High: {max_c}°C  Low: {min_c}°C  Avg: {avg_c}°C",
        f"    Sun: {sun_hours}h  UV: {uv}",
    ]
    # Add hourly details (every 3 hours)
    for h in day.get("hourly", []):
        time_str = h.get("time", "?").zfill(4)
        h_desc = h.get("weatherDesc", [{}])[0].get("value", "?")
        h_temp = h.get("tempC", "?")
        h_feels = h.get("FeelsLikeC", "?")
        h_rain = h.get("chanceofrain", "?")
        h_snow = h.get("chanceofsnow", "?")
        h_wind = h.get("windspeedKmph", "?")
        lines.append(
            f"    {time_str[:2]}:{time_str[2:]} — {h_desc}, {h_temp}°C "
            f"(feels {h_feels}°C), rain {h_rain}%, snow {h_snow}%, wind {h_wind}km/h"
        )
    return "\n".join(lines)


class WeatherTool:
    """Fetch weather forecasts using wttr.in JSON API."""
    name = "weather"
    description = "Fetch weather forecast for a location using wttr.in"
    system_prompt = (
        "## weather\n"
        "Fetch weather forecast using wttr.in (no API key). Returns current conditions + 3-day forecast.\n"
        "Parameters (JSON object):\n"
        "- location (string, required): City, IATA code, landmark, or coordinates (e.g. 'London', 'muc', '48.85,2.35')\n"
        "- lang (string, optional): Language code (e.g. 'en', 'ru')"
    )
    parameters = {
        "location": {
            "type": "string",
            "description": "City, IATA code, landmark, or coordinates",
            "required": True,
        },
        "lang": {
            "type": "string",
            "description": "Language code (e.g. 'fr', 'de')",
            "required": False,
        },
    }

    def execute(self, params, workdir=None):
        location = params.get("location", "").strip()
        if not location:
            return "[Error: 'location' parameter is required]"

        lang = params.get("lang", "").strip()
        if lang and lang not in ("en", "ru"):
            return "[Error: 'lang' only supports 'en' or 'ru']"
        params_str = "m"
        if lang:
            params_str += "&lang=" + urllib.parse.quote(lang)

        try:
            data = _fetch_json(location, params_str)
        except Exception as e:
            return f"[Error fetching weather: {e}]"

        try:
            area = data["nearest_area"][0]
            loc = area.get("areaName", [{}])[0].get("value", location)
            region = area.get("region", [{}])[0].get("value", "")
            country = area.get("country", [{}])[0].get("value", "")
            lat = area.get("latitude", "?")
            lon = area.get("longitude", "?")

            lines = [f"{loc}, {region}, {country} ({lat}, {lon})"]
            lines.append("")
            lines.append("Current conditions:")
            lines.append(_format_current(data["current_condition"][0]))
            lines.append("")
            lines.append("3-day forecast:")
            for day in data.get("weather", []):
                lines.append(_format_forecast(day))

            result = "\n".join(lines)
        except (KeyError, IndexError):
            result = f"[Error parsing weather data for: {location}]"

        return result[:MAX_OBSERVATION_CHARS]
