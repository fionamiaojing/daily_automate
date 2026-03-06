from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from modules.slack_digest import parse_digest_output, _normalize_channels


def test_normalize_channels_dict_format():
    raw = [
        {"name": "#ai-adoption", "id": "C05946FLL85"},
        {"name": "#ai-dev-tooling", "id": "C08D0TKLU3V"},
    ]
    result = _normalize_channels(raw)
    assert len(result) == 2
    assert result[0]["name"] == "#ai-adoption"
    assert result[0]["id"] == "C05946FLL85"


def test_normalize_channels_string_format():
    raw = ["#general", "#random"]
    result = _normalize_channels(raw)
    assert len(result) == 2
    assert result[0]["name"] == "#general"
    assert result[0]["id"] == ""


def test_parse_digest_output():
    output = "1. New Claude model announced (#ai-adoption)\n2. MCP server update (#proj-foundations-mcp)"
    result = parse_digest_output(output)
    assert "Claude model" in result
    assert "MCP" in result


def test_parse_digest_output_empty():
    result = parse_digest_output("")
    assert "failed" in result.lower() or "no digest" in result.lower()
