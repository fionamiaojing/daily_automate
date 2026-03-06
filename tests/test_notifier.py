from __future__ import annotations

import asyncio
from unittest.mock import patch, MagicMock

import pytest

from modules.notifier import send_slack_message, notify


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@patch("modules.notifier.WebClient")
def test_send_slack_message(mock_client_cls):
    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = {"ok": True}
    mock_client_cls.return_value = mock_client

    run(send_slack_message(token="xoxb-test", channel="#test", text="Hello"))
    mock_client.chat_postMessage.assert_called_once_with(channel="#test", text="Hello")


@patch("modules.notifier.send_slack_message")
def test_notify_calls_slack(mock_send):
    mock_send.return_value = None
    config = {"slack": {"bot_token": "xoxb-test", "default_channel": "#alerts"}}
    run(notify(config, message="CI failed", pr_url="https://github.com/org/repo/pull/1", event="ci_changed"))
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert "CI failed" in call_kwargs.get("text", "")


@patch("modules.notifier.send_slack_message")
def test_notify_skips_when_no_token(mock_send):
    config = {"slack": {"bot_token": "", "default_channel": "#alerts"}}
    run(notify(config, message="CI failed", pr_url="", event="ci_changed"))
    mock_send.assert_not_called()
