from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
import aiosqlite

from db import (
    init_db, log_activity, get_recent_activity,
    upsert_pr_status, get_all_pr_status, get_pr_status,
    create_pr_draft, get_pending_drafts, update_draft_status,
)


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_init_db_creates_tables(db_path):
    run(init_db(db_path))
    async def check():
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in await cursor.fetchall()]
            return tables
    tables = run(check())
    assert "activity_log" in tables
    assert "pr_drafts" in tables
    assert "pr_status" in tables
    assert "standups" in tables
    assert "reminders" in tables


def test_init_db_is_idempotent(db_path):
    run(init_db(db_path))
    run(init_db(db_path))


def test_log_activity_and_retrieve(db_path):
    run(init_db(db_path))
    run(log_activity(db_path, module="test", action="did_thing", detail="some detail"))
    run(log_activity(db_path, module="test", action="did_another", detail="more detail"))
    activities = run(get_recent_activity(db_path, limit=10))
    assert len(activities) == 2
    assert activities[0]["action"] == "did_another"
    assert activities[1]["action"] == "did_thing"
    assert activities[0]["module"] == "test"


def test_get_recent_activity_respects_limit(db_path):
    run(init_db(db_path))
    for i in range(5):
        run(log_activity(db_path, module="test", action=f"action_{i}", detail=""))
    activities = run(get_recent_activity(db_path, limit=3))
    assert len(activities) == 3


def test_upsert_pr_status_insert(db_path):
    run(init_db(db_path))
    run(upsert_pr_status(db_path, pr_url="https://github.com/org/repo/pull/1", repo="org/repo", title="Fix bug", ci_status="pending"))
    prs = run(get_all_pr_status(db_path))
    assert len(prs) == 1
    assert prs[0]["ci_status"] == "pending"
    assert prs[0]["title"] == "Fix bug"


def test_upsert_pr_status_update(db_path):
    run(init_db(db_path))
    run(upsert_pr_status(db_path, pr_url="https://github.com/org/repo/pull/1", repo="org/repo", title="Fix bug", ci_status="pending"))
    run(upsert_pr_status(db_path, pr_url="https://github.com/org/repo/pull/1", repo="org/repo", title="Fix bug", ci_status="success"))
    prs = run(get_all_pr_status(db_path))
    assert len(prs) == 1
    assert prs[0]["ci_status"] == "success"


def test_get_pr_status_single(db_path):
    run(init_db(db_path))
    run(upsert_pr_status(db_path, pr_url="https://github.com/org/repo/pull/1", repo="org/repo", title="Fix", ci_status="success"))
    pr = run(get_pr_status(db_path, pr_url="https://github.com/org/repo/pull/1"))
    assert pr is not None
    assert pr["ci_status"] == "success"


def test_get_pr_status_not_found(db_path):
    run(init_db(db_path))
    pr = run(get_pr_status(db_path, pr_url="https://github.com/org/repo/pull/999"))
    assert pr is None


def test_create_and_get_pending_drafts(db_path):
    run(init_db(db_path))
    run(create_pr_draft(db_path, pr_url="https://github.com/org/repo/pull/1", comment_id="c1", draft_text="Looks good, thanks!"))
    run(create_pr_draft(db_path, pr_url="https://github.com/org/repo/pull/1", comment_id="c2", draft_text="Will fix."))
    drafts = run(get_pending_drafts(db_path))
    assert len(drafts) == 2
    assert drafts[0]["status"] == "pending"


def test_update_draft_status(db_path):
    run(init_db(db_path))
    run(create_pr_draft(db_path, pr_url="https://github.com/org/repo/pull/1", comment_id="c1", draft_text="Thanks!"))
    drafts = run(get_pending_drafts(db_path))
    draft_id = drafts[0]["id"]
    run(update_draft_status(db_path, draft_id=draft_id, status="approved"))
    updated_drafts = run(get_pending_drafts(db_path))
    assert len(updated_drafts) == 0


def test_update_draft_preserves_other_drafts(db_path):
    run(init_db(db_path))
    run(create_pr_draft(db_path, pr_url="https://github.com/org/repo/pull/1", comment_id="c1", draft_text="Reply 1"))
    run(create_pr_draft(db_path, pr_url="https://github.com/org/repo/pull/1", comment_id="c2", draft_text="Reply 2"))
    drafts = run(get_pending_drafts(db_path))
    run(update_draft_status(db_path, draft_id=drafts[0]["id"], status="approved"))
    remaining = run(get_pending_drafts(db_path))
    assert len(remaining) == 1
