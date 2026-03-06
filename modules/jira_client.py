"""JIRA client using Claude's jira skill (MCP-based, no credentials needed)."""
from __future__ import annotations

import asyncio
import json
import logging
import re

logger = logging.getLogger("daily_automate.jira_client")

TICKET_PATTERN = re.compile(r"([A-Z][A-Z0-9]+-\d+)")


def extract_ticket_key(text: str) -> str | None:
    """Extract a JIRA ticket key from text (e.g., PROJ-123-fix-bug -> PROJ-123)."""
    match = TICKET_PATTERN.search(text)
    return match.group(1) if match else None


async def _run_claude(prompt: str) -> str:
    """Run a Claude command with jira skill access."""
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", prompt, "--output-format", "text",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("Claude jira command failed: %s", stderr.decode())
        return ""
    return stdout.decode().strip()


class JiraClient:
    """JIRA client that delegates to Claude's jira skill."""

    async def get_issue(self, ticket_key: str) -> dict:
        """Fetch a JIRA issue via the jira skill.

        Returns dict with at minimum: fields.status.name, fields.summary
        """
        output = await _run_claude(
            f"Use the jira skill to get ticket {ticket_key}. "
            f"Return ONLY a JSON object with this exact format, no other text:\n"
            f'{{"fields": {{"status": {{"name": "<status>"}}, "summary": "<summary>"}}}}'
        )
        try:
            return json.loads(output)
        except (json.JSONDecodeError, ValueError):
            # Try to extract JSON from mixed output
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        return json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
            logger.warning("Could not parse JIRA response for %s: %s", ticket_key, output[:200])
            return {"fields": {"status": {"name": "unknown"}, "summary": ""}}

    async def transition_issue(self, ticket_key: str, target_status: str) -> bool:
        """Transition a JIRA issue to a target status."""
        output = await _run_claude(
            f"Use the jira skill to transition ticket {ticket_key} to '{target_status}'. "
            f"If successful, respond with exactly 'OK'. If it fails, explain why."
        )
        success = "ok" in output.lower()[:20]
        if not success:
            logger.warning("Transition of %s to %s may have failed: %s", ticket_key, target_status, output[:200])
        return success
