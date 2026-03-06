from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Patch config dir to temp before importing server
_tmpdir = tempfile.mkdtemp()
_test_config_dir = Path(_tmpdir)

# Create required subdirs
(_test_config_dir / "logs").mkdir(parents=True, exist_ok=True)

with patch("config.CONFIG_DIR", _test_config_dir):
    from server import app

from fastapi.testclient import TestClient

# Use context manager so lifespan runs (init_db creates tables)
_client_ctx = TestClient(app)
client = _client_ctx.__enter__()


def teardown_module():
    _client_ctx.__exit__(None, None, None)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "uptime" in data


def test_dashboard_returns_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "daily_automate" in response.text


def test_activity_api_returns_list():
    response = client.get("/api/activity")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_trigger_endpoint_exists():
    response = client.post("/api/trigger/standup")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
