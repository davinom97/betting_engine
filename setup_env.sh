#!/usr/bin/env bash

# setup_env.sh
# Create venv, install dependencies, create default .env and initialize DB schema

set -euo pipefail

cd "$(dirname "$0")"

echo ">>> 🏗️  Creating project directories..."
mkdir -p data logs

echo ">>> 🐍 Setting up Python Virtual Environment..."
if command -v python >/dev/null 2>&1; then
    python -m venv venv
else
    python3 -m venv venv
fi

# Activate the venv in this shell
if [ -f "venv/bin/activate" ]; then
    # shellcheck source=/dev/null
    source "venv/bin/activate"
elif [ -f "venv/Scripts/activate" ]; then
    # Windows-Style activate for MSYS/Git-Bash
    # shellcheck source=/dev/null
    source "venv/Scripts/activate"
fi

echo ">>> 📦 Installing dependencies..."
pip install --upgrade pip
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
else
    # fallback
    pip install pandas sqlalchemy click requests pydantic-settings tenacity scikit-learn
fi

# Create .env if missing
if [ ! -f .env ]; then
    echo ">>> 📝 Creating default .env file..."
    cat > .env <<EOF
ODDS_API_KEY=replace_with_your_actual_key
LOG_LEVEL=INFO
DATABASE_URL=sqlite:///data/bets.db
BANKROLL=100
MAX_DAILY_STAKE_PERCENT=0.05
KELLY_FRACTION=0.1
TARGET_SPORTS=basketball_nba
TARGET_MARKETS=h2h,spreads
TARGET_BOOKMAKERS=draftkings,fanduel
TARGET_REGIONS=us
EOF
    echo "⚠️  ACTION REQUIRED: Edit .env and paste your API Key!"
fi

echo ">>> 🗄 Initializing Database Schema..."
export PYTHONPATH="${PYTHONPATH:-}:$PWD"
python manage.py setup

echo ">>> ✅ Setup Complete."
echo "    Next Step: Edit .env, then run './run_backfill_utility.sh' to seed data."