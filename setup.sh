#!/bin/bash
# AquaIQ one-command setup.
# Usage: bash setup.sh
set -e

echo "=== AquaIQ Setup ==="

# 1. Virtual environment
echo "[1/5] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# 2. Dependencies
echo "[2/5] Installing dependencies from requirements.txt..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

# 3. Directory structure (idempotent — safe if already created)
echo "[3/5] Ensuring data/model directories exist..."
mkdir -p data/raw data/processed models/checkpoints db

# 4. Database
echo "[4/5] Initializing SQLite database..."
python3 db/init_db.py

# 5. Sanity check config
echo "[5/5] Validating config.yaml..."
python3 -c "import yaml; yaml.safe_load(open('config.yaml')); print('config.yaml is valid')"

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. source venv/bin/activate"
echo "  2. Download CGWB/IMD/ERA5 data into data/raw/ (see README.md)"
echo "  3. Download India district GeoJSON into data/raw/india_districts.geojson"
