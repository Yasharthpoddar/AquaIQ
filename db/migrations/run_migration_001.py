"""Apply an explicit crosswalk atomically, with a database collision/loss audit.

Unmapped valid districts, existing canonical rows, row IDs, foreign keys, and
feature provenance survive. Conflicting identities or derived outputs stop the
transaction rather than silently moving them. The SQL file is executed only
after state-aware validation; it does not own or commit the transaction.
"""

import csv
import json
import logging
import os
import re
import sys
from pathlib import Path

import psycopg2.extras

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from db.connection import get_connection  # noqa: E402

logger = logging.getLogger(__name__)

MAPPING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS legacy_district_ids (
    legacy_id VARCHAR(64) PRIMARY KEY,
    canonical_id VARCHAR(64) NOT NULL,
    canonical_name TEXT NOT NULL,
    canonical_state TEXT NOT NULL,
    source TEXT NOT NULL,
    match_type TEXT NOT NULL,
    notes TEXT,
    migrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def normalize_state(value):
    """Normalize recorded state variants without matching district names."""
    value = re.sub(r"[^a-z0-9]+", " ", str(value).casefold().replace("&", " and ")).strip()
    value = re.sub(r"\s+", " ", value)
    if value.startswith("the "):
        value = value[4:]
    aliases = {
        "orissa": "odisha", "uttaranchal": "uttarakhand",
        "pondicherry": "puducherry", "nct of delhi": "delhi",
        "national capital territory of delhi": "delhi",
        "andaman and nicobar": "andaman and nicobar islands",
        "dadra and nagar haveli": "dadra and nagar haveli and daman and diu",
        "daman and diu": "dadra and nagar haveli and daman and diu",
    }
    return aliases.get(value, value)


def _name_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def read_crosswalk(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_crosswalk(rows, districts, existing_mappings=()):
    """Return validated exact-ID mappings and missing canonical master rows.

    Duplicate district names in different states never establish a mapping.
    Existing canonical metadata and previously recorded mappings are immutable.
    """
    master = {row["district_id"]: row for row in districts}
    recorded = {row["legacy_id"]: row["canonical_id"] for row in existing_mappings}
    mappings, canonical = {}, {}
    required = ("legacy_district_id", "canonical_district_id", "canonical_name",
                "canonical_state", "source", "match_type")
    for source_row in rows:
        if any(not str(source_row.get(key, "")).strip() for key in required):
            raise ValueError("Crosswalk rows require IDs, canonical name/state, source, and match type")
        row = {key: str(value or "").strip() for key, value in source_row.items()}
        legacy, target = row["legacy_district_id"], row["canonical_district_id"]
        if len(legacy) > 64 or len(target) > 50 or not re.fullmatch(r"[A-Z]{2}-.+", target):
            raise ValueError(f"Invalid district identity in crosswalk: {legacy} -> {target}")
        if legacy in mappings and mappings[legacy]["canonical_district_id"] != target:
            raise ValueError(f"Ambiguous crosswalk identity: {legacy}")
        if legacy in recorded and recorded[legacy] != target:
            raise ValueError(f"Crosswalk changes a previously recorded mapping: {legacy}")
        if legacy in master and "-" in legacy and legacy != target:
            raise ValueError(f"Crosswalk attempts to remap an existing canonical district: {legacy}")
        state = normalize_state(row["canonical_state"])
        old = master.get(legacy)
        if old and normalize_state(old["state"]) != state:
            raise ValueError(f"Cross-state mapping rejected: {legacy} -> {target}")
        current = master.get(target)
        if current and (normalize_state(current["state"]) != state
                        or _name_key(current["district_name"]) != _name_key(row["canonical_name"])):
            raise ValueError(f"Crosswalk conflicts with canonical master metadata: {target}")
        previous = canonical.get(target)
        if previous and (normalize_state(previous["canonical_state"]) != state
                         or _name_key(previous["canonical_name"]) != _name_key(row["canonical_name"])):
            raise ValueError(f"Conflicting canonical metadata in crosswalk: {target}")
        mappings[legacy] = row
        if previous is None or legacy == target:
            canonical[target] = row

    # Retained audit mappings also participate in the SQL reconciliation.
    # Validate entries absent from today's CSV instead of trusting old aliases.
    for recorded_row in existing_mappings:
        legacy, target = recorded_row["legacy_id"], recorded_row["canonical_id"]
        old, current = master.get(legacy), master.get(target)
        candidate = canonical.get(target)
        if current is None and candidate is None:
            raise ValueError(f"Recorded mapping has no verified canonical destination: {legacy}")
        state = normalize_state(current["state"] if current else candidate["canonical_state"])
        if old and normalize_state(old["state"]) != state:
            raise ValueError(f"Cross-state recorded mapping rejected: {legacy} -> {target}")
        if old and "-" in legacy and legacy != target:
            raise ValueError(f"Recorded mapping remaps an existing canonical district: {legacy}")
        if recorded_row.get("canonical_state") and normalize_state(recorded_row["canonical_state"]) != state:
            raise ValueError(f"Recorded mapping conflicts with canonical state: {legacy}")

    missing = []
    for target, row in canonical.items():
        if target in master:
            continue
        # Zone inheritance also uses exact mapped IDs, never a name-only lookup.
        zones = {master[legacy].get("agro_climatic_zone")
                 for legacy, mapping in mappings.items()
                 if mapping["canonical_district_id"] == target and legacy in master}
        zones.discard(None)
        missing.append({"district_id": target, "district_name": row["canonical_name"],
                        "state": row["canonical_state"], "geojson_name": row["canonical_name"],
                        "agro_climatic_zone": next(iter(zones)) if len(zones) == 1 else None})
    return list(mappings.values()), missing


def run_migration(connection=None, crosswalk_path=None, report_path=None, commit=True):
    """Run once or repeatedly; ``commit=False`` supports isolated DB verification."""
    rows = read_crosswalk(crosswalk_path or ROOT / "data_ingestion" / "district_crosswalk.csv")
    sql = Path(__file__).with_name("001_canonical_districts.sql").read_text(encoding="utf-8")
    owns_connection = connection is None
    conn = connection or get_connection()
    if conn.autocommit:
        if owns_connection:
            conn.close()
        raise ValueError("Canonical migration requires a connection with autocommit disabled")
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(MAPPING_TABLE_SQL)
            cur.execute("LOCK TABLE districts, raw_data, features, predictions, crisis_scores, "
                        "legacy_district_ids IN SHARE ROW EXCLUSIVE MODE")
            cur.execute("SELECT district_id, district_name, state, agro_climatic_zone, geojson_name FROM districts")
            districts = cur.fetchall()
            cur.execute("SELECT * FROM legacy_district_ids")
            mappings, missing = validate_crosswalk(rows, districts, cur.fetchall())
            # Drop only this former overly broad name constraint. Unmapped
            # numeric master rows are retained and may share a canonical name.
            cur.execute("ALTER TABLE districts DROP CONSTRAINT IF EXISTS districts_state_district_name_unique")
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO districts(district_id, district_name, state, agro_climatic_zone, geojson_name)
                VALUES (%(district_id)s, %(district_name)s, %(state)s, %(agro_climatic_zone)s, %(geojson_name)s)
                ON CONFLICT(district_id) DO NOTHING
            """, missing)
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO legacy_district_ids(legacy_id, canonical_id, canonical_name,
                    canonical_state, source, match_type, notes)
                VALUES (%(legacy_district_id)s, %(canonical_district_id)s, %(canonical_name)s,
                    %(canonical_state)s, %(source)s, %(match_type)s, %(notes)s)
                ON CONFLICT(legacy_id) DO NOTHING
            """, [{**row, "notes": row.get("notes", "")} for row in mappings])
            cur.execute("""
                SELECT 'predictions' AS table_name, p.district_id, COUNT(*) AS row_count
                FROM predictions p JOIN legacy_district_ids m ON p.district_id = m.legacy_id
                WHERE m.legacy_id <> m.canonical_id GROUP BY p.district_id
                UNION ALL
                SELECT 'crisis_scores', s.district_id, COUNT(*)
                FROM crisis_scores s JOIN legacy_district_ids m ON s.district_id = m.legacy_id
                WHERE m.legacy_id <> m.canonical_id GROUP BY s.district_id
            """)
            if cur.fetchall():
                raise ValueError("Derived predictions/scores reference legacy IDs; archive and rebuild those outputs before canonical migration")
            cur.execute(sql)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_districts_canonical_state_name
                ON districts(state, district_name) WHERE district_id ~ '^[A-Z]{2}-'
            """)
            cur.execute("""
                SELECT audit.* FROM canonical_migration_runs audit
                JOIN migration_001_run run ON run.run_id = audit.run_id
            """)
            report = dict(cur.fetchone())
            cur.execute("SELECT table_name, canonical_id, row_key, before_rows, after_row "
                        "FROM canonical_migration_audit WHERE run_id = %s ORDER BY audit_id",
                        (report["run_id"],))
            report["collisions"] = [dict(row) for row in cur.fetchall()]
            if commit:
                conn.commit()
        # The database audit is authoritative and belongs to the same commit.
        # Write the optional convenience report only after successful checks.
        if commit:
            target = Path(report_path or ROOT / "reports" / "canonical_migration_audit.json")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_text(json.dumps(report, indent=2, default=str, allow_nan=False), encoding="utf-8")
            os.replace(temporary, target)
        logger.info("Canonical migration passed the loss audit: %s", report["after_counts"])
        return report
    except Exception:
        conn.rollback()
        raise
    finally:
        if owns_connection:
            conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_migration()
