"""JIRA automation: link PRs to tickets, auto-transition, create subtasks."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from db import get_all_pr_status, log_jira_automation, log_activity
from modules.jira_client import JiraClient, extract_ticket_key
from modules.notifier import notify

logger = logging.getLogger("daily_automate.jira_automation")


def should_transition(pr_state: str, current_jira_status: str) -> str | None:
    """Determine if a JIRA ticket should be transitioned based on PR state.

    Returns target status name or None if no transition needed.
    """
    status_lower = current_jira_status.lower()

    if pr_state == "merged" and status_lower != "done":
        return "Done"
    if pr_state == "open" and status_lower in ("to do", "open", "backlog"):
        return "In Progress"
    return None


async def link_prs_to_tickets(db_path: Path, projects: list[str]) -> list[dict]:
    """Scan PRs in DB and extract JIRA ticket keys from titles.

    Returns list of {pr_url, ticket_key, title} for linked PRs.
    """
    prs = await get_all_pr_status(db_path)
    linked = []
    project_prefixes = [p.upper() + "-" for p in projects]

    for pr in prs:
        title = pr.get("title", "")
        pr_url = pr.get("pr_url", "")
        head_branch = pr.get("head_branch", "")

        # Try to extract ticket key from branch name first (most reliable)
        ticket_key = extract_ticket_key(head_branch) if head_branch else None

        # Fall back to title
        if not ticket_key:
            ticket_key = extract_ticket_key(title)

        # Last resort: URL
        if not ticket_key:
            ticket_key = extract_ticket_key(pr_url)

        if ticket_key and any(ticket_key.startswith(prefix) for prefix in project_prefixes):
            linked.append({
                "pr_url": pr_url,
                "ticket_key": ticket_key,
                "title": title,
                "ci_status": pr.get("ci_status", "unknown"),
                "state": pr.get("state", "open"),
            })

    return linked


async def run_jira_automation(db_path: Path, config: dict) -> None:
    """Main JIRA automation loop: link PRs, transition tickets, create subtasks."""
    jira_config = config.get("jira", {})
    projects = jira_config.get("projects", [])
    auto_transition = jira_config.get("auto_transition", True)

    if not projects:
        logger.info("No JIRA projects configured — skipping automation")
        await log_activity(db_path, module="jira", action="poll_complete", detail="No projects configured")
        return

    client = JiraClient()

    # Link PRs to tickets
    linked = await link_prs_to_tickets(db_path, projects=projects)

    for item in linked:
        ticket_key = item["ticket_key"]

        try:
            issue = await client.get_issue(ticket_key)
        except Exception as e:
            logger.error("Failed to fetch JIRA issue %s: %s", ticket_key, e)
            continue

        current_status = issue.get("fields", {}).get("status", {}).get("name", "")

        # Auto-transition if enabled
        if auto_transition:
            pr_state = item.get("state", "open")
            target = should_transition(pr_state, current_status)

            if target:
                try:
                    success = await client.transition_issue(ticket_key, target)
                    if success:
                        action = f"transitioned to {target}"
                        await log_jira_automation(db_path, ticket_key=ticket_key, action=action)
                        await log_activity(db_path, module="jira", action="transition", detail=f"{ticket_key}: {action}")
                        await notify(config, message=f"*JIRA* {ticket_key} → {target} (linked to PR)")
                        logger.info("Transitioned %s to %s", ticket_key, target)
                except Exception as e:
                    logger.error("Failed to transition %s: %s", ticket_key, e)

    await log_activity(db_path, module="jira", action="poll_complete", detail=f"Checked {len(linked)} linked tickets")
