"""Standup generator: gathers data and generates standup via Claude."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from db import create_standup, log_activity
from modules.notifier import notify

logger = logging.getLogger("daily_automate.standup")

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
DEFAULT_TEMPLATE = PROMPTS_DIR / "standup.txt"


async def _run_cmd(*args: str, cwd: str | None = None) -> str:
    """Run a shell command and return stdout."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("Command failed: %s\n%s", " ".join(args), stderr.decode())
        return ""
    return stdout.decode().strip()


async def gather_commits(repos: list[str], cwd: str | None = None) -> str:
    """Gather git commits from the last 24 hours across configured repos."""
    all_commits = []
    for repo in repos:
        output = await _run_cmd(
            "git", "log", "--oneline", "--since=24 hours ago", "--author=@me",
            cwd=cwd,
        )
        if output:
            all_commits.append(f"### {repo}\n{output}")
    return "\n\n".join(all_commits) if all_commits else "(no commits in last 24h)"


async def gather_open_prs() -> str:
    """Gather open PRs authored by you."""
    output = await _run_cmd(
        "gh", "pr", "list", "--author", "@me", "--state", "open",
        "--json", "url,number,title,repository",
    )
    if not output:
        return "(no open PRs)"
    prs = json.loads(output)
    lines = []
    for pr in prs:
        repo = pr["repository"]["nameWithOwner"]
        lines.append(f"- PR #{pr['number']}: {pr['title']} ({repo})")
    return "\n".join(lines) if lines else "(no open PRs)"


def build_standup_prompt(
    commits: str,
    prs: str,
    jira: str = "(JIRA integration coming soon)",
    template_path: Path | None = None,
) -> str:
    """Build the standup prompt from gathered data and template."""
    template_file = template_path or DEFAULT_TEMPLATE
    if template_file.exists():
        template = template_file.read_text()
    else:
        template = (
            "You are generating a daily standup update. Use a casual, conversational tone — "
            "like talking to a teammate.\n\n"
            "## Git Commits\n{commits}\n\n## Open PRs\n{prs}\n\n## JIRA Activity\n{jira}\n\n"
            "Generate a standup with these sections:\n"
            "- **Yesterday**: What was accomplished\n"
            "- **Today**: What's in progress\n"
            "- **Blockers**: Any issues\n\n"
            "Keep it concise — 3-5 bullet points total."
        )
    return template.format(commits=commits, prs=prs, jira=jira)


async def generate_standup(
    db_path: Path,
    config: dict,
    slack_channels: list[str] | None = None,
) -> str:
    """Generate a standup update and save it.

    Returns the standup text.
    """
    # Gather data
    repos = []
    knowledge_paths = []
    for project in config.get("projects", []):
        repos.extend(project.get("repos", []))
        if project.get("knowledge_path"):
            knowledge_paths.append(project["knowledge_path"])

    commits = await gather_commits(repos, cwd=knowledge_paths[0] if knowledge_paths else None)
    prs = await gather_open_prs()

    # Build prompt
    prompt = build_standup_prompt(commits=commits, prs=prs)

    # Call Claude
    args = ["claude", "-p", prompt, "--output-format", "text"]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.error("Claude standup generation failed: %s", stderr.decode())
        standup_text = "(Standup generation failed — please write manually)"
    else:
        standup_text = stdout.decode().strip()

    # Save to DB
    today = datetime.now().strftime("%Y-%m-%d")
    await create_standup(db_path, date=today, content=standup_text)
    await log_activity(db_path, module="standup", action="generated", detail=f"Standup for {today}")

    # Notify Slack
    await notify(config, message=f"*Daily Standup — {today}*\n\n{standup_text}")

    return standup_text
