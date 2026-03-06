from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from modules.pr_manager import (
    fetch_my_open_prs,
    fetch_pr_details,
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
def test_fetch_pr_details_success(mock_gh):
    data = {"statusCheckRollup": [
        {"name": "build", "status": "COMPLETED", "conclusion": "SUCCESS"},
        {"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"},
    ], "headRefName": "fiona/PACHI-123-fix", "state": "OPEN"}
    mock_gh.return_value = json.dumps(data)
    details = run(fetch_pr_details("org/repo", 1))
    assert details["ci_status"] == "success"
    assert details["head_branch"] == "fiona/PACHI-123-fix"
    assert details["state"] == "open"


@patch("modules.pr_manager._run_gh")
def test_fetch_pr_details_failure(mock_gh):
    data = {"statusCheckRollup": [
        {"name": "build", "status": "COMPLETED", "conclusion": "FAILURE"},
    ], "headRefName": "fix-bug", "state": "OPEN"}
    mock_gh.return_value = json.dumps(data)
    details = run(fetch_pr_details("org/repo", 1))
    assert details["ci_status"] == "failure"


@patch("modules.pr_manager._run_gh")
def test_fetch_pr_details_merged(mock_gh):
    data = {"statusCheckRollup": [
        {"name": "build", "status": "COMPLETED", "conclusion": "SUCCESS"},
    ], "headRefName": "feature", "state": "MERGED"}
    mock_gh.return_value = json.dumps(data)
    details = run(fetch_pr_details("org/repo", 1))
    assert details["ci_status"] == "success"
    assert details["state"] == "merged"


@patch("modules.pr_manager._run_gh")
def test_fetch_pr_comments(mock_gh):
    comments = [
        {"id": 123, "body": "Please fix this", "user": {"login": "reviewer"}, "created_at": "2026-03-05T10:00:00Z"},
    ]
    mock_gh.return_value = json.dumps(comments)
    result = run(fetch_pr_comments("org/repo", 1))
    assert len(result) == 1
    assert result[0]["body"] == "Please fix this"
