from __future__ import annotations

import asyncio
from unittest.mock import patch, AsyncMock

import pytest

from modules.jira_client import extract_ticket_key, JiraClient


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_extract_ticket_key_from_branch():
    assert extract_ticket_key("PROJ-123-fix-login-bug") == "PROJ-123"
    assert extract_ticket_key("feature/DISC-456-add-feature") == "DISC-456"
    assert extract_ticket_key("main") is None
    assert extract_ticket_key("fix-typo") is None
    assert extract_ticket_key("PACHI-789") == "PACHI-789"


@patch("modules.jira_client._run_claude")
def test_get_issue(mock_claude):
    mock_claude.return_value = '{"fields": {"status": {"name": "To Do"}, "summary": "Fix bug"}}'
    client = JiraClient()
    result = run(client.get_issue("PROJ-123"))
    assert result["fields"]["status"]["name"] == "To Do"


@patch("modules.jira_client._run_claude")
def test_get_issue_messy_output(mock_claude):
    mock_claude.return_value = 'Here is the result:\n{"fields": {"status": {"name": "In Progress"}, "summary": "Add feature"}}\nDone.'
    client = JiraClient()
    result = run(client.get_issue("PROJ-123"))
    assert result["fields"]["status"]["name"] == "In Progress"


@patch("modules.jira_client._run_claude")
def test_transition_issue(mock_claude):
    mock_claude.return_value = "OK"
    client = JiraClient()
    result = run(client.transition_issue("PROJ-123", "Done"))
    assert result is True
