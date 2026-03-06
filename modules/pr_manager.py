"""PR Manager module: polls GitHub PRs, tracks CI status, detects new comments."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Callable, Awaitable

from db import (
    upsert_pr_status,
    get_pr_status,
    create_pr_draft,
    get_pending_drafts,
    log_activity,
)

logger = logging.getLogger("daily_automate.pr_manager")


async def _run_gh(*args: str) -> str:
    """Run a gh CLI command and return stdout."""
    proc = await asyncio.create_subprocess_exec(
        "gh", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("gh command failed: %s\nstderr: %s", " ".join(args), stderr.decode())
        return "[]"
    return stdout.decode()


async def fetch_my_open_prs() -> list[dict]:
    """Fetch all open PRs authored by the current user across all repos."""
    output = await _run_gh(
        "search", "prs", "--author", "@me", "--state", "open",
        "--json", "url,number,title,repository",
    )
    return json.loads(output)


async def fetch_pr_check_status(repo: str, pr_number: int) -> str:
    """Fetch CI check status for a PR. Returns 'success', 'failure', or 'pending'."""
    output = await _run_gh(
        "pr", "view", str(pr_number), "--repo", repo,
        "--json", "statusCheckRollup",
    )
    data = json.loads(output)
    checks = data.get("statusCheckRollup", [])
    if not checks:
        return "pending"

    has_failure = any(c.get("conclusion") == "FAILURE" for c in checks)
    has_pending = any(c.get("status") != "COMPLETED" for c in checks)

    if has_failure:
        return "failure"
    if has_pending:
        return "pending"
    return "success"


async def fetch_pr_comments(repo: str, pr_number: int) -> list[dict]:
    """Fetch review comments on a PR."""
    output = await _run_gh(
        "api", f"repos/{repo}/pulls/{pr_number}/comments",
    )
    return json.loads(output)


async def draft_reply(comment_body: str, pr_title: str, knowledge_path: Optional[str] = None) -> str:
    """Use Claude to draft a reply to a review comment."""
    prompt = (
        f"You are replying to a code review comment on a PR titled '{pr_title}'. "
        f"The reviewer said:\n\n{comment_body}\n\n"
        f"Draft a concise, casual reply. If the comment is a valid concern, acknowledge it "
        f"and say you'll fix it. If it's a question, answer it. Keep it brief."
    )
    args = ["claude", "-p", prompt, "--output-format", "text"]
    if knowledge_path:
        args.extend(["--project-dir", knowledge_path])

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("Claude draft failed: %s", stderr.decode())
        return "(Draft generation failed — please write manually)"
    return stdout.decode().strip()


async def poll_prs(
    db_path: Path,
    config: dict,
    notify_fn: Optional[Callable[..., Awaitable[None]]] = None,
) -> None:
    """Main polling loop: fetch PRs, check CI, detect new comments, draft replies."""
    try:
        prs = await fetch_my_open_prs()
    except Exception as e:
        logger.error("Failed to fetch PRs: %s", e)
        await log_activity(db_path, module="pr_manager", action="poll_failed", detail=str(e))
        return

    if not prs:
        await log_activity(db_path, module="pr_manager", action="poll_complete", detail="No open PRs found")
        return

    for pr in prs:
        pr_url = pr["url"]
        repo = pr["repository"]["nameWithOwner"]
        pr_number = pr["number"]
        title = pr["title"]

        # Check CI status
        ci_status = await fetch_pr_check_status(repo, pr_number)
        old = await get_pr_status(db_path, pr_url)
        old_status = old["ci_status"] if old else None

        await upsert_pr_status(db_path, pr_url=pr_url, repo=repo, title=title, ci_status=ci_status)

        # Notify on status change
        if old_status and old_status != ci_status:
            msg = f"CI {ci_status} on PR #{pr_number}: {title}"
            await log_activity(db_path, module="pr_manager", action="ci_changed", detail=msg)
            if notify_fn:
                await notify_fn(msg, pr_url, "ci_changed")

        # Check for new comments
        try:
            comments = await fetch_pr_comments(repo, pr_number)
        except Exception as e:
            logger.error("Failed to fetch comments for PR #%d: %s", pr_number, e)
            continue

        # Find knowledge path for this repo
        knowledge_path = None
        for project in config.get("projects", []):
            if repo in project.get("repos", []):
                knowledge_path = project.get("knowledge_path")
                break

        for comment in comments:
            comment_id = str(comment.get("id", ""))
            # Skip if we already have a draft for this comment
            existing = await get_pending_drafts(db_path)
            if any(d["comment_id"] == comment_id for d in existing):
                continue

            body = comment.get("body", "")
            author = comment.get("user", {}).get("login", "unknown")

            # Draft a reply
            draft_text = await draft_reply(body, title, knowledge_path)
            await create_pr_draft(db_path, pr_url=pr_url, comment_id=comment_id, draft_text=draft_text)
            await log_activity(
                db_path, module="pr_manager", action="draft_created",
                detail=f"Draft reply to {author}'s comment on PR #{pr_number}",
            )
            if notify_fn:
                await notify_fn(
                    f"New review comment from {author} on PR #{pr_number} — draft reply ready",
                    pr_url, "draft_ready",
                )

    await log_activity(db_path, module="pr_manager", action="poll_complete",
                       detail=f"Checked {len(prs)} open PRs")
