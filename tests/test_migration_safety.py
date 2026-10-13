"""Canonical migration regressions, including an isolated PostgreSQL namespace.

The integration cases require --integration. All fixture DDL/data are in one
uncommitted transaction with a unique search_path and are rolled back at exit.
They never invoke the migration in the user's public schema.
"""

import csv
import uuid
from pathlib import Path

import pytest
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from db.migrations.run_migration_001 import normalize_state, run_migration, validate_crosswalk


def mapping(legacy="7", target="RJ-Jaipur", name="Jaipur", state="Rajasthan"):
    return {"legacy_district_id": legacy, "canonical_district_id": target,
            "canonical_name": name, "canonical_state": state,
            "source": "CGWB", "match_type": "Exact", "notes": "Verified exact state and ID"}


def district(identity, name, state):
    return {"district_id": identity, "district_name": name, "state": state,
            "agro_climatic_zone": "Zone A", "geojson_name": name}


def test_crosswalk_cannot_borrow_same_name_from_other_state():
    master = [district("7", "Aurangabad", "Bihar"),
              district("MH-Aurangabad", "Aurangabad", "Maharashtra")]
    with pytest.raises(ValueError, match="Cross-state"):
        validate_crosswalk([mapping(target="MH-Aurangabad", name="Aurangabad", state="Maharashtra")], master)


def test_same_name_in_two_states_is_not_an_automatic_alias():
    master = [district("BH-Aurangabad", "Aurangabad", "Bihar"),
              district("MH-Aurangabad", "Aurangabad", "Maharashtra")]
    rows, missing = validate_crosswalk([], master)
    assert rows == [] and missing == []


def test_existing_canonical_district_cannot_be_remapped():
    with pytest.raises(ValueError, match="existing canonical"):
        validate_crosswalk([mapping(legacy="RJ-Jaipur", target="RJ-Ajmer", name="Ajmer")],
                           [district("RJ-Jaipur", "Jaipur", "Rajasthan")])


def test_recorded_mapping_cannot_be_silently_changed():
    with pytest.raises(ValueError, match="previously recorded"):
        validate_crosswalk([mapping()], [], [{"legacy_id": "7", "canonical_id": "RJ-Ajmer"}])


def test_retained_mapping_absent_from_csv_is_still_checked_for_state():
    master = [district("7", "Aurangabad", "Bihar"),
              district("MH-Aurangabad", "Aurangabad", "Maharashtra")]
    with pytest.raises(ValueError, match="Cross-state recorded"):
        validate_crosswalk([], master, [{"legacy_id": "7", "canonical_id": "MH-Aurangabad"}])


def test_ambiguous_legacy_id_is_rejected():
    with pytest.raises(ValueError, match="Ambiguous"):
        validate_crosswalk([mapping(), mapping(target="RJ-Ajmer", name="Ajmer")], [])


def test_missing_canonical_zone_comes_only_from_exact_mapped_identity():
    master = [district("7", "Jaipur", "Rajasthan"), district("MH-Jaipur", "Jaipur", "Maharashtra")]
    master[1]["agro_climatic_zone"] = "Wrong state zone"
    _, missing = validate_crosswalk([mapping()], master)
    assert missing[0]["agro_climatic_zone"] == "Zone A"


@pytest.mark.parametrize("left,right", [("Orissa", "Odisha"),
    ("The Dadra And Nagar Haveli And Daman And Diu", "Dadra and Nagar Haveli and Daman and Diu"),
    ("NCT of Delhi", "Delhi"), ("Andaman & Nicobar Islands", "Andaman and Nicobar Islands")])
def test_state_normalization_accepts_recorded_variants(left, right):
    assert normalize_state(left) == normalize_state(right)


