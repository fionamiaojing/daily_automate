"""Gmail module: fetch unread emails via Gmail API."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from db import log_activity

logger = logging.getLogger("daily_automate.gmail")

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


async def fetch_unread_emails() -> dict:
    """Fetch unread emails from Gmail.

    Returns dict with keys: unread_count, messages (list of dicts).
    """
    output = await _run_script("google_gmail.py")
    if not output:
        return {"unread_count": 0, "messages": []}
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        logger.error("Failed to parse gmail output: %s", output[:200])
        return {"unread_count": 0, "messages": []}


async def poll_gmail(db_path: Path, config: dict) -> dict:
    """Poll Gmail and log the result."""
    data = await fetch_unread_emails()
    count = data.get("unread_count", 0)
    await log_activity(
        db_path, module="gmail", action="poll_complete",
        detail=f"{count} unread emails",
    )
    return data
