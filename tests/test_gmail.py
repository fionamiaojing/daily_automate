from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from modules.gmail import fetch_unread_emails


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


SAMPLE_GMAIL = {
    "unread_count": 3,
    "messages": [
        {
            "id": "abc123",
            "from": "Alice <alice@doordash.com>",
            "subject": "Code review needed",
            "date": "Fri, 06 Mar 2026 10:00:00 -0800",
            "snippet": "Hey, can you review my PR?",
        },
        {
            "id": "def456",
            "from": "GitHub <noreply@github.com>",
            "subject": "[doordash/feed-service] PR #123 merged",
            "date": "Fri, 06 Mar 2026 09:30:00 -0800",
            "snippet": "Your pull request was merged.",
        },
    ],
}


@patch("modules.gmail._run_script")
def test_fetch_unread_emails(mock_script):
    mock_script.return_value = json.dumps(SAMPLE_GMAIL)
    data = run(fetch_unread_emails())
    assert data["unread_count"] == 3
    assert len(data["messages"]) == 2
    assert data["messages"][0]["subject"] == "Code review needed"


@patch("modules.gmail._run_script")
def test_fetch_unread_emails_empty(mock_script):
    mock_script.return_value = ""
    data = run(fetch_unread_emails())
    assert data["unread_count"] == 0
    assert data["messages"] == []


@patch("modules.gmail._run_script")
def test_fetch_unread_emails_bad_json(mock_script):
    mock_script.return_value = "not json"
    data = run(fetch_unread_emails())
    assert data["unread_count"] == 0
    assert data["messages"] == []
