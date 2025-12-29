echo ">>> 🔙 Starting History Backfill (NBA - 30 Days)..."
echo ">>> ✅ Backfill Complete."
#!/usr/bin/env bash

cd "$(dirname "$0")"

mkdir -p logs data

# Activate virtualenv (cross-platform)
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

LOGFILE=logs/backfill.log
echo "[$(date)] ▶ Starting History Backfill (NBA - 30 Days)..." | tee -a "$LOGFILE"
echo "    (This may take a few minutes due to API rate limits)" | tee -a "$LOGFILE"

# Defaulting to NBA, 30 days back, Daily intervals
# Change arguments here if you want other sports
python -m src.backfill --sport basketball_nba --days 30 --interval 24 2>&1 | tee -a "$LOGFILE"

if [ ${PIPESTATUS[0]:-${?}} -eq 0 ]; then
	echo "[$(date)] ✅ Backfill Complete." | tee -a "$LOGFILE"
else
	echo "[$(date)] ❌ Backfill FAILED" | tee -a "$LOGFILE"
fi