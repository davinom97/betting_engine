#!/usr/bin/env bash

# run_feature_archiver.sh
# Compute and archive features (manage.py compute_features)

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

LOGFILE=logs/features.log
echo "[$(date)] 🧠 Running Feature Archiver..." | tee -a "$LOGFILE"

# Look back 24 hours to ensure we catch recent games and finalized velocities
if python manage.py compute_features --hours 24 2>&1 | tee -a "$LOGFILE"; then
	echo "[$(date)] ✅ Feature Archiver Complete" | tee -a "$LOGFILE"
else
	echo "[$(date)] ❌ Feature Archiver FAILED" | tee -a "$LOGFILE"
	exit 1
fi