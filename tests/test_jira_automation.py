from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

from modules.jira_automation import link_prs_to_tickets, should_transition
from db import init_db, upsert_pr_status


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_should_transition_merged():
    assert should_transition(pr_state="merged", current_jira_status="In Progress") == "Done"


def test_should_transition_open():
    assert should_transition(pr_state="open", current_jira_status="To Do") == "In Progress"


def test_should_transition_no_change():
    assert should_transition(pr_state="open", current_jira_status="In Progress") is None


def test_link_prs_to_tickets(db_path):
    run(init_db(db_path))
    run(upsert_pr_status(db_path, pr_url="https://github.com/org/repo/pull/1", repo="org/repo", title="PROJ-123 Fix bug", ci_status="success"))
    run(upsert_pr_status(db_path, pr_url="https://github.com/org/repo/pull/2", repo="org/repo", title="no ticket here", ci_status="success"))

    linked = run(link_prs_to_tickets(db_path, projects=["PROJ"]))
    assert len(linked) == 1
    assert linked[0]["ticket_key"] == "PROJ-123"
