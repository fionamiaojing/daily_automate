"""Slack Digest module: daily digest from monitored Slack channels.

Generates both:
1. A full HTML report via /ai-digest skill -> ~/Desktop/learn/claude/ailearnings/
2. A text summary stored in the DB for the dashboard
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from db import create_digest, log_activity
from modules.notifier import notify

logger = logging.getLogger("daily_automate.slack_digest")

REPORT_DIR = Path.home() / "Desktop" / "learn" / "claude" / "ailearnings"


async def _run_cmd(*args: str, timeout: int = 600) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        logger.error("Command timed out after %ds: %s", timeout, " ".join(args))
        return ""
    if proc.returncode != 0:
        logger.warning("Command failed: %s\n%s", " ".join(args), stderr.decode())
        return ""
    return stdout.decode().strip()


def parse_digest_output(output: str) -> str:
    """Parse and clean Claude's digest output."""
    if not output or not output.strip():
        return "(No digest output — generation may have failed)"
    return output.strip()


def _normalize_channels(raw: list) -> list[dict]:
    """Normalize channel config to list of {name, id} dicts."""
    channels = []
    for item in raw:
        if isinstance(item, dict):
            channels.append({"name": item.get("name", ""), "id": item.get("id", "")})
        elif isinstance(item, str):
            channels.append({"name": item, "id": ""})
    return channels


async def generate_digest(db_path: Path, config: dict) -> str:
    """Generate a Slack digest: full HTML report via /ai-digest + text summary.

    Returns the summary text.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    report_path = str(REPORT_DIR / f"ai-report-{today}.html")

    # Step 1: Run /ai-digest skill via claude to generate the full HTML report.
    # The skill handles channel reading, thread fetching, ranking, and HTML generation.
    logger.info("Running /ai-digest to generate HTML report...")
    await _run_cmd(
        "claude", "-p", "/ai-digest", "--output-format", "text",
        timeout=600,  # ai-digest can take a while reading threads
    )

    # Step 2: Generate a short text summary for the dashboard
    raw_channels = config.get("slack", {}).get("digest_channels", [])
    channels = _normalize_channels(raw_channels)
    channels_str = ", ".join(ch["name"] for ch in channels) if channels else ""

    # Check if the report was created
    actual_report_path = report_path if Path(report_path).exists() else ""

    if actual_report_path:
        # Ask Claude to summarize the generated report for the dashboard
        summary_output = await _run_cmd(
            "claude", "-p",
            f"Read the file at {actual_report_path} and produce a plain-text summary "
            f"of the top 5 most important items. No HTML. Keep it under 300 words. "
            f"Format as a numbered list with the channel source in parentheses.",
            "--output-format", "text",
        )
        summary_text = parse_digest_output(summary_output)
    else:
        summary_text = "(AI digest report was not generated — check logs)"

    # Save to DB
    await create_digest(
        db_path, date=today, content=summary_text,
        channels=channels_str, report_path=actual_report_path,
    )
    await log_activity(db_path, module="slack_digest", action="generated", detail=f"Digest for {today}")

    # Notify Slack
    msg = f"*Daily Digest — {today}*\n\n{summary_text}"
    if actual_report_path:
        msg += f"\n\nFull report: {actual_report_path}"
    await notify(config, message=msg)

    return summary_text