@pytest.fixture
def isolated_database():
    from db.connection import get_connection
    conn = get_connection()
    namespace = "aquaiq_migration_test_" + uuid.uuid4().hex
    root = Path(__file__).resolve().parents[1]
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(namespace)))
            cur.execute(sql.SQL("SET LOCAL search_path TO {}\n").format(sql.Identifier(namespace)))
            cur.execute((root / "db" / "schema.sql").read_text(encoding="utf-8"))
            cur.execute((root / "db" / "migrations" / "003_pipeline_provenance.sql").read_text(encoding="utf-8"))
            cur.execute("""
                INSERT INTO districts(district_id,district_name,state,agro_climatic_zone)
                VALUES ('7','Jaipur','Rajasthan','Zone A'), ('RJ-Jaipur','Jaipur','Rajasthan','Zone A'),
                       ('MH-Mumbai_Suburban','Mumbai Suburban','Maharashtra','Zone B'),
                       ('999','Unmapped Valid District','Rajasthan','Zone A');
                INSERT INTO raw_data(district_id,date,source,metric,value)
                VALUES ('7','2020-01-01','CGWB','GWL',10),
                       ('RJ-Jaipur','2020-01-01','CGWB','GWL',14),
                       ('MH-Mumbai_Suburban','2020-01-01','CGWB','GWL',6),
                       ('999','2020-01-01','CGWB','GWL',8);
                INSERT INTO features(district_id,date,gwl_current,crop_season_flag,
                    is_observed,is_imputed,months_since_observation,feature_generation)
                VALUES ('7','2020-01-01',10,'Rabi',TRUE,FALSE,0,'physical-v3-test'),
                       ('RJ-Jaipur','2020-01-01',14,'Rabi',TRUE,FALSE,0,'physical-v3-test'),
                       ('MH-Mumbai_Suburban','2020-01-01',6,'Rabi',TRUE,FALSE,0,'physical-v3-test'),
                       ('999','2020-01-01',8,'Rabi',TRUE,FALSE,0,'physical-v3-test');
            """)
        yield conn
    finally:
        conn.rollback()
        conn.close()


def write_crosswalk(tmp_path):
    path = tmp_path / "crosswalk.csv"
    row = mapping()
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    return path


def snapshot(conn):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        result = {}
        for table in ("districts", "raw_data", "features"):
            cur.execute(sql.SQL("SELECT * FROM {} ORDER BY district_id").format(sql.Identifier(table)))
            result[table] = [dict(row) for row in cur.fetchall()]
    return result


@pytest.mark.requires_db
def test_migration_preserves_mumbai_and_unmapped_rows_and_is_idempotent(isolated_database, tmp_path):
    conn = isolated_database
    before = snapshot(conn)
    report = run_migration(conn, write_crosswalk(tmp_path), commit=False)
    after = snapshot(conn)
    for identity in ("MH-Mumbai_Suburban", "999"):
        for table in before:
            assert [r for r in before[table] if r["district_id"] == identity] == [
                r for r in after[table] if r["district_id"] == identity]
    assert len(after["raw_data"]) == len(after["features"]) == 3
    canonical = next(row for row in after["features"] if row["district_id"] == "RJ-Jaipur")
    assert canonical["gwl_current"] == 12
    assert canonical["feature_generation"] == "physical-v3-test"
    assert canonical["is_observed"] is True and canonical["is_imputed"] is False
    assert report["raw_collapsed_rows"] == report["feature_collapsed_rows"] == 1
    assert len(report["collisions"]) == 2
    assert all(len(row["before_rows"]) == 2 for row in report["collisions"])
    second = run_migration(conn, write_crosswalk(tmp_path), commit=False)
    assert snapshot(conn) == after
    assert second["raw_collapsed_rows"] == second["feature_collapsed_rows"] == 0


@pytest.mark.requires_db
def test_conflicting_feature_generation_rolls_back_whole_migration(isolated_database, tmp_path):
    conn = isolated_database
    with conn.cursor() as cur:
        cur.execute("UPDATE features SET feature_generation='old-scaled-v1' WHERE district_id='7'")
    with pytest.raises(Exception, match="conflicting provenance"):
        run_migration(conn, write_crosswalk(tmp_path), commit=False)
    # Fixture DDL was also uncommitted; rollback must remove its namespace.
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM pg_namespace WHERE nspname LIKE 'aquaiq_migration_test_%'")
        assert cur.fetchone()[0] == 0


@pytest.mark.requires_db
def test_legacy_model_outputs_block_migration_without_silent_merge(isolated_database, tmp_path):
    conn = isolated_database
    with conn.cursor() as cur:
        cur.execute("INSERT INTO predictions(district_id,forecast_date,model_name,predicted_gwl) "
                    "VALUES('7','2020-07-01','xgboost',5)")
    with pytest.raises(ValueError, match="Derived predictions/scores"):
        run_migration(conn, write_crosswalk(tmp_path), commit=False)
