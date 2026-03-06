"""JIRA REST API client."""
from __future__ import annotations

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger("daily_automate.jira_client")

TICKET_PATTERN = re.compile(r"([A-Z][A-Z0-9]+-\d+)")


def extract_ticket_key(branch_name: str) -> str | None:
    """Extract a JIRA ticket key from a branch name (e.g., PROJ-123-fix-bug -> PROJ-123)."""
    match = TICKET_PATTERN.search(branch_name)
    return match.group(1) if match else None


class JiraClient:
    """Async JIRA REST API v3 client."""

    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.auth = (email, api_token)

    async def get_issue(self, ticket_key: str) -> dict:
        """Fetch a JIRA issue."""
        async with httpx.AsyncClient(auth=self.auth) as client:
            resp = await client.get(
                f"{self.base_url}/rest/api/3/issue/{ticket_key}",
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    async def transition_issue(self, ticket_key: str, target_status: str) -> bool:
        """Transition an issue to a target status. Returns True if successful."""
        async with httpx.AsyncClient(auth=self.auth) as client:
            # Get available transitions
            resp = await client.get(
                f"{self.base_url}/rest/api/3/issue/{ticket_key}/transitions",
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            transitions = resp.json().get("transitions", [])

            # Find matching transition
            transition_id = None
            for t in transitions:
                if t["name"].lower() == target_status.lower():
                    transition_id = t["id"]
                    break

            if not transition_id:
                logger.warning("No transition to '%s' found for %s. Available: %s",
                    target_status, ticket_key, [t["name"] for t in transitions])
                return False

            # Execute transition
            resp = await client.post(
                f"{self.base_url}/rest/api/3/issue/{ticket_key}/transitions",
                json={"transition": {"id": transition_id}},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return True

    async def create_subtask(self, parent_key: str, project_key: str, summary: str, description: str = "") -> dict:
        """Create a subtask under a parent issue."""
        async with httpx.AsyncClient(auth=self.auth) as client:
            resp = await client.post(
                f"{self.base_url}/rest/api/3/issue",
                json={
                    "fields": {
                        "project": {"key": project_key},
                        "parent": {"key": parent_key},
                        "summary": summary,
                        "issuetype": {"name": "Sub-task"},
                    }
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_project_issues(self, project_key: str, status: str | None = None, limit: int = 20) -> list[dict]:
        """Fetch issues from a JIRA project via JQL."""
        jql = f'project = "{project_key}"'
        if status:
            jql += f' AND status = "{status}"'
        jql += " ORDER BY updated DESC"

        async with httpx.AsyncClient(auth=self.auth) as client:
            resp = await client.get(
                f"{self.base_url}/rest/api/3/search",
                params={"jql": jql, "maxResults": limit, "fields": "key,summary,status,assignee,updated"},
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            return resp.json().get("issues", [])
