#!/usr/bin/env bash

# run_decision.sh
# Runs the daily decision engine and appends output to logs/decision.log

set -euo pipefail

cd "$(dirname "$0")"

mkdir -p logs

# Activate virtualenv (support venv or .venv, Windows-style Scripts/activate for Git Bash)
if [ -f "venv/bin/activate" ]; then
    # unix-style venv
    # shellcheck source=/dev/null
    source "venv/bin/activate"
elif [ -f ".venv/bin/activate" ]; then
    # unix-style .venv
    # shellcheck source=/dev/null
    source ".venv/bin/activate"
elif [ -f "venv/Scripts/activate" ]; then
    # git-bash / msys style on Windows
    # shellcheck source=/dev/null
    source "venv/Scripts/activate"
elif [ -f ".venv/Scripts/activate" ]; then
    # git-bash / msys style on Windows
    # shellcheck source=/dev/null
    source ".venv/Scripts/activate"
fi

export PYTHONPATH="${PYTHONPATH:-}:$ROOT_DIR"

LOGFILE=logs/decision.log
echo "[$(date)] 🏆 Running Daily Decision Engine..." | tee -a "$LOGFILE"

# Run the main orchestrator; use -u to flush output timely
python -u main.py >> "$LOGFILE" 2>&1 || {
    echo "[$(date)] ❌ Decision Cycle FAILED" | tee -a "$LOGFILE"
    exit 1
}

echo "[$(date)] ✅ Decision Cycle Complete" | tee -a "$LOGFILE"