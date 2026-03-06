"""Fetch today's calendar events via Google Calendar API."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta

from googleapiclient.discovery import build

from google_auth import get_credentials

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def fetch_todays_events() -> list[dict]:
    """Return today's events as a list of dicts."""
    creds = get_credentials(SCOPES, "calendar")
    service = build("calendar", "v3", credentials=creds)

    now = datetime.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
    end_of_day = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat() + "Z"

    result = service.events().list(
        calendarId="primary",
        timeMin=start_of_day,
        timeMax=end_of_day,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    IGNORED_EVENTS = {"coding", "dns"}

    events = []
    for item in result.get("items", []):
        # Skip all-day events (they have "date" but no "dateTime")
        if "dateTime" not in item.get("start", {}):
            continue
        # Skip focus time / blocked events
        if item.get("summary", "").strip().lower() in IGNORED_EVENTS:
            continue
        start = item["start"]["dateTime"]
        end = item["end"].get("dateTime", "")
        attendees = [a.get("email", "") for a in item.get("attendees", [])]

        # Extract RSVP statuses
        my_rsvp = ""
        other_rsvp = ""  # For 1:1s, show the other person's status
        other_name = ""
        raw_attendees = item.get("attendees", [])
        for a in raw_attendees:
            if a.get("self"):
                my_rsvp = a.get("responseStatus", "")
            else:
                other_rsvp = a.get("responseStatus", "")
                other_name = a.get("displayName", a.get("email", "").split("@")[0])

        # Extract Google Meet link
        meet_link = ""
        if item.get("hangoutLink"):
            meet_link = item["hangoutLink"]
        elif item.get("conferenceData", {}).get("entryPoints"):
            for ep in item["conferenceData"]["entryPoints"]:
                if ep.get("entryPointType") == "video":
                    meet_link = ep.get("uri", "")
                    break

        # For 1:1s (exactly 2 attendees), include the other person's info
        is_1on1 = len(raw_attendees) == 2
        event = {
            "summary": item.get("summary", "(No title)"),
            "start": start,
            "end": end,
            "location": item.get("location", ""),
            "meet_link": meet_link,
            "attendees": attendees,
            "my_rsvp": my_rsvp,
            "html_link": item.get("htmlLink", ""),
        }
        if is_1on1:
            event["other_name"] = other_name
            event["other_rsvp"] = other_rsvp
        events.append(event)

    return events


if __name__ == "__main__":
    events = fetch_todays_events()
    json.dump(events, sys.stdout, indent=2)
    print()
