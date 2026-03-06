from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from modules.pr_manager import (
    fetch_my_open_prs,
    fetch_pr_check_status,
    fetch_pr_comments,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


SAMPLE_PRS = [
    {
        "url": "https://github.com/org/repo/pull/1",
        "number": 1,
        "title": "Fix bug",
        "repository": {"nameWithOwner": "org/repo", "name": "repo"},
    }
]


@patch("modules.pr_manager._run_gh")
def test_fetch_my_open_prs(mock_gh):
    mock_gh.return_value = json.dumps(SAMPLE_PRS)
    prs = run(fetch_my_open_prs())
    assert len(prs) == 1
    assert prs[0]["title"] == "Fix bug"
    mock_gh.assert_called_once()


@patch("modules.pr_manager._run_gh")
def test_fetch_pr_check_status_success(mock_gh):
    checks = {"statusCheckRollup": [
        {"name": "build", "status": "COMPLETED", "conclusion": "SUCCESS"},
        {"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"},
    ]}
    mock_gh.return_value = json.dumps(checks)
    status = run(fetch_pr_check_status("org/repo", 1))
    assert status == "success"


@patch("modules.pr_manager._run_gh")
def test_fetch_pr_check_status_failure(mock_gh):
    checks = {"statusCheckRollup": [
        {"name": "build", "status": "COMPLETED", "conclusion": "FAILURE"},
    ]}
    mock_gh.return_value = json.dumps(checks)
    status = run(fetch_pr_check_status("org/repo", 1))
    assert status == "failure"


@patch("modules.pr_manager._run_gh")
def test_fetch_pr_check_status_pending(mock_gh):
    checks = {"statusCheckRollup": [
        {"name": "build", "status": "IN_PROGRESS", "conclusion": None},
    ]}
    mock_gh.return_value = json.dumps(checks)
    status = run(fetch_pr_check_status("org/repo", 1))
    assert status == "pending"


@patch("modules.pr_manager._run_gh")
def test_fetch_pr_comments(mock_gh):
    comments = [
        {"id": 123, "body": "Please fix this", "user": {"login": "reviewer"}, "created_at": "2026-03-05T10:00:00Z"},
    ]
    mock_gh.return_value = json.dumps(comments)
    result = run(fetch_pr_comments("org/repo", 1))
    assert len(result) == 1
    assert result[0]["body"] == "Please fix this"
