echo "[$(date)] 🏆 Running Daily Decision Engine..." >> logs/decision.log
#!/usr/bin/env bash

cd "$(dirname "$0")"

mkdir -p logs

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

LOGFILE=logs/decision.log
echo "[$(date)] 🏆 Running Daily Decision Engine..." | tee -a "$LOGFILE"

# Run the full Orchestrator
python main.py >> "$LOGFILE" 2>&1

if [ ${PIPESTATUS[0]:-${?}} -eq 0 ]; then
  echo "[$(date)] ✅ Decision Cycle Complete" | tee -a "$LOGFILE"
else
  echo "[$(date)] ❌ Decision Cycle FAILED" | tee -a "$LOGFILE"
fi