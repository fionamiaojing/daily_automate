import tempfile
from pathlib import Path

import pytest
import yaml

from config import load_config, DEFAULT_CONFIG


def test_load_config_returns_defaults_when_no_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = load_config(config_dir=Path(tmpdir))
        assert cfg["schedules"]["standup"] == "0 9 * * 1-5"
        assert cfg["tone"] == "casual"
        assert cfg["server"]["port"] == 8080


def test_load_config_merges_user_values():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        config_path.write_text(yaml.dump({
            "server": {"port": 9090},
            "tone": "professional",
        }))
        cfg = load_config(config_dir=Path(tmpdir))
        assert cfg["server"]["port"] == 9090
        assert cfg["tone"] == "professional"
        assert cfg["schedules"]["standup"] == "0 9 * * 1-5"


def test_load_config_creates_config_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        new_dir = Path(tmpdir) / "subdir"
        cfg = load_config(config_dir=new_dir)
        assert new_dir.exists()


def test_default_config_has_all_schedule_keys():
    schedules = DEFAULT_CONFIG["schedules"]
    expected = [
        "standup", "morning_reminder", "periodic_reminder",
        "pr_poll", "pr_review", "jira_poll", "slack_digest",
        "weekly_summary", "metrics",
    ]
    for key in expected:
        assert key in schedules, f"Missing schedule key: {key}"
