from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from modules.slack_digest import build_digest_prompt, parse_digest_output


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_build_digest_prompt_with_channels():
    prompt = build_digest_prompt(channels=["#eng-feed", "#ai-news"])
    assert "#eng-feed" in prompt
    assert "#ai-news" in prompt
    assert "digest" in prompt.lower()


def test_build_digest_prompt_empty():
    prompt = build_digest_prompt(channels=[])
    assert "no" in prompt.lower() or "digest" in prompt.lower()


def test_parse_digest_output():
    output = "## #eng-feed\n- New PR merged\n\n## #ai-news\n- GPT-5 announced"
    result = parse_digest_output(output)
    assert "eng-feed" in result
    assert "GPT-5" in result


def test_parse_digest_output_empty():
    result = parse_digest_output("")
    assert "failed" in result.lower() or "no digest" in result.lower()
