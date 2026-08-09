"""
AquaIQ database initializer.

Run once during setup (setup.sh calls this automatically):
    python3 db/init_db.py

Reads db_path from config.yaml, creates all 6 tables from schema.sql if they
don't already exist. Safe to re-run — every CREATE TABLE uses IF NOT EXISTS.
"""
import sqlite3
import yaml
from pathlib import Path

ROOT = Path(__file__).parent.parent


def init_db():
    with open(ROOT / "config.yaml") as f:
        config = yaml.safe_load(f)

    db_path = ROOT / config["paths"]["db_path"]
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with open(Path(__file__).parent / "schema.sql") as f:
        schema_sql = f.read()

    conn = sqlite3.connect(db_path)
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()

    print(f"AquaIQ database initialized at: {db_path}")
    print("Tables: districts, raw_data, features, predictions, shap_values, crisis_scores")


if __name__ == "__main__":
    init_db()
