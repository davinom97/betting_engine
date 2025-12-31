#!/usr/bin/env bash

# run_feature_archiver.sh
# Compute and archive features (manage.py compute_features)


set -euo pipefail

# Set ROOT_DIR to the directory of this script
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$ROOT_DIR"

mkdir -p "$ROOT_DIR/logs"

# Activate virtualenv
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

echo "[$(date)] Using python: $PYTHON_CMD" | tee -a "$LOGFILE"

export PYTHONPATH="${PYTHONPATH:-}:$PWD"

LOGFILE="$ROOT_DIR/logs/features.log"
echo "[$(date)] 🧠 Running Feature Archiver..." | tee -a "$LOGFILE"

# Look back 24 hours to ensure we catch recent games and finalized velocities
if python manage.py compute_features --hours 24 2>&1 | tee -a "$LOGFILE"; then
	echo "[$(date)] ✅ Feature Archiver Complete" | tee -a "$LOGFILE"
else
	echo "[$(date)] ❌ Feature Archiver FAILED" | tee -a "$LOGFILE"
	exit 1
fi