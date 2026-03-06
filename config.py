"""Configuration loader for daily_automate."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

CONFIG_DIR = Path.home() / ".daily-automate"

DEFAULT_CONFIG: Dict[str, Any] = {
    "projects": [],
    "schedules": {
        "standup": "0 9 * * 1-5",
        "morning_reminder": "0 7 * * 1-5",
        "periodic_reminder": "0 */2 * * 1-5",
        "pr_poll": "*/5 * * * *",
        "pr_review": "0 * * * *",
        "jira_poll": "*/30 * * * *",
        "slack_digest": "0 8 * * 1-5",
        "weekly_summary": "0 16 * * 5",
        "metrics": "*/30 * * * *",
    },
    "slack": {
        "bot_token": "",
        "default_channel": "",
    },
    "server": {
        "host": "127.0.0.1",
        "port": 8080,
    },
    "tone": "casual",
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_dir: Path | None = None) -> Dict[str, Any]:
    config_dir = config_dir or CONFIG_DIR
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / "config.yaml"
    if config_file.exists():
        with open(config_file) as f:
            user_config = yaml.safe_load(f) or {}
        return _deep_merge(DEFAULT_CONFIG, user_config)

    return DEFAULT_CONFIG.copy()
