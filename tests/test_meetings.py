from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from modules.meetings import fetch_todays_meetings, format_time, meetings_summary


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


SAMPLE_EVENTS = [
    {
        "summary": "Standup",
        "start": "2026-03-06T09:30:00-08:00",
        "end": "2026-03-06T09:45:00-08:00",
        "location": "",
        "meet_link": "https://meet.google.com/abc-defg-hij",
        "attendees": ["alice@doordash.com", "bob@doordash.com"],
        "status": "confirmed",
        "html_link": "https://calendar.google.com/event?eid=abc123",
    },
    {
        "summary": "1:1 with Manager",
        "start": "2026-03-06T14:00:00-08:00",
        "end": "2026-03-06T14:30:00-08:00",
        "location": "",
        "meet_link": "",
        "attendees": ["manager@doordash.com"],
        "status": "confirmed",
        "html_link": "",
    },
]


@patch("modules.meetings._run_script")
def test_fetch_todays_meetings(mock_script):
    mock_script.return_value = json.dumps(SAMPLE_EVENTS)
    events = run(fetch_todays_meetings())
    assert len(events) == 2
    assert events[0]["summary"] == "Standup"


@patch("modules.meetings._run_script")
def test_fetch_todays_meetings_empty(mock_script):
    mock_script.return_value = ""
    events = run(fetch_todays_meetings())
    assert events == []


def test_format_time_iso():
    assert "9:30 AM" in format_time("2026-03-06T09:30:00-08:00")


def test_format_time_all_day():
    assert format_time("2026-03-06") == "All day"


def test_format_time_empty():
    assert format_time("") == "All day"


def test_meetings_summary_with_meetings():
    summary = meetings_summary(SAMPLE_EVENTS)
    assert "2 meetings" in summary
    assert "Standup" in summary


def test_meetings_summary_no_meetings():
    summary = meetings_summary([])
    assert "No meetings" in summary
