"""Miscellaneous utility functions."""

from datetime import datetime


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
