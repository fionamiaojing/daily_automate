from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from modules.reminders import build_morning_summary, gather_pending_review_prs
from db import init_db


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


SAMPLE_REVIEW_PRS = [
    {"url": "https://github.com/org/repo/pull/5", "title": "Add feature", "number": 5},
]


@patch("modules.reminders._run_cmd")
def test_gather_pending_review_prs(mock_cmd):
    mock_cmd.return_value = json.dumps(SAMPLE_REVIEW_PRS)
    prs = run(gather_pending_review_prs())
    assert len(prs) == 1
    assert prs[0]["title"] == "Add feature"


def test_build_morning_summary():
    summary = build_morning_summary(
        my_prs=[{"title": "Fix bug", "ci_status": "success", "pr_url": "url1"}],
        review_prs=[{"title": "Add feature", "number": 5, "url": "url2"}],
    )
    assert "Fix bug" in summary
    assert "Add feature" in summary


def test_build_morning_summary_empty():
    summary = build_morning_summary(my_prs=[], review_prs=[])
    assert "nothing" in summary.lower() or "no " in summary.lower() or "clear" in summary.lower()
