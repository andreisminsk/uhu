"""google_calendar tool — manage Google Calendar events via GCP service account."""

import datetime
import os

# Lazy imports — fail gracefully if not installed
_GOOGLE_DEPS_ERROR = (
    "Google Calendar dependencies not installed. "
    "Run: pip install google-auth google-api-python-client"
)


def _get_calendar_service(creds_path, calendar_id=None):
    """Build and return an authenticated Google Calendar service object."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds_path = os.path.expanduser(creds_path)
    if not os.path.isfile(creds_path):
        return None, f"[Error: Credentials file not found: {creds_path}]"

    try:
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/calendar"]
        )
        service = build("calendar", "v3", credentials=credentials)
        return service, None
    except Exception as e:
        return None, f"[Error: Failed to authenticate: {e}]"


def _parse_datetime(dt_str):
    """Parse a datetime string in various formats.

    Accepts: ISO format (2025-01-15T10:00:00), date only (2025-01-15),
    and relative expressions handled by dateutil if available.
    """
    # ISO format
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.datetime.strptime(dt_str, fmt)
        except ValueError:
            continue

    # Try dateutil for natural language
    try:
        from dateutil import parser
        return parser.parse(dt_str)
    except ImportError:
        pass

    return None


def _format_event(event):
    """Format a calendar event into a readable string."""
    eid = event.get("id", "?")
    summary = event.get("summary", "(no title)")
    start = event.get("start", {})
    end = event.get("end", {})

    # Start/end can be dateTime or date (all-day)
    start_str = start.get("dateTime") or start.get("date") or "?"
    end_str = end.get("dateTime") or end.get("date") or "?"
    location = event.get("location", "")
    desc = event.get("description", "")

    lines = [f"  [{eid}] {summary}"]
    lines.append(f"    {start_str} → {end_str}")
    if location:
        lines.append(f"    Location: {location}")
    if desc:
        preview = desc[:120] + ("..." if len(desc) > 120 else "")
        lines.append(f"    Description: {preview}")
    return "\n".join(lines)


class GoogleCalendarTool:
    name = "google_calendar"
    description = (
        "Manage Google Calendar events. "
        "Actions: create, list, quick_add, delete, update. "
        "Params: {\"action\": \"create\", \"summary\": \"...\", \"start\": \"...\", \"end\": \"...\"}"
    )
    system_prompt = (
        "## google_calendar\n"
        "Manage Google Calendar events using a GCP service account.\n"
        "\n"
        "Actions and parameters:\n"
        "\n"
        "### create\n"
        "Create a new event.\n"
        "```json\n"
        '{"action": "create", "summary": "Team standup", "start": "2025-01-15T10:00:00", "end": "2025-01-15T10:30:00", "description": "Daily sync", "location": "Room B"}\n'
        "```\n"
        "Required: summary, start, end. Optional: description, location.\n"
        "\n"
        "### list\n"
        "List upcoming events.\n"
        "```json\n"
        '{"action": "list", "days": 7, "query": "standup"}\n'
        "```\n"
        "Optional: days (default 7), query (filter by keyword).\n"
        "\n"
        "### quick_add\n"
        "Create an event from natural language.\n"
        "```json\n"
        '{"action": "quick_add", "text": "Lunch with Sarah Friday noon"}\n'
        "```\n"
        "Required: text.\n"
        "\n"
        "### delete\n"
        "Delete an event by ID.\n"
        "```json\n"
        '{"action": "delete", "event_id": "abc123"}\n'
        "```\n"
        "Required: event_id. Use list first to find the ID.\n"
        "\n"
        "### update\n"
        "Modify an existing event.\n"
        "```json\n"
        '{"action": "update", "event_id": "abc123", "summary": "New title", "start": "2025-01-15T11:00:00"}\n'
        "```\n"
        "Required: event_id. Optional: summary, start, end, description, location.\n"
        "\n"
        "When the user says things like \"add to calendar\", \"schedule\", \"create event\" — use create or quick_add.\n"
        "When the user says \"show calendar\", \"what's on my calendar\", \"upcoming events\" — use list.\n"
        "When the user says \"delete event\", \"remove from calendar\" — use delete (list first if no ID).\n"
        "When the user says \"move event\", \"reschedule\", \"change time\" — use update (list first if no ID).\n"
        "When the user says \"check calendar setup\", \"diagnose calendar\", \"calendar not working\" — use diagnostics.\n"
    )

    def execute(self, params, workdir=None):
        from ._config import load_config, DEFAULT_CONFIG

        # Load config
        config = load_config(workdir)
        cal_config = config.get("tools", {}).get("google_calendar", DEFAULT_CONFIG["tools"].get("google_calendar", {}))
        creds_path = cal_config.get("credentials_path", "gs-cred.json")
        calendar_id = cal_config.get("calendar_id", "primary")
        timezone = cal_config.get("timezone", "UTC")

        # Try to authenticate
        service, error = _get_calendar_service(creds_path, calendar_id)
        if error:
            return error

        action = params.get("action", "").lower()

        if action == "diagnostics" or action == "diag" or action == "info":
            return self._diagnostics(service, calendar_id, cal_config)

        if action == "create":
            return self._create(service, calendar_id, timezone, params)
        elif action == "list":
            return self._list(service, calendar_id, params)
        elif action == "quick_add":
            return self._quick_add(service, calendar_id, params)
        elif action == "delete":
            return self._delete(service, calendar_id, params)
        elif action == "update":
            return self._update(service, calendar_id, timezone, params)
        else:
            return (
                f"[Error: Unknown action '{action}'. "
                f"Supported actions: create, list, quick_add, delete, update]"
            )

    def _diagnostics(self, service, calendar_id, cal_config):
        """Show diagnostic info: config, service account email, accessible calendars."""
        lines = ["[Google Calendar Diagnostics]"]
        lines.append(f"  calendar_id: {calendar_id}")
        lines.append(f"  timezone: {cal_config.get('timezone', 'UTC')}")
        lines.append(f"  credentials_path: {cal_config.get('credentials_path', 'gs-cred.json')}")

        # Show service account email
        try:
            about = service.calendarList().list().execute()
            cals = about.get("items", [])
            lines.append(f"  accessible_calendars: {len(cals)}")
            for cal in cals:
                cid = cal.get("id", "?")
                summary = cal.get("summary", "?")
                access = cal.get("accessRole", "?")
                lines.append(f"    - {cid} ({summary}) [access: {access}]")
        except Exception as e:
            lines.append(f"  calendar_list_error: {e}")

        # Try to get the target calendar info
        try:
            cal_info = service.calendars().get(calendarId=calendar_id).execute()
            lines.append(f"  target_calendar: {cal_info.get('summary', '?')} ({cal_info.get('id', '?')})")
            lines.append(f"  target_timezone: {cal_info.get('timeZone', '?')}")
        except Exception as e:
            lines.append(f"  target_calendar_error: {e}")
            lines.append("")
            lines.append("  HINT: If 'calendar not found', you need to:")
            lines.append("  1. Share your Google Calendar with the service account email")
            lines.append("  2. Set calendar_id to your email (e.g., 'you@gmail.com') in .ollama_agent.json")

        return "\n".join(lines)

    def _create(self, service, calendar_id, timezone, params):
        summary = params.get("summary") or params.get("title") or params.get("event")
        if not summary:
            return "[Error: 'summary' is required for create action]"

        start_str = params.get("start") or params.get("begin") or params.get("from")
        end_str = params.get("end") or params.get("to")

        if not start_str:
            return "[Error: 'start' is required for create action]"
        if not end_str:
            return "[Error: 'end' is required for create action]"

        start_dt = _parse_datetime(start_str)
        if not start_dt:
            return f"[Error: Could not parse start datetime: '{start_str}'. Use ISO format like 2025-01-15T10:00:00]"

        end_dt = _parse_datetime(end_str)
        if not end_dt:
            return f"[Error: Could not parse end datetime: '{end_str}'. Use ISO format like 2025-01-15T11:00:00]"

        # Determine if all-day event (date only, no time)
        has_time = "T" in start_str or ":" in start_str

        if has_time:
            event_body = {
                "summary": summary,
                "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone},
            }
        else:
            event_body = {
                "summary": summary,
                "start": {"date": start_dt.strftime("%Y-%m-%d")},
                "end": {"date": (end_dt).strftime("%Y-%m-%d")},
            }

        if params.get("description") or params.get("desc"):
            event_body["description"] = params.get("description") or params.get("desc")
        if params.get("location") or params.get("where"):
            event_body["location"] = params.get("location") or params.get("where")

        try:
            event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
            return f"[Event created]\n{_format_event(event)}"
        except Exception as e:
            return f"[Error: Failed to create event: {e}]"

    def _list(self, service, calendar_id, params):
        days = params.get("days") or params.get("num_days") or 7
        try:
            days = int(days)
        except (ValueError, TypeError):
            days = 7

        query = params.get("query") or params.get("search") or params.get("filter")

        now = datetime.datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + datetime.timedelta(days=days)).isoformat() + "Z"

        try:
            kwargs = {
                "calendarId": calendar_id,
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": True,
                "orderBy": "startTime",
                "maxResults": 25,
            }
            if query:
                kwargs["q"] = query

            events_result = service.events().list(**kwargs).execute()
            events = events_result.get("items", [])

            if not events:
                if days == 1:
                    period = "today"
                    if query:
                        return f"[No events found for '{query}' {period}]"
                    return f"[No upcoming events {period}]"
                else:
                    period = f"in the next {days} days"
                    if query:
                        return f"[No events found for '{query}' {period}]"
                    return f"[No upcoming events {period}]"

            lines = [f"Calendar events (next {days} days):"]
            for event in events:
                lines.append(_format_event(event))
            return "\n".join(lines)

        except Exception as e:
            return f"[Error: Failed to list events: {e}]"

    def _quick_add(self, service, calendar_id, params):
        text = params.get("text") or params.get("event") or params.get("query")
        if not text:
            return "[Error: 'text' is required for quick_add action]"

        try:
            event = service.events().quickAdd(calendarId=calendar_id, text=text).execute()
            return f"[Event created via quick add]\n{_format_event(event)}"
        except Exception as e:
            return f"[Error: Failed to create event via quick add: {e}]"

    def _delete(self, service, calendar_id, params):
        event_id = params.get("event_id") or params.get("id") or params.get("event")
        if not event_id:
            return "[Error: 'event_id' is required for delete action. Use list first to find the event ID.]"

        try:
            # Fetch event details first for confirmation message
            event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
            summary = event.get("summary", "(no title)")
            start_str = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date") or "?"
            service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            return f"[Event deleted: {summary} at {start_str} (id: {event_id})]"
        except Exception as e:
            return f"[Error: Failed to delete event: {e}]"

    def _update(self, service, calendar_id, timezone, params):
        event_id = params.get("event_id") or params.get("id") or params.get("event")
        if not event_id:
            return "[Error: 'event_id' is required for update action. Use list first to find the event ID.]"

        try:
            event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        except Exception as e:
            return f"[Error: Event not found: {e}]"

        # Update fields
        if params.get("summary") or params.get("title"):
            event["summary"] = params.get("summary") or params.get("title")
        if params.get("description") or params.get("desc"):
            event["description"] = params.get("description") or params.get("desc")
        if params.get("location") or params.get("where"):
            event["location"] = params.get("location") or params.get("where")

        if params.get("start") or params.get("begin") or params.get("from"):
            start_str = params.get("start") or params.get("begin") or params.get("from")
            start_dt = _parse_datetime(start_str)
            if not start_dt:
                return f"[Error: Could not parse start datetime: '{start_str}']"
            has_time = "T" in start_str or ":" in start_str
            if has_time:
                event["start"] = {"dateTime": start_dt.isoformat(), "timeZone": timezone}
            else:
                event["start"] = {"date": start_dt.strftime("%Y-%m-%d")}

        if params.get("end") or params.get("to"):
            end_str = params.get("end") or params.get("to")
            end_dt = _parse_datetime(end_str)
            if not end_dt:
                return f"[Error: Could not parse end datetime: '{end_str}']"
            has_time = "T" in end_str or ":" in end_str
            if has_time:
                event["end"] = {"dateTime": end_dt.isoformat(), "timeZone": timezone}
            else:
                event["end"] = {"date": end_dt.strftime("%Y-%m-%d")}

        try:
            updated = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
            return f"[Event updated]\n{_format_event(updated)}"
        except Exception as e:
            return f"[Error: Failed to update event: {e}]"
