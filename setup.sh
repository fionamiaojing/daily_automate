#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="$HOME/.daily-automate"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "=== daily_automate Setup ==="
echo ""

# 1. Create config directory
echo "Creating config directory at $CONFIG_DIR ..."
mkdir -p "$CONFIG_DIR/logs"
mkdir -p "$CONFIG_DIR/prompts"

# 2. Create venv and install dependencies
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    if command -v uv &>/dev/null; then
        uv venv "$VENV_DIR"
    else
        python3 -m venv "$VENV_DIR"
    fi
fi

echo "Installing dependencies..."
if command -v uv &>/dev/null; then
    uv pip install --python "$VENV_DIR/bin/python" -r "$SCRIPT_DIR/requirements.txt"
else
    "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
fi

# 3. Copy example config if no config exists
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    cp "$SCRIPT_DIR/config.example.yaml" "$CONFIG_DIR/config.yaml"
    echo ""
    echo "=== ACTION REQUIRED ==="
    echo "Edit your config at: $CONFIG_DIR/config.yaml"
    echo "  - Add your project repos, Slack channels, JIRA project"
    echo "  - Add your Slack bot token"
    echo ""
else
    echo "Config already exists at $CONFIG_DIR/config.yaml (not overwritten)."
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "  Run (foreground):  $VENV_DIR/bin/python $SCRIPT_DIR/server.py run"
echo "  Start (daemon):    $VENV_DIR/bin/python $SCRIPT_DIR/server.py start"
echo "  Stop:              $VENV_DIR/bin/python $SCRIPT_DIR/server.py stop"
echo "  Dashboard:         http://localhost:8080"
