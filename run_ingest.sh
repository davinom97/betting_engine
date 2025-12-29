#!/usr/bin/env bash

# Move to repo root (script dir)
cd "$(dirname "$0")"

# Create logs dir if missing
mkdir -p logs

# Activate virtualenv (support venv or .venv, Windows or Unix)
if [ -f "venv/bin/activate" ]; then
  source "venv/bin/activate"
elif [ -f "venv/Scripts/activate" ]; then
  source "venv/Scripts/activate"
elif [ -f ".venv/bin/activate" ]; then
  source ".venv/bin/activate"
elif [ -f ".venv/Scripts/activate" ]; then
  source ".venv/Scripts/activate"
fi

export PYTHONPATH="$PYTHONPATH:."

LOGFILE=logs/ingest.log
echo "[$(date)] 🚀 Starting Ingest..." | tee -a "$LOGFILE"

# Run the Scraper via manage.py (click command: scrape)
python manage.py scrape 2>&1 | tee -a "$LOGFILE"

EXIT_CODE=${PIPESTATUS[0]:-$?}
if [ "$EXIT_CODE" -eq 0 ]; then
  echo "[$(date)] ✅ Ingest Success" | tee -a "$LOGFILE"
else
  echo "[$(date)] ❌ Ingest FAILED (exit=$EXIT_CODE)" | tee -a "$LOGFILE"
fi