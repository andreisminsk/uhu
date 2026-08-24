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


def check_for_update(current_version, timeout=3):
    """Check GitHub for a newer version. Returns (latest_version, is_newer) or (None, False)."""
    try:
        import urllib.request
        url = _get_github_raw_url()
        if not url:
            return (None, False)
        req = urllib.request.Request(url, headers={"User-Agent": "uhu-version-check"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latest = resp.read().decode("utf-8", errors="replace").strip()
        if not latest:
            return (None, False)
        is_newer = _compare_versions(latest, current_version) > 0
        return (latest, is_newer)
    except Exception as e:
        logger.debug("Version check failed: %s", e)
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
