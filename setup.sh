#!/usr/bin/env bash
# Run from any directory: bash /path/to/AquaIQ/setup.sh
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ ! -f .env ]]; then
  echo 'Copy .env.example to .env and configure an existing PostgreSQL database before setup.' >&2
  exit 1
fi

if [[ ! -x venv/bin/python ]]; then
  python_bin="${PYTHON_BIN:-python3}"
  "$python_bin" -c 'import sys; assert sys.version_info[:2] == (3, 13), "AquaIQ requires Python 3.13"'
  "$python_bin" -m venv venv
fi
venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 13), "Existing venv requires Python 3.13; use a separate new environment"'
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements.txt
venv/bin/python -m pip check
mkdir -p data/raw data/processed models/checkpoints reports
venv/bin/python -m db.init_db
venv/bin/python -c 'from pathlib import Path; import yaml; yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8")); print("config.yaml is valid")'
echo 'Setup complete. Activate with: source venv/bin/activate'
echo 'See README.md for climate regeneration, pipeline execution, and dashboard setup.'
