"""PR Reviewer module: reviews PRs using the /review-prs skill.

Delegates the actual review work to Claude's /review-prs skill, which handles
fetching diffs, analyzing code, and producing structured reviews. This module
manages the orchestration: finding PRs, storing results, and sending notifications.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from db import create_review, log_activity
from modules.notifier import notify

logger = logging.getLogger("daily_automate.pr_reviewer")


async def _run_cmd(*args: str, timeout: int = 300) -> str:
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


async def fetch_review_requested_prs() -> list[dict]:
    """Fetch PRs where your review is requested across all repos."""
    output = await _run_cmd(
        "gh", "search", "prs", "--review-requested", "@me",
        "--state", "open",
        "--json", "url,number,title,repository",
    )
    if not output:
        return []
    return json.loads(output)


async def review_pr_with_skill(pr_url: str, repo: str, pr_number: int) -> str:
    """Use the /review-prs skill to review a single PR."""
    output = await _run_cmd(
        "claude", "-p",
        f"/review-prs {pr_url}",
        "--output-format", "text",
        timeout=600,  # reviews can take a while for large PRs
    )
    return output if output else "(Review generation failed)"


def parse_review_output(output: str) -> str:
    """Parse and clean Claude's review output."""
    if not output or not output.strip():
        return "(No review output — generation may have failed)"
    return output.strip()


async def review_prs(db_path: Path, config: dict) -> list[dict]:
    """Review all PRs requesting your review.

    Returns list of review results.
    """
    prs = await fetch_review_requested_prs()
    if not prs:
        logger.info("No PRs requesting review")
        await log_activity(db_path, module="pr_reviewer", action="review_complete", detail="No PRs requesting review")
        return []

    results = []
    for pr in prs:
        pr_url = pr["url"]
        repo = pr["repository"]["nameWithOwner"]
        pr_number = pr["number"]
        title = pr["title"]

        logger.info("Reviewing PR #%d: %s", pr_number, title)

        review_text = await review_pr_with_skill(pr_url, repo, pr_number)
        review_text = parse_review_output(review_text)

        # Save to DB
        await create_review(db_path, pr_url=pr_url, review_summary=review_text)
        await log_activity(
            db_path, module="pr_reviewer", action="reviewed",
            detail=f"Reviewed PR #{pr_number}: {title}",
        )

        # Notify Slack
        msg = f"*PR Review — #{pr_number}: {title}*\n{repo}\n\n{review_text}"
        await notify(config, message=msg)

        results.append({"pr_url": pr_url, "title": title, "review": review_text})

    await log_activity(db_path, module="pr_reviewer", action="review_complete",
                       detail=f"Reviewed {len(results)} PRs")
    return results
