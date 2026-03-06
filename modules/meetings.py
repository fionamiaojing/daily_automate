"""Meetings module: fetch today's calendar events via Google Calendar API."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from db import log_activity

logger = logging.getLogger("daily_automate.meetings")

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
VENV_PYTHON = str(BASE_DIR / ".venv" / "bin" / "python")


async def _run_script(script: str, timeout: int = 60) -> str:
    proc = await asyncio.create_subprocess_exec(
        VENV_PYTHON, str(SCRIPTS_DIR / script),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(SCRIPTS_DIR),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        logger.error("Script %s timed out after %ds", script, timeout)
        return ""
    if proc.returncode != 0:
        logger.warning("Script %s failed:\n%s", script, stderr.decode())
        return ""
    return stdout.decode().strip()


async def fetch_todays_meetings() -> list[dict]:
    """Fetch today's meetings from Google Calendar."""
    output = await _run_script("google_calendar.py")
    if not output:
        return []
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        logger.error("Failed to parse calendar output: %s", output[:200])
        return []


def format_time(iso_str: str) -> str:
    """Format an ISO datetime string to a short time like '9:30 AM'."""
    if not iso_str or len(iso_str) <= 10:
        return "All day"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%-I:%M %p")
    except ValueError:
        return iso_str


async def poll_meetings(db_path: Path, config: dict) -> list[dict]:
    """Poll today's meetings and log the result."""
    meetings = await fetch_todays_meetings()
    count = len(meetings)
    await log_activity(
        db_path, module="meetings", action="poll_complete",
        detail=f"Found {count} meetings today",
    )
    return meetings


def meetings_summary(meetings: list[dict]) -> str:
    """Build a short text summary for notifications."""
    if not meetings:
        return "No meetings today."
    count = len(meetings)
    first = meetings[0]
    first_time = format_time(first.get("start", ""))
    summary = f"You have {count} meeting{'s' if count != 1 else ''} today."
    summary += f" First: {first.get('summary', '')} at {first_time}."
    return summary
