"""Slack Digest module: daily digest from monitored Slack channels."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from db import create_digest, log_activity
from modules.notifier import notify

logger = logging.getLogger("daily_automate.slack_digest")


async def _run_cmd(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("Command failed: %s\n%s", " ".join(args), stderr.decode())
        return ""
    return stdout.decode().strip()


def build_digest_prompt(channels: list[str]) -> str:
    """Build the prompt for generating a Slack digest."""
    if not channels:
        return (
            "Generate a brief daily digest summary. No specific channels were configured. "
            "Mention that the user should add channels to config.yaml under slack.digest_channels."
        )
    channel_list = ", ".join(channels)
    return (
        f"Generate a daily digest of important messages and discussions from these "
        f"Slack channels: {channel_list}.\n\n"
        f"For each channel, summarize:\n"
        f"- Key announcements or decisions\n"
        f"- Important discussions or threads\n"
        f"- Action items mentioned\n\n"
        f"Keep it concise — 2-3 bullet points per channel. "
        f"Use a casual, conversational tone."
    )


def parse_digest_output(output: str) -> str:
    """Parse and clean Claude's digest output."""
    if not output or not output.strip():
        return "(No digest output — generation may have failed)"
    return output.strip()


async def generate_digest(db_path: Path, config: dict) -> str:
    """Generate a Slack digest and save it.

    Returns the digest text.
    """
    channels = config.get("slack", {}).get("digest_channels", [])
    prompt = build_digest_prompt(channels)

    # Call Claude with Slack MCP access
    output = await _run_cmd("claude", "-p", prompt, "--output-format", "text")
    digest_text = parse_digest_output(output)

    # Save to DB
    today = datetime.now().strftime("%Y-%m-%d")
    channels_str = ",".join(channels) if channels else ""
    await create_digest(db_path, date=today, content=digest_text, channels=channels_str)
    await log_activity(db_path, module="slack_digest", action="generated", detail=f"Digest for {today}")

    # Notify Slack
    await notify(config, message=f"*Daily Digest — {today}*\n\n{digest_text}")

    return digest_text
