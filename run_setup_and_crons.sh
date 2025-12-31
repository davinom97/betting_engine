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

# Detect if running under WSL (so we can prefer linux-style venv and avoid sourcing Windows Scripts/activate)
IS_WSL=false
if [ -f /proc/version ] && grep -qi microsoft /proc/version 2>/dev/null; then
  IS_WSL=true
fi

# Choose where to create the virtualenv. If repo is on a Windows mount under WSL (/mnt/*),
# create the venv in the WSL-native filesystem to avoid permission and symlink problems.
if [ "$IS_WSL" = true ] && [[ "$ROOT_DIR" == /mnt/* ]]; then
  REPO_NAME="$(basename "$ROOT_DIR")"
  VENV_DIR="$HOME/.cache/${REPO_NAME}_venv"
  mkdir -p "$(dirname "$VENV_DIR")" || true
else
  VENV_DIR="venv"
fi

CRON_TAG="# betting_engine_cron"

print_help() {
    cat <<EOF
Usage: $0 [OPTIONS]

Options:
  --install        Install the recommended crontab entries (Unix only).
  --install-windows Create a PowerShell helper to install equivalent Windows Scheduled Tasks (schtasks).
  --run-now        Run manage.py tasks now: setup, scrape, compute_features.
  --no-pip         Skip pip install step.
  --dry-run        Print the crontab entries but do not install.
  --help           Show this message.

This script is designed for Unix-like shells. On Windows, run inside WSL or Git-Bash.
On native Windows you can also create equivalent Scheduled Tasks using the generated
`tasks_windows.ps1` helper (use --install-windows to generate it). See notes below.
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
INSTALL_WINDOWS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install) INSTALL=true; shift ;;
    --run-now) RUN_NOW=true; shift ;;
    --no-pip) NO_PIP=true; shift ;;
  --install-windows) INSTALL_WINDOWS=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --help) print_help; exit 0 ;;
    *) echo "Unknown arg: $1"; print_help; exit 2 ;;
  esac
done

echo ">>> ROOT: $ROOT_DIR"

mkdir -p data logs

if [ "$NO_PIP" = false ]; then
  echo ">>> Creating venv (if missing) and installing dependencies..."
  # When running inside WSL prefer python3 (system python) to create a proper Linux venv
  if [ "$IS_WSL" = true ]; then
    if command -v python3 >/dev/null 2>&1; then
      python3 -m venv "$VENV_DIR" || true
    else
      python -m venv "$VENV_DIR" || true
    fi
  else
    if command -v python >/dev/null 2>&1; then
      python -m venv "$VENV_DIR" || true
    else
      python3 -m venv "$VENV_DIR" || true
    fi
  fi

  # Activate venv in this script so subsequent python commands use it
  if [ -f "$VENV_DIR/bin/activate" ]; then
    # Unix-style venv (WSL/Git-Bash/Unix)
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
  elif [ -f "$VENV_DIR/Scripts/activate" ] && [ "$IS_WSL" != true ]; then
    # Windows-style venv (Git-Bash on Windows / native Windows). Avoid sourcing this under WSL
    # shellcheck source=/dev/null
    source "$VENV_DIR/Scripts/activate"
  fi

  # If venv creation failed on Debian/Ubuntu under WSL, provide a hint
  if [ "$IS_WSL" = true ] && [ ! -x "$VENV_DIR/bin/python" ]; then
    echo ">>> Failed to create venv: '$VENV_DIR/bin/python' not found. On Debian/Ubuntu distributions you may need to install python3-venv:" >&2
    echo "    sudo apt update && sudo apt install python3-venv -y" >&2
    echo "Then re-run this script inside WSL to create the venv." >&2
    exit 1
  fi

  # Prefer the venv python executable if present; fall back to python/python3 on PATH
  if [ -x "$VENV_DIR/bin/python" ]; then
    PYTHON_CMD="$VENV_DIR/bin/python"
  elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then
    PYTHON_CMD="$VENV_DIR/Scripts/python.exe"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
  else
    PYTHON_CMD="python3"
  fi

  if [ -f requirements.txt ]; then
    echo ">>> Installing from requirements.txt..."
    # Use the selected Python interpreter to run pip so the venv's pip is used on all platforms
    "$PYTHON_CMD" -m pip install --upgrade pip
    "$PYTHON_CMD" -m pip install -r requirements.txt
  else
    echo ">>> requirements.txt not found, installing core dependencies..."
    "$PYTHON_CMD" -m pip install --upgrade pip
    "$PYTHON_CMD" -m pip install pandas sqlalchemy click requests pydantic-settings tenacity scikit-learn
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

# Show which python interpreter will be used
echo ">>> Using python: $PYTHON_CMD"

# Quick sanity-check: can that python import click? If not, try installing requirements and re-check.
if ! "$PYTHON_CMD" -c "import click" >/dev/null 2>&1; then
  echo ">>> 'click' not importable by $PYTHON_CMD; attempting to install requirements (if present)..."
  if [ -f requirements.txt ]; then
    "$PYTHON_CMD" -m pip install -r requirements.txt || true
  else
    echo ">>> No requirements.txt found; please install 'click' into your venv: $PYTHON_CMD -m pip install click"
  fi

  # Re-check
  if ! "$PYTHON_CMD" -c "import click" >/dev/null 2>&1; then
    echo ">>> ERROR: 'click' still not importable by $PYTHON_CMD. Aborting."
    echo ">>> Try activating the venv or run: $PYTHON_CMD -m pip install -r requirements.txt"
    exit 1
  fi
fi

# Run manage.py using the chosen Python interpreter so installed packages in the venv are available
"${PYTHON_CMD:-python}" manage.py setup

if [ "$RUN_NOW" = true ]; then
  echo ">>> Running ingest (manage.py scrape) now..."
  "${PYTHON_CMD:-python}" manage.py scrape

  echo ">>> Running feature computation (manage.py compute-features --hours 24) now..."
  "${PYTHON_CMD:-python}" manage.py compute-features --hours 24
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

if [ "$INSTALL_WINDOWS" = true ]; then
  echo ">>> Generating PowerShell helper: tasks_windows.ps1"
  cat > tasks_windows.ps1 <<'PS'
#!/usr/bin/env pwsh
# tasks_windows.ps1
# Helper to create and remove Windows Scheduled Tasks equivalent to the project's crontab entries.

$root = "$(Get-Location)"
$repo = $root.Path
$gitbash = "C:\Program Files\Git\bin\bash.exe"

Write-Host "This script will create scheduled tasks that run the project's shell scripts via Git-Bash."
Write-Host "Edit the paths below if Git-Bash is installed elsewhere."

function Create-Tasks {
    Write-Host "Creating tasks..."
    schtasks /Create /SC MINUTE /MO 5 /TN "betting_engine_ingest" /TR "\"$gitbash\" -lc 'cd /c/$($repo -replace ':', '') && ./run_ingest.sh >> /c/$($repo -replace ':', '')/logs/ingest.log 2>&1'" /F
    schtasks /Create /SC DAILY /TN "betting_engine_decision_morning" /ST 10:00 /TR "\"$gitbash\" -lc 'cd /c/$($repo -replace ':', '') && ./run_decision.sh >> /c/$($repo -replace ':', '')/logs/decision.log 2>&1'" /F
    schtasks /Create /SC DAILY /TN "betting_engine_decision_evening" /ST 18:00 /TR "\"$gitbash\" -lc 'cd /c/$($repo -replace ':', '') && ./run_decision.sh >> /c/$($repo -replace ':', '')/logs/decision.log 2>&1'" /F
    schtasks /Create /SC DAILY /TN "betting_engine_feature_archiver" /ST 03:30 /TR "\"$gitbash\" -lc 'cd /c/$($repo -replace ':', '') && ./run_feature_archiver.sh >> /c/$($repo -replace ':', '')/logs/features.log 2>&1'" /F
    schtasks /Create /SC WEEKLY /D SUN /TN "betting_engine_backfill" /ST 04:00 /TR "\"$gitbash\" -lc 'cd /c/$($repo -replace ':', '') && ./run_backfill_utility.sh tierA >> /c/$($repo -replace ':', '')/logs/backfill.log 2>&1'" /F
    Write-Host "Tasks created. Verify with: schtasks /Query /TN betting_engine_*"
}

function Remove-Tasks {
    Write-Host "Removing tasks..."
    schtasks /Delete /TN "betting_engine_ingest" /F
    schtasks /Delete /TN "betting_engine_decision_morning" /F
    schtasks /Delete /TN "betting_engine_decision_evening" /F
    schtasks /Delete /TN "betting_engine_feature_archiver" /F
    schtasks /Delete /TN "betting_engine_backfill" /F
    Write-Host "Tasks removed."
}

param(
    [Switch]$Create,
    [Switch]$Remove
)

if ($Create) { Create-Tasks }
elseif ($Remove) { Remove-Tasks }
else { Write-Host "Usage: .\tasks_windows.ps1 -Create  or .\tasks_windows.ps1 -Remove" }
PS

  chmod +x tasks_windows.ps1 2>/dev/null || true
  echo ">>> Wrote tasks_windows.ps1. Run it in PowerShell with '-Create' to install tasks or '-Remove' to delete them." 
fi

echo ">>> Done."

exit 0
