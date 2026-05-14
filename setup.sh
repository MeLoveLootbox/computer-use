#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

echo "=== ComputerUse MCP Setup ==="
echo ""

# Pick Python >= 3.10
PYTHON=""
for p in python3.12 python3.11 python3.10 python3; do
  if command -v "$p" >/dev/null 2>&1; then
    if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      PYTHON="$p"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "ERROR: Python >= 3.10 not found. Install it: brew install python@3.12"
  exit 1
fi

echo "Python: $PYTHON ($($PYTHON --version))"

# Create venv
if [ ! -x "$VENV/bin/python3" ]; then
  echo "Creating venv..."
  "$PYTHON" -m venv "$VENV"
fi

# Install deps
echo "Installing Python dependencies..."
"$VENV/bin/pip" install -r "$SCRIPT_DIR/servers/requirements.txt" --disable-pip-version-check -q

# Install Chromium
echo "Installing Chromium browser..."
"$VENV/bin/playwright" install chromium

echo ""
echo "=== Setup complete ==="
echo ""
echo "Add this to your agent config:"
echo ""
PYTHON_PATH="$VENV/bin/python3"
MCP_PATH="$SCRIPT_DIR/servers/computer_use_mcp.py"

cat <<CONFIG
--- OpenCode (opencode.json) ---
"mcp": {
  "computerUse": {
    "type": "local",
    "command": ["$PYTHON_PATH", "$MCP_PATH"],
    "enabled": true
  }
}

--- Claude Code (~/.claude.json) ---
"mcpServers": {
  "computerUse": {
    "command": "$PYTHON_PATH",
    "args": ["$MCP_PATH"]
  }
}
CONFIG
echo ""
echo "Restart your agent to activate ComputerUse."
