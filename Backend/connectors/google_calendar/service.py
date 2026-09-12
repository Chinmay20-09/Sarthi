"""
Google Calendar API service — fetches real calendar data.

Uses the Google Calendar API v3 via httpx (no google-api-python-client dependency
for the API calls themselves — only google-auth-oauthlib is needed for the OAuth flow).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"


def _get_access_token(token_data: dict) -> str | None:
    """Extract the access token from token data."""
    return token_data.get("access_token")


def _headers(token_data: dict) -> dict[str, str]:
    """Build authorization headers."""
    token = _get_access_token(token_data)
    if not token:
        raise ValueError("No access token available")
    return {"Authorization": f"Bearer {token}"}


def list_upcoming_events(
    token_data: dict,
    max_results: int = 10,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Fetch upcoming events from Google Calendar.

    Args:
        token_data: OAuth token data with a valid access_token.
        max_results: Maximum number of events to return.
        calendar_id: Calendar to query (default: primary).

    Returns:
        Dict with 'events' list and 'success' status.
    """
    try:
        headers = _headers(token_data)

        # Time range: from now to 30 days ahead
        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=30)).isoformat()

        params = {
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
        }

        url = f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events"

        resp = httpx.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        events = []
        for item in data.get("items", []):
            event = _normalize_event(item)
            events.append(event)

        return {"success": True, "events": events}

    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 401:
            return {"success": False, "error": "Token expired — please reconnect", "events": []}
        elif status == 403:
            return {
                "success": False,
                "error": "Calendar API access denied — ensure the API is enabled in Google Cloud",
                "events": [],
            }
        logger.error(f"Calendar API error: {status} {e.response.text}")
        return {"success": False, "error": f"Calendar API error: {status}", "events": []}
    except Exception as e:
        logger.error(f"Failed to fetch calendar events: {e}")
        return {"success": False, "error": str(e), "events": []}


def get_calendar_info(token_data: dict) -> dict[str, Any]:
    """Get calendar metadata (name, timezone, etc.)."""
    try:
        headers = _headers(token_data)
        url = f"{CALENDAR_API_BASE}/calendars/primary"
        resp = httpx.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return {
            "success": True,
            "summary": data.get("summary", ""),
            "timeZone": data.get("timeZone", ""),
            "id": data.get("id", ""),
        }
    except Exception as e:
        logger.error(f"Failed to get calendar info: {e}")
        return {"success": False, "error": str(e)}


def _normalize_event(item: dict) -> dict[str, Any]:
    """Normalize a Google Calendar event into a clean Sarthi-friendly structure.

    Handles both timed events and all-day events.
    """
    start = item.get("start", {})
    end = item.get("end", {})

    # All-day events have "date" instead of "dateTime"
    start_time = start.get("dateTime") or start.get("date", "")
    end_time = end.get("dateTime") or end.get("date", "")
    is_all_day = "date" in start and "dateTime" not in start

    return {
        "id": item.get("id", ""),
        "summary": item.get("summary", "(No title)"),
        "description": item.get("description", ""),
        "start": start_time,
        "end": end_time,
        "is_all_day": is_all_day,
        "location": item.get("location", ""),
        "status": item.get("status", ""),
        "html_link": item.get("htmlLink", ""),
        "organizer": item.get("organizer", {}).get("email", ""),
        "attendees_count": len(item.get("attendees", [])),
    }
