#!/usr/bin/env bash
# Backfill utility script
# Usage: ./run_backfill_utility.sh [mode]
# Modes: tierA | tierB | tierC | all | sport:<sport_key>

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
echo "[$(date)] ▶ Starting History Backfill..." | tee -a "$LOGFILE"
echo "    (This may take a while; API rate limits apply)" | tee -a "$LOGFILE"

# Ensure required packages are installed
if ! python -c "import click,requests" &>/dev/null; then
	echo "Installing runtime requirements into venv..." | tee -a "$LOGFILE"
	python -m pip install -r requirements.txt >>"$LOGFILE" 2>&1 || true
fi

MODE=${1:-tierA}

run_cmd() {
	echo "[$(date)] ▶ $*" | tee -a "$LOGFILE"
	# Run the python backfill command
	python -m src.backfill $* 2>&1 | tee -a "$LOGFILE"
	local rc=${PIPESTATUS[0]:-${?}}
	if [ $rc -ne 0 ]; then
		echo "[$(date)] ❌ Command failed: python -m src.backfill $* (rc=$rc)" | tee -a "$LOGFILE"
		return $rc
	fi
	return 0
}

case "$MODE" in
	tierA)
		# High-resolution recent
		run_cmd --sport basketball_nba --days 45 --interval 1 || exit 1
		run_cmd --sport icehockey_nhl --days 45 --interval 1 || exit 1
		run_cmd --sport americanfootball_nfl --days 90 --interval 2 || exit 1
		run_cmd --sport basketball_ncaab --days 30 --interval 2 || exit 1
		;;
	tierB)
		run_cmd --sport basketball_nba --days 180 --interval 4 || exit 1
		run_cmd --sport icehockey_nhl --days 180 --interval 4 || exit 1
		run_cmd --sport americanfootball_nfl --days 365 --interval 6 || exit 1
		run_cmd --sport basketball_ncaab --days 120 --interval 6 || exit 1
		;;
	tierC)
		run_cmd --sport basketball_nba --days 720 --interval 24 || exit 1
		run_cmd --sport icehockey_nhl --days 720 --interval 24 || exit 1
		run_cmd --sport americanfootball_nfl --days 1460 --interval 24 || exit 1
		run_cmd --sport basketball_ncaab --days 365 --interval 24 || exit 1
		;;
	all)
		# Full optimizer run (A -> B -> C)
		"$0" tierA || exit 1
		"$0" tierB || exit 1
		"$0" tierC || exit 1
		;;
	sport:*)
		SPORT=${MODE#sport:}
		run_cmd --sport $SPORT --days 30 --interval 24 || exit 1
		;;
	*)
		echo "Unknown mode: $MODE" | tee -a "$LOGFILE"
		echo "Usage: $0 [tierA|tierB|tierC|all|sport:<sport_key>]" | tee -a "$LOGFILE"
		exit 2
		;;
esac

echo "[$(date)] ✅ Backfill Complete." | tee -a "$LOGFILE"