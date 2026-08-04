"""Ollama balance/usage indicator — fetches usage from ollama.com/settings.

Uses exported Netscape-format cookies for authentication, same approach
as the standalone ollama-balance scraper. Results are cached with a TTL
to avoid hitting ollama.com on every show_ctx() call.
"""

import json
import logging
import os
import re
import threading
import time
from http.cookiejar import MozillaCookieJar
from pathlib import Path

logger = logging.getLogger(__name__)

# Default cache TTL: 5 minutes
_DEFAULT_TTL = 300


class OllamaBalance:
    """Fetches and caches ollama.com usage data."""

    BASE_URL = "https://ollama.com"

    def __init__(self, cookie_path, ttl=_DEFAULT_TTL):
        self.cookie_path = cookie_path
        self.ttl = ttl
        self._cache = None
        self._cache_time = 0
        self._lock = threading.Lock()

    def _load_cookies(self, session):
        """Load Netscape-format cookies into a requests.Session."""
        from requests import Session
        jar = MozillaCookieJar(self.cookie_path)
        jar.load(ignore_discard=True, ignore_expires=True)
        for cookie in jar:
            session.cookies.set_cookie(cookie)
        return session

    def _fetch(self):
        """Fetch and parse usage data from ollama.com/settings."""
        import requests
        from bs4 import BeautifulSoup

        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
        })
        self._load_cookies(session)

        resp = session.get(f"{self.BASE_URL}/settings", timeout=15)
        resp.raise_for_status()
        html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        result = {}

        # Session usage
        m = re.search(r"Session usage\s*(\d+(?:\.\d+)?%)\s*used", text)
        if m:
            result["session_usage"] = m.group(1)

        m = re.search(r"Resets in (\d+ \w+)[\.\n]", text)
        if m:
            result["session_resets_in"] = m.group(1)

        # Weekly usage
        m = re.search(r"Weekly usage\s*(\d+(?:\.\d+)?%)\s*used", text)
        if m:
            result["weekly_usage"] = m.group(1)

        resets = re.findall(r"Resets in (\d+ \w+)", text)
        if len(resets) >= 2:
            result["weekly_resets_in"] = resets[1]
        elif len(resets) == 1 and "session_resets_in" not in result:
            result["weekly_resets_in"] = resets[0]

        # Balance
        m = re.search(r"Balance remaining\s*\$(\d+(?:\.\d+)?)", text)
        if m:
            result["balance_remaining"] = f"${m.group(1)}"

        return result

    def get_usage(self):
        """Return cached usage dict, or fetch if stale. Returns None on error."""
        with self._lock:
            now = time.time()
            if self._cache and (now - self._cache_time) < self.ttl:
                return self._cache
            try:
                self._cache = self._fetch()
                self._cache_time = now
                return self._cache
            except Exception as e:
                logger.debug("ollama balance fetch failed: %s", e)
                # Return stale cache if available, else None
                return self._cache

    def format_indicator(self):
        """Return a one-liner like: [ollama: session 1.9% (5h) | weekly 5.7% (5d) | $4.98]

        Returns "[ollama: stats n/a]" if scraping fails or returns no data.
        """
        usage = self.get_usage()
        if not usage:
            return "[ollama: stats n/a]"

        parts = []
        if "session_usage" in usage:
            s = f"session {usage['session_usage']}"
            if "session_resets_in" in usage:
                s += f" ({self._short_time(usage['session_resets_in'])})"
            parts.append(s)
        if "weekly_usage" in usage:
            s = f"weekly {usage['weekly_usage']}"
            if "weekly_resets_in" in usage:
                s += f" ({self._short_time(usage['weekly_resets_in'])})"
            parts.append(s)
        if "balance_remaining" in usage:
            parts.append(usage["balance_remaining"])

        if not parts:
            return "[ollama: stats n/a]"
        return "[ollama: " + " | ".join(parts) + "]"

    @staticmethod
    def _short_time(text):
        """Shorten '5 hours' -> '5h', '2 days' -> '2d', '3 minutes' -> '3m'."""
        m = re.match(r"(\d+)\s+(\w+)", text)
        if not m:
            return text
        num, unit = m.group(1), m.group(2).lower()
        return num + unit[0]


# ── Singleton management ─────────────────────────────────────────────

_balance_instance = None
_balance_lock = threading.Lock()


def get_balance_indicator(workdir=None):
    """Get the OllamaBalance singleton, or None if not configured.

    Cookie path is resolved from .ollama_agent.json config, with fallbacks:
    1. tools.ollama_balance.cookie_path in config
    2. <workdir>/ollama.com_cookies.txt
    3. <agent_dir>/ollama.com_cookies.txt
    """
    global _balance_instance
    with _balance_lock:
        if _balance_instance is not None:
            return _balance_instance

        from .tools._config import load_config, _agent_dir
        config = load_config(workdir)
        balance_cfg = config.get("tools", {}).get("ollama_balance", {})
        cookie_path = balance_cfg.get("cookie_path")

        if not cookie_path:
            # Fallback: look for cookies file in workdir or agent dir
            candidates = [
                os.path.join(workdir or ".", "ollama.com_cookies.txt"),
                os.path.join(_agent_dir(), "ollama.com_cookies.txt"),
            ]
            for c in candidates:
                if os.path.isfile(c):
                    cookie_path = c
                    break

        if not cookie_path or not os.path.isfile(cookie_path):
            return None

        ttl = balance_cfg.get("ttl", _DEFAULT_TTL)
        _balance_instance = OllamaBalance(cookie_path, ttl=ttl)
        return _balance_instance
