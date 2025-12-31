#!/usr/bin/env bash
# run_setup_and_crons.sh
#
# Single-entry setup script for the betting_engine project.
# - Creates/activates venv and installs requirements
# - Optionally runs manage.py tasks now (ingest, compute_features)
# - Prints recommended crontab entries and can install them with --install
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

CRON_TAG="# betting_engine_cron"

print_help() {
    cat <<EOF
Usage: $0 [OPTIONS]

Options:
  --install        Install the recommended crontab entries (Unix only).
  --run-now        Run manage.py tasks now: setup, scrape, compute_features.
  --no-pip         Skip pip install step.
  --dry-run        Print the crontab entries but do not install.
  --help           Show this message.

This script is designed for Unix-like shells. On Windows, run inside WSL or Git-Bash.
Cron entries perform:
  - Ingest every 5 minutes (run_ingest.sh)
  - Decision run at 10:00 and 18:00 daily (run_decision.sh)
  - Feature archiver daily at 03:30 (run_feature_archiver.sh)
  - Weekly backfill Sunday 04:00 (run_backfill_utility.sh tierA)

Example:
  bash $0 --run-now --install

EOF
}

INSTALL=false
RUN_NOW=false
NO_PIP=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install) INSTALL=true; shift ;;
    --run-now) RUN_NOW=true; shift ;;
    --no-pip) NO_PIP=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --help) print_help; exit 0 ;;
    *) echo "Unknown arg: $1"; print_help; exit 2 ;;
  esac
done

echo ">>> ROOT: $ROOT_DIR"

mkdir -p data logs

if [ "$NO_PIP" = false ]; then
  echo ">>> Creating venv (if missing) and installing dependencies..."
  if command -v python >/dev/null 2>&1; then
    python -m venv venv || true
  else
    python3 -m venv venv || true
  fi

  # Activate venv in this script so subsequent python commands use it
  if [ -f "venv/bin/activate" ]; then
    # shellcheck source=/dev/null
    source "venv/bin/activate"
  elif [ -f "venv/Scripts/activate" ]; then
    # Git-Bash on Windows
    # shellcheck source=/dev/null
    source "venv/Scripts/activate"
  fi

  if [ -f requirements.txt ]; then
    echo ">>> Installing from requirements.txt..."
    pip install --upgrade pip
    pip install -r requirements.txt
  else
    echo ">>> requirements.txt not found, installing core dependencies..."
    pip install --upgrade pip
    pip install pandas sqlalchemy click requests pydantic-settings tenacity scikit-learn
  fi
else
  echo ">>> --no-pip provided; skipping pip install." 
fi

echo ">>> Ensuring DB schema exists (manage.py setup)"
# Safely extend PYTHONPATH even when set -u is enabled
if [ -z "${PYTHONPATH:-}" ]; then
  export PYTHONPATH="$ROOT_DIR"
else
  export PYTHONPATH="${PYTHONPATH}:$ROOT_DIR"
fi
python manage.py setup

if [ "$RUN_NOW" = true ]; then
  echo ">>> Running ingest (manage.py scrape) now..."
  python manage.py scrape

  echo ">>> Running feature computation (manage.py compute_features --hours 24) now..."
  python manage.py compute_features --hours 24
fi

# Prepare crontab entries
CRON_INGEST="*/5 * * * * cd $ROOT_DIR && ./run_ingest.sh >> $ROOT_DIR/logs/ingest.log 2>&1 $CRON_TAG"
CRON_DECISION="0 10,18 * * * cd $ROOT_DIR && ./run_decision.sh >> $ROOT_DIR/logs/decision.log 2>&1 $CRON_TAG"
CRON_FEATURES="30 3 * * * cd $ROOT_DIR && ./run_feature_archiver.sh >> $ROOT_DIR/logs/features.log 2>&1 $CRON_TAG"
CRON_BACKFILL="0 4 * * 0 cd $ROOT_DIR && ./run_backfill_utility.sh tierA >> $ROOT_DIR/logs/backfill.log 2>&1 $CRON_TAG"

echo "" 
echo ">>> Recommended crontab entries:" 
echo "# --- BEGIN betting_engine crontab ---"
echo "$CRON_INGEST"
echo "$CRON_DECISION"
echo "$CRON_FEATURES"
echo "$CRON_BACKFILL"
echo "# --- END betting_engine crontab ---"

if [ "$DRY_RUN" = true ]; then
  echo ">>> Dry run requested; not installing crontab."
  exit 0
fi

if [ "$INSTALL" = true ]; then
  # Check for crontab availability
  if ! command -v crontab >/dev/null 2>&1; then
    echo ">>> crontab command not found on this system. Cannot install."
    echo ">>> If you're on Windows, use Task Scheduler or run this script inside WSL/Git-Bash."
    exit 1
  fi

  echo ">>> Installing crontab entries..."
  TMP_CRON="$(mktemp)"

  # Capture existing crontab if any
  if crontab -l >/dev/null 2>&1; then
    crontab -l > "$TMP_CRON"
  else
    echo "" > "$TMP_CRON"
  fi

  # Remove any previous entries we installed (idempotent)
  grep -v "$CRON_TAG" "$TMP_CRON" > "${TMP_CRON}.clean" || true
  mv "${TMP_CRON}.clean" "$TMP_CRON"

  # Append our entries
  echo "$CRON_INGEST" >> "$TMP_CRON"
  echo "$CRON_DECISION" >> "$TMP_CRON"
  echo "$CRON_FEATURES" >> "$TMP_CRON"
  echo "$CRON_BACKFILL" >> "$TMP_CRON"

  # Install
  crontab "$TMP_CRON"
  rm -f "$TMP_CRON"

  echo ">>> Crontab installed. Verify with: crontab -l"
fi

echo ">>> Done."

exit 0
