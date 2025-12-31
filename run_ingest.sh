#!/usr/bin/env bash

# run_ingest.sh
# Run the ingestion (manage.py scrape) and log output

set -euo pipefail

cd "$(dirname "$0")"

mkdir -p logs

# Activate virtualenv
if [ -f "venv/bin/activate" ]; then
    # shellcheck source=/dev/null
    source "venv/bin/activate"
elif [ -f ".venv/bin/activate" ]; then
    # shellcheck source=/dev/null
    source ".venv/bin/activate"
elif [ -f "venv/Scripts/activate" ]; then
    # Git Bash on Windows
    # shellcheck source=/dev/null
    source "venv/Scripts/activate"
fi

export PYTHONPATH="${PYTHONPATH:-}:$PWD"

LOGFILE=logs/ingest.log
echo "[$(date)] 🚀 Starting Ingest..." | tee -a "$LOGFILE"

# Run the Scraper via manage.py (click command: scrape)
if python manage.py scrape 2>&1 | tee -a "$LOGFILE"; then
    echo "[$(date)] ✅ Ingest Success" | tee -a "$LOGFILE"
else
    echo "[$(date)] ❌ Ingest FAILED" | tee -a "$LOGFILE"
    exit 1
fi