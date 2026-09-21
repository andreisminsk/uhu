"""Miscellaneous utility functions."""

import logging
import os
import re
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_github_raw_url(filename="uhu-ver.txt"):
    """Dynamically discover the GitHub raw URL for a file in the repo root.

    Walks up from this file's location to find the .git directory, then reads
    the origin remote URL to construct the raw.githubusercontent.com URL.
    Returns None if not in a git repo or remote is not GitHub.
    """
    try:
        # Find git root by walking up from this file's directory
        current = os.path.dirname(os.path.abspath(__file__))
        git_root = None
        for _ in range(10):
            if os.path.isdir(os.path.join(current, ".git")):
                git_root = current
                break
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        if not git_root:
            return None

        # Get origin remote URL
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=3,
            cwd=git_root,
        )
        if result.returncode != 0:
            return None
        remote_url = result.stdout.strip()

        # Parse GitHub URL (handles https, ssh, and git@ formats)
        # https://github.com/owner/repo(.git)
        # git@github.com:owner/repo(.git)
        m = re.search(r'github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$', remote_url)
        if not m:
            return None
        owner, repo = m.group(1), m.group(2)

        # Get default branch
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=3,
            cwd=git_root,
        )
        branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "main"
        if not branch or branch == "HEAD":
            branch = "main"

        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"
    except Exception as e:
        logger.debug("Failed to discover GitHub URL: %s", e)
        return None


# Fallback raw URL for update checks — the public repository. Used when git
# discovery fails (pip installs from git+URL have no .git directory) or when
# the discovered remote is unreachable (e.g. a private repo).
_FALLBACK_RAW_URL = "https://raw.githubusercontent.com/andreisminsk/uhu/main/uhu-ver.txt"


def get_local_version():
    """Return the local uhu version string, or None if unknown.

    Preference order:
    1. uhu-ver.txt next to the package — git checkout or direct script run
    2. Installed package metadata — pip install (incl. git+URL installs)
    """
    ver_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uhu-ver.txt")
    try:
        with open(ver_path, "r", encoding="utf-8") as f:
            version = f.read().strip()
        if version:
            return version
    except OSError:
        pass
    try:
        from importlib.metadata import version as _pkg_version
        # Historically the console script was misspelled "huhu" in some
        # builds; keep trying both names for version lookup robustness.
        for dist_name in ("huhu", "uhu"):
            try:
                v = _pkg_version(dist_name)
                if v:
                    return v
            except Exception:
                continue
    except Exception:
        pass
    return None


_last_check_error = None


def get_last_check_error():
    """Return a short description of the last version-check fetch failure, or None."""
    return _last_check_error


def _fetch_text(url, timeout=3):
    """Fetch URL content as text.

    Prefers requests (a hard dependency) because its bundled certifi CA
    bundle avoids the macOS 'unable to get local issuer certificate'
    failures that plague urllib's default SSL context. Falls back to
    urllib when requests is unavailable.
    """
    headers = {"User-Agent": "uhu-version-check"}
    try:
        import requests
        resp = requests.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
        return resp.text
    except ImportError:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")


def check_for_update(current_version, timeout=3):
    """Check GitHub for a newer version. Returns (latest_version, is_newer) or (None, False).

    Tries the git-discovered raw URL first, then falls back to the public
    repository — covers pip installs (no .git directory) and private or
    unreachable remotes. On failure, the reason is available via
    get_last_check_error().
    """
    global _last_check_error
    urls = []
    discovered = _get_github_raw_url()
    if discovered and discovered != _FALLBACK_RAW_URL:
        urls.append(discovered)
    urls.append(_FALLBACK_RAW_URL)
    last_error = None
    for url in urls:
        try:
            latest = _fetch_text(url, timeout=timeout).strip()
            if latest:
                _last_check_error = None
                return (latest, _compare_versions(latest, current_version) > 0)
        except Exception as e:
            last_error = e
            logger.debug("Version check failed for %s: %s", url, e)
    _last_check_error = f"{type(last_error).__name__}: {last_error}"[:120] if last_error else "no reachable URL"
    return (None, False)


def _compare_versions(a, b):
    """Compare two dot-separated version strings. Returns 1 if a>b, -1 if a<b, 0 if equal."""
    def parse(v):
        parts = []
        for p in v.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        return parts
    pa, pb = parse(a), parse(b)
    while len(pa) < len(pb):
        pa.append(0)
    while len(pb) < len(pa):
        pb.append(0)
    for x, y in zip(pa, pb):
        if x > y:
            return 1
        if x < y:
            return -1
    return 0


def relative_time(iso_str):
    """Convert an ISO datetime string to a human-readable relative time."""
    try:
        saved_dt = datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return "?"
    now = datetime.now(saved_dt.tzinfo) if saved_dt.tzinfo else datetime.now()
    delta = now - saved_dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''} ago"
    months = days // 30
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = months // 12
    return f"{years} year{'s' if years != 1 else ''} ago"
