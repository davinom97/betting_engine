echo "[$(date)] 🧠 Running Feature Archiver..." >> logs/features.log
#!/usr/bin/env bash

cd "$(dirname "$0")"

# Activate virtual environment (cross-platform)
if [ -f "venv/bin/activate" ]; then
	source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
	source venv/Scripts/activate
fi

export PYTHONPATH="$PYTHONPATH:."

mkdir -p logs

echo "[$(date)] 🧠 Running Feature Archiver..." >> logs/features.log

# Look back 24 hours to ensure we catch recent games and finalized velocities
python manage.py compute_features --hours 24 >> logs/features.log 2>&1