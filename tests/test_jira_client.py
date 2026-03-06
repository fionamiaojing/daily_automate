from __future__ import annotations

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

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


def test_jira_client_init():
    client = JiraClient(base_url="https://test.atlassian.net", email="a@b.com", api_token="tok")
    assert client.base_url == "https://test.atlassian.net"


@patch("modules.jira_client.httpx.AsyncClient")
def test_get_issue(mock_client_cls):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"key": "PROJ-123", "fields": {"status": {"name": "To Do"}}}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client

    client = JiraClient(base_url="https://test.atlassian.net", email="a@b.com", api_token="tok")
    result = run(client.get_issue("PROJ-123"))
    assert result["key"] == "PROJ-123"


@patch("modules.jira_client.httpx.AsyncClient")
def test_transition_issue(mock_client_cls):
    transitions_resp = MagicMock()
    transitions_resp.status_code = 200
    transitions_resp.json.return_value = {"transitions": [{"id": "31", "name": "In Progress"}, {"id": "41", "name": "Done"}]}
    transitions_resp.raise_for_status = MagicMock()

    transition_resp = MagicMock()
    transition_resp.status_code = 204
    transition_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=transitions_resp)
    mock_client.post = AsyncMock(return_value=transition_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client

    client = JiraClient(base_url="https://test.atlassian.net", email="a@b.com", api_token="tok")
    result = run(client.transition_issue("PROJ-123", "Done"))
    assert result is True
