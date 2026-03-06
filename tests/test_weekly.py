# tests/test_weekly.py
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from modules.weekly import build_weekly_prompt, parse_weekly_output


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_build_weekly_prompt():
    prompt = build_weekly_prompt(
        prs_summary="3 PRs merged, 1 open",
        standups_summary="5 standups generated",
        jira_summary="2 tickets transitioned",
        metrics_summary="All checks passing",
    )
    assert "3 PRs merged" in prompt
    assert "5 standups" in prompt
    assert "summary" in prompt.lower() or "weekly" in prompt.lower()


def test_build_weekly_prompt_empty():
    prompt = build_weekly_prompt(
        prs_summary="", standups_summary="", jira_summary="", metrics_summary=""
    )
    assert "summary" in prompt.lower() or "weekly" in prompt.lower()


def test_parse_weekly_output():
    output = "## This Week\nMerged 3 PRs, resolved 2 JIRA tickets."
    result = parse_weekly_output(output)
    assert "3 PRs" in result


def test_parse_weekly_output_empty():
    result = parse_weekly_output("")
    assert "failed" in result.lower() or "no" in result.lower()
