#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/exercise-arcade}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_FILE="app.py"

cd "$APP_DIR"

if [ ! -d "venv" ]; then
  "$PYTHON_BIN" -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

exec python "$APP_FILE"
