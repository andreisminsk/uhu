"""Time now tool: current date, time, and timezone."""

import sys
from datetime import datetime, timezone


def _tz_offset_str():
    """Return timezone offset string like +0530 or -0800."""
    offset = datetime.now().astimezone().utcoffset()
    if offset is None:
        return "+0000"
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    h, m = divmod(total // 60, 60)
    return f"{sign}{h:02d}{m:02d}"


def _tz_name():
    """Return timezone name, handling Windows encoding issues."""
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation",
            )
            tz_key_name, _ = winreg.QueryValueEx(key, "TimeZoneKeyName")
            winreg.CloseKey(key)
            if tz_key_name:
                return tz_key_name
        except Exception:
            pass
    try:
        import time as _time_mod
        return _time_mod.tzname[0]
    except Exception:
        return "UTC" + _tz_offset_str()


class TimeNowTool:
    """Return the current date, time, and timezone."""
    name = "time_now"
    description = "Return the current date, time, and timezone."
    system_prompt = (
        "## time_now\n"
        "Return the current date, time, and timezone.\n"
        "Parameters (JSON object):\n"
        "- utc (boolean, optional, default false): Also show UTC time\n"
        "Use this when you need to know the current date/time, e.g. for scheduling, timestamps, or time-relative logic."
    )
    parameters = {
        "utc": {
            "type": "boolean",
            "description": "Also show UTC time (default false)",
            "required": False,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        show_utc = params.get("utc", False)
        now = datetime.now()
        tz_name = _tz_name()
        tz_offset = _tz_offset_str()

        lines = [
            f"Date: {now.strftime('%Y-%m-%d')}",
            f"Time: {now.strftime('%H:%M:%S')}",
            f"Timezone: {tz_name} (UTC{tz_offset})",
        ]

        if show_utc:
            utc_now = datetime.now(timezone.utc)
            lines.append(f"UTC: {utc_now.strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines)
