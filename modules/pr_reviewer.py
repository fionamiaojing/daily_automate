"""PR Reviewer module: reviews PRs assigned to you using Claude."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from db import create_review, log_activity
from modules.notifier import notify

logger = logging.getLogger("daily_automate.pr_reviewer")


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


async def fetch_review_requested_prs() -> list[dict]:
    """Fetch PRs where your review is requested."""
    output = await _run_cmd(
        "gh", "pr", "list", "--search", "review-requested:@me",
        "--state", "open",
        "--json", "url,number,title,repository,headRefName",
    )
    if not output:
        return []
    return json.loads(output)


async def review_pr_with_claude(pr_url: str, repo: str, pr_number: int, title: str) -> str:
    """Use Claude to review a PR."""
    prompt = (
        f"Review the pull request #{pr_number} in {repo} titled '{title}'. "
        f"URL: {pr_url}\n\n"
        f"Fetch the PR diff using `gh pr diff {pr_number} --repo {repo}` and provide:\n"
        f"1. A brief summary of the changes\n"
        f"2. Any concerns or issues found\n"
        f"3. Suggestions for improvement\n"
        f"4. Overall assessment (approve / request changes / comment)\n\n"
        f"Keep the review concise but thorough."
    )
    output = await _run_cmd("claude", "-p", prompt, "--output-format", "text")
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
        return []

    results = []
    for pr in prs:
        pr_url = pr["url"]
        repo = pr["repository"]["nameWithOwner"]
        pr_number = pr["number"]
        title = pr["title"]

        logger.info("Reviewing PR #%d: %s", pr_number, title)

        review_text = await review_pr_with_claude(pr_url, repo, pr_number, title)
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

    return results
