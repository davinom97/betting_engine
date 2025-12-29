#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo ">>> 🏗️  Creating project directories..."
mkdir -p data logs

echo ">>> 🐍 Setting up Python Virtual Environment..."
python3 -m venv venv
source venv/bin/activate

echo ">>> 📦 Installing dependencies..."
pip install --upgrade pip
# Added scikit-learn for the ML Engine and Tenacity for robust API calls
pip install pandas sqlalchemy click requests pydantic-settings tenacity scikit-learn

# Create .env if missing
if [ ! -f .env ]; then
    echo ">>> 📝 Creating default .env file..."
    echo "ODDS_API_KEY=replace_with_your_actual_key" > .env
    echo "LOG_LEVEL=INFO" >> .env
    echo "⚠️  ACTION REQUIRED: Edit .env and paste your API Key!"
#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

echo ">>> 🗂 Creating project directories..."
mkdir -p data logs

echo ">>> 🐍 Setting up Python Virtual Environment..."
# Try to create venv with system python, fallback to python3 if needed
if command -v python >/dev/null 2>&1; then
    python -m venv venv
else
    python3 -m venv venv
fi

# Activate the venv in this shell (cross-platform)
if [ -f "venv/bin/activate" ]; then
    source "venv/bin/activate"
elif [ -f "venv/Scripts/activate" ]; then
    source "venv/Scripts/activate"
fi

echo ">>> 📦 Installing dependencies..."
pip install --upgrade pip
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
else
    # Fallback to core deps
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

echo ">>> � Initializing Database Schema..."
export PYTHONPATH="$PYTHONPATH:."
python manage.py setup

echo ">>> ✅ Setup Complete."
echo "    Next Step: Edit .env, then run './run_backfill_utility.sh' to seed data."