from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
import aiosqlite

from db import init_db, log_activity, get_recent_activity


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
