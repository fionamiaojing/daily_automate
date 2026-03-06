from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from modules.pr_reviewer import fetch_review_requested_prs, parse_review_output


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


SAMPLE_REVIEW_PRS = [
    {"url": "https://github.com/org/repo/pull/5", "title": "Add feature", "number": 5,
     "repository": {"nameWithOwner": "org/repo"}, "headRefName": "feature-branch"},
]


@patch("modules.pr_reviewer._run_cmd")
def test_fetch_review_requested_prs(mock_cmd):
    mock_cmd.return_value = json.dumps(SAMPLE_REVIEW_PRS)
    prs = run(fetch_review_requested_prs())
    assert len(prs) == 1
    assert prs[0]["title"] == "Add feature"


def test_parse_review_output_with_content():
    output = "## Summary\nThis PR adds a new feature.\n\n## Suggestions\n- Fix typo on line 42"
    result = parse_review_output(output)
    assert "Summary" in result
    assert "Fix typo" in result


def test_parse_review_output_empty():
    result = parse_review_output("")
    assert "no review" in result.lower() or "failed" in result.lower()
