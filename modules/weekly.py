"""Weekly summary module: generates weekly report and creates Google Doc."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from db import (
    get_recent_activity, get_all_pr_status, get_standups,
    get_jira_automations, get_metrics_checks,
    create_weekly_summary, log_activity,
)
from modules.notifier import notify

logger = logging.getLogger("daily_automate.weekly")


def build_weekly_prompt(
    prs_summary: str,
    standups_summary: str,
    jira_summary: str,
    metrics_summary: str,
) -> str:
    """Build the prompt for generating a weekly summary."""
    return (
        "Generate a weekly summary report for this engineering week. "
        "Use a casual, conversational tone.\n\n"
        f"## PRs & Code\n{prs_summary or '(no PR data)'}\n\n"
        f"## Daily Standups\n{standups_summary or '(no standup data)'}\n\n"
        f"## JIRA Activity\n{jira_summary or '(no JIRA data)'}\n\n"
        f"## Metrics\n{metrics_summary or '(no metrics data)'}\n\n"
        "Format the summary with these sections:\n"
        "- **Highlights**: Top accomplishments this week\n"
        "- **In Progress**: Work that carried over\n"
        "- **Blockers/Risks**: Any ongoing issues\n"
        "- **Next Week**: Priorities for next week\n\n"
        "Keep it concise — suitable for sharing with the team."
    )


def parse_weekly_output(output: str) -> str:
    """Parse and clean Claude's weekly summary output."""
    if not output or not output.strip():
        return "(No weekly summary output — generation may have failed)"
    return output.strip()


async def generate_weekly_summary(db_path: Path, config: dict) -> str:
    """Generate a weekly summary, save to DB, create Google Doc, post to Slack."""
    # Gather data from the week
    prs = await get_all_pr_status(db_path)
    prs_summary = f"{len(prs)} open PRs tracked"

    standups = await get_standups(db_path, limit=5)
    standups_summary = f"{len(standups)} standups generated this week"

    jira_autos = await get_jira_automations(db_path, limit=20)
    jira_summary = f"{len(jira_autos)} JIRA automations this week"

    checks = await get_metrics_checks(db_path)
    metrics_summary = f"{len(checks)} metrics checks configured"

    # Build prompt
    prompt = build_weekly_prompt(
        prs_summary=prs_summary,
        standups_summary=standups_summary,
        jira_summary=jira_summary,
        metrics_summary=metrics_summary,
    )

    # Call Claude to generate summary
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", prompt, "--output-format", "text",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.error("Claude weekly summary failed: %s", stderr.decode())
        summary_text = "(Weekly summary generation failed)"
    else:
        summary_text = parse_weekly_output(stdout.decode().strip())

    # Create Google Doc via Claude with google-drive skill
    google_doc_url = ""
    try:
        doc_prompt = (
            f"Create a Google Doc titled 'Weekly Summary — "
            f"{datetime.now().strftime('%Y-%m-%d')}' with the following content:\n\n"
            f"{summary_text}"
        )
        doc_proc = await asyncio.create_subprocess_exec(
            "claude", "-p", doc_prompt, "--output-format", "text",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        doc_stdout, doc_stderr = await doc_proc.communicate()
        if doc_proc.returncode == 0:
            url_match = re.search(r"https://docs\.google\.com/\S+", doc_stdout.decode())
            if url_match:
                google_doc_url = url_match.group()
    except Exception as e:
        logger.error("Google Doc creation failed: %s", e)

    # Save to DB
    today = datetime.now()
    week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
    await create_weekly_summary(db_path, week_start=week_start, content=summary_text, google_doc_url=google_doc_url)
    await log_activity(db_path, module="weekly", action="generated", detail=f"Weekly summary for {week_start}")

    # Notify Slack
    msg = f"*Weekly Summary — {week_start}*\n\n{summary_text}"
    if google_doc_url:
        msg += f"\n\nGoogle Doc: {google_doc_url}"
    await notify(config, message=msg)

    return summary_text
