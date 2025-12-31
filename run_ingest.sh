#!/usr/bin/env bash

# run_ingest.sh
# Run the ingestion (manage.py scrape) and log output

set -euo pipefail

cd "$(dirname "$0")"

mkdir -p logs

# Activate virtualenv
## Determine whether we're under WSL so we avoid sourcing Windows activate scripts
IS_WSL=false
if [ -f /proc/version ] && grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
fi

# Choose venv dir: if under WSL and repo is on /mnt/*, prefer a WSL-local venv cache
if [ "$IS_WSL" = true ] && [[ "$PWD" == /mnt/* ]]; then
    REPO_NAME="$(basename "$PWD")"
    VENV_DIR="$HOME/.cache/${REPO_NAME}_venv"
else
    VENV_DIR="venv"
fi

# Prefer to run the venv python directly instead of sourcing activate (avoids CRLF issues)
if [ -x "$VENV_DIR/bin/python" ]; then
    PYTHON_CMD="$VENV_DIR/bin/python"
elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then
    PYTHON_CMD="$VENV_DIR/Scripts/python.exe"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi

LOGFILE=logs/ingest.log
echo "[$(date)] Using python: $PYTHON_CMD" | tee -a "$LOGFILE"

export PYTHONPATH="${PYTHONPATH:-}:$PWD"

echo "[$(date)] 🚀 Starting Ingest..." | tee -a "$LOGFILE"

# Run the Scraper via manage.py (click command: scrape)
if "$PYTHON_CMD" manage.py scrape 2>&1 | tee -a "$LOGFILE"; then
    echo "[$(date)] ✅ Ingest Success" | tee -a "$LOGFILE"
else
    echo "[$(date)] ❌ Ingest FAILED" | tee -a "$LOGFILE"
    exit 1
fi