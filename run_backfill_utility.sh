#!/usr/bin/env bash

# run_backfill_utility.sh
# Backfill historical data for various sports. Usage: ./run_backfill_utility.sh [mode]
# Modes: tierA | tierB | tierC | all | sport:<sport_key>


set -euo pipefail

# Set ROOT_DIR to the directory of this script
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$ROOT_DIR"

mkdir -p "$ROOT_DIR/logs" "$ROOT_DIR/data"


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

export PYTHONPATH="${PYTHONPATH:-}:$PWD"

LOGFILE="$ROOT_DIR/logs/backfill.log"
echo "[$(date)] ▶ Starting History Backfill..." | tee -a "$LOGFILE"
echo "    (This may take a while; API rate limits apply)" | tee -a "$LOGFILE"

echo "[$(date)] Using python: $PYTHON_CMD" | tee -a "$LOGFILE"

# Ensure required packages are installed (best-effort)
if ! "$PYTHON_CMD" -c "import click,requests" >/dev/null 2>&1; then
	echo "Installing runtime requirements into venv..." | tee -a "$LOGFILE"
	"$PYTHON_CMD" -m pip install -r requirements.txt >>"$LOGFILE" 2>&1 || true
fi

MODE=${1:-tierA}

run_cmd() {
	echo "[$(date)] ▶ $*" | tee -a "$LOGFILE"
	# Run the python backfill command
	if "$PYTHON_CMD" -m src.backfill "$@" 2>&1 | tee -a "$LOGFILE"; then
		return 0
	else
		local rc=${PIPESTATUS[0]:-${?}}
		echo "[$(date)] ❌ Command failed: $PYTHON_CMD -m src.backfill $* (rc=$rc)" | tee -a "$LOGFILE"
		return $rc
	fi
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
		run_cmd --sport "$SPORT" --days 30 --interval 24 || exit 1
		;;
	*)
		echo "Unknown mode: $MODE" | tee -a "$LOGFILE"
		echo "Usage: $0 [tierA|tierB|tierC|all|sport:<sport_key>]" | tee -a "$LOGFILE"
		exit 2
		;;
esac

echo "[$(date)] ✅ Backfill Complete." | tee -a "$LOGFILE"