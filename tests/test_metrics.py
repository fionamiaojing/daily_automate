# tests/test_metrics.py
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from modules.metrics import run_check_command, parse_numeric_output, evaluate_threshold
from db import init_db, create_metrics_check, get_metrics_checks


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_parse_numeric_output():
    assert parse_numeric_output("123.45") == 123.45
    assert parse_numeric_output("  42  \n") == 42.0
    assert parse_numeric_output("result: 99.9") == 99.9
    assert parse_numeric_output("no numbers here") is None
    assert parse_numeric_output("") is None


def test_evaluate_threshold():
    assert evaluate_threshold(value=600.0, threshold=500.0) is True  # exceeded
    assert evaluate_threshold(value=400.0, threshold=500.0) is False  # OK
    assert evaluate_threshold(value=500.0, threshold=500.0) is False  # equal = OK


@patch("modules.metrics._run_shell")
def test_run_check_command(mock_shell):
    mock_shell.return_value = "123.45"
    result = run(run_check_command("echo 123.45"))
    assert result == "123.45"
