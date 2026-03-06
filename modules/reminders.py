"""Reminders module: morning summary and periodic nudges."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from db import (
    get_all_pr_status,
    get_pending_drafts,
    create_reminder,
    get_active_reminders,
    log_activity,
)
from modules.notifier import notify

logger = logging.getLogger("daily_automate.reminders")


async def _run_cmd(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return "[]"
    return stdout.decode().strip()


async def gather_pending_review_prs() -> list[dict]:
    """Fetch PRs that need your review."""
    output = await _run_cmd(
        "gh", "pr", "list", "--search", "review-requested:@me",
        "--state", "open", "--json", "url,number,title",
    )
    return json.loads(output) if output else []


def build_morning_summary(
    my_prs: list[dict],
    review_prs: list[dict],
) -> str:
    """Build a morning summary text from gathered data."""
    lines = []

    if my_prs:
        lines.append("*Your open PRs:*")
        for pr in my_prs:
            ci = pr.get("ci_status", "unknown")
            lines.append(f"  - {pr['title']} (CI: {ci})")
    else:
        lines.append("*Your open PRs:* None")

    if review_prs:
        lines.append(f"\n*PRs waiting for your review ({len(review_prs)}):*")
        for pr in review_prs:
            lines.append(f"  - PR #{pr['number']}: {pr['title']}")
    else:
        lines.append("\n*PRs waiting for your review:* None")

    if not my_prs and not review_prs:
        lines.append("\nLooks like a clear morning! No pending items.")

    return "\n".join(lines)


async def morning_summary(db_path: Path, config: dict) -> str:
    """Generate and send the morning summary."""
    my_prs = await get_all_pr_status(db_path)
    review_prs = await gather_pending_review_prs()
    drafts = await get_pending_drafts(db_path)

    summary = build_morning_summary(my_prs=my_prs, review_prs=review_prs)

    if drafts:
        summary += f"\n\n*Pending reply drafts:* {len(drafts)} — check /prs to approve"

    await create_reminder(db_path, type="morning", content=summary)
    await log_activity(db_path, module="reminders", action="morning_summary", detail="Morning summary generated")

    today = datetime.now().strftime("%Y-%m-%d")
    await notify(config, message=f"*Morning Summary — {today}*\n\n{summary}")

    return summary


async def periodic_nudge(db_path: Path, config: dict) -> None:
    """Send periodic reminders about stale items."""
    my_prs = await get_all_pr_status(db_path)
    drafts = await get_pending_drafts(db_path)

    nudges = []
    failed = [pr for pr in my_prs if pr.get("ci_status") == "failure"]
    if failed:
        nudges.append(f"{len(failed)} PR(s) with failing CI")

    if drafts:
        nudges.append(f"{len(drafts)} reply draft(s) waiting for approval")

    if nudges:
        text = "*Periodic reminder:*\n" + "\n".join(f"  - {n}" for n in nudges)
        await create_reminder(db_path, type="periodic", content=text)
        await log_activity(db_path, module="reminders", action="periodic_nudge", detail=text)
        await notify(config, message=text)
