#!/usr/bin/env bash

# run_decision.sh
# Runs the daily decision engine and appends output to logs/decision.log


set -euo pipefail

# Set ROOT_DIR to the directory of this script
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$ROOT_DIR"

mkdir -p "$ROOT_DIR/logs"

IS_WSL=false
if [ -f /proc/version ] && grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
fi

if [ "$IS_WSL" = true ] && [[ "$ROOT_DIR" == /mnt/* ]]; then
    REPO_NAME="$(basename "$ROOT_DIR")"
    VENV_DIR="$HOME/.cache/${REPO_NAME}_venv"
else
    VENV_DIR="$ROOT_DIR/venv"
fi

if [ -x "$VENV_DIR/bin/python" ]; then
    PYTHON_CMD="$VENV_DIR/bin/python"
elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then
    PYTHON_CMD="$VENV_DIR/Scripts/python.exe"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi


export PYTHONPATH="${PYTHONPATH:-}:$ROOT_DIR"

LOGFILE="$ROOT_DIR/logs/decision.log"
echo "[$(date)] 🏆 Running Daily Decision Engine..." | tee -a "$LOGFILE"
echo "[$(date)] Using python: $PYTHON_CMD" | tee -a "$LOGFILE"

# Run the main orchestrator using the explicit python
"$PYTHON_CMD" -u main.py >> "$LOGFILE" 2>&1 || {
    echo "[$(date)] ❌ Decision Cycle FAILED" | tee -a "$LOGFILE"
    exit 1
}

echo "[$(date)] ✅ Decision Cycle Complete" | tee -a "$LOGFILE"