from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from modules.standup import gather_commits, gather_open_prs, build_standup_prompt


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


SAMPLE_COMMITS = "abc1234 Fix login bug\ndef5678 Add unit tests"

SAMPLE_PRS = [
    {"url": "https://github.com/org/repo/pull/1", "title": "Fix bug", "number": 1,
     "repository": {"nameWithOwner": "org/repo"}},
]


@patch("modules.standup._run_cmd")
def test_gather_commits(mock_cmd):
    mock_cmd.return_value = SAMPLE_COMMITS
    commits = run(gather_commits(repos=["org/repo"], cwd="/tmp"))
    assert "Fix login bug" in commits


@patch("modules.standup._run_cmd")
def test_gather_open_prs(mock_cmd):
    mock_cmd.return_value = json.dumps(SAMPLE_PRS)
    prs = run(gather_open_prs())
    assert "Fix bug" in prs


def test_build_standup_prompt():
    prompt = build_standup_prompt(
        commits="abc Fix thing",
        prs="PR #1: Fix thing",
        jira="PROJ-123: In Progress",
        template_path=None,
    )
    assert "Fix thing" in prompt
    assert "Yesterday" in prompt
    assert "casual" in prompt.lower() or "teammate" in prompt.lower()
