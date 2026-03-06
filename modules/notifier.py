"""Notification helpers — Slack messages for all modules."""
from __future__ import annotations

import logging

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger("daily_automate.notifier")


async def send_slack_message(token: str, channel: str, text: str) -> None:
    """Send a message to a Slack channel."""
    try:
        client = WebClient(token=token)
        client.chat_postMessage(channel=channel, text=text)
    except SlackApiError as e:
        logger.error("Slack API error: %s", e.response["error"])


async def notify(config: dict, message: str, pr_url: str = "", event: str = "") -> None:
    """Send a notification via Slack. Skips if no bot token configured."""
    token = config.get("slack", {}).get("bot_token", "")
    channel = config.get("slack", {}).get("default_channel", "")

    if not token or not channel:
        logger.debug("Slack not configured, skipping notification: %s", message)
        return

    text = message
    if pr_url:
        text += f"\n<{pr_url}|View PR>"

    await send_slack_message(token=token, channel=channel, text=text)
