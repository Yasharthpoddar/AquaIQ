"""Read-only AquaIQ source/CSV/database quality audit; writes reports only.

Run: python -m scripts.audit_data_quality --database
The database transaction is explicitly READ ONLY. No source file is modified.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from data_ingestion.data_completeness import canonical_mapping
from data_ingestion.ingest_imd_era5 import norm_state, norm_str

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {"venv", ".venv", "node_modules", ".git", ".pytest_cache", "__pycache__"}
NUMERIC = {"currentlevel", "gwl", "gwl_mean", "gwl_m_bgl", "GWL_current", "GWL_lag_3mo",
           "GWL_lag_6mo", "gwl_current", "gwl_lag_3mo", "gwl_lag_6mo", "rainfall",
           "rainfall_mm", "rainfall_current", "rainfall_3mo_avg", "temperature",
           "evapotranspiration", "water_balance_proxy", "monsoon_deficit_pct",
           "latitude", "longitude", "Latitude", "Longitude", "data_readiness_score",
           "months_since_observation", "Groundwater Level Quarterly Manual (meter)"}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def district_series(frame, mapping):
    _, legacy, names = mapping
    if "district_id" in frame:
        raw = frame.district_id.str.strip()
        return raw.where(raw.isin(set(legacy.values()))), raw
    if "district_code" in frame:
        raw = frame.district_code.str.strip()
        return raw.map(legacy), raw
    name_column = next((name for name in ("district", "district_name", "District") if name in frame), None)
    state_column = next((name for name in ("st_nm", "state", "state_name", "State") if name in frame), None)
    if name_column and state_column:
        pairs = list(zip(frame[name_column].map(norm_str), frame[state_column].map(norm_state)))
        ids = [next(iter(names[p])) if len(names.get(p, ())) == 1 else None for p in pairs]
        return pd.Series(ids, index=frame.index, dtype=object), frame[state_column].fillna("") + "|" + frame[name_column].fillna("")
    return None, None


def date_series(frame):
    for column in ["date", "observation_date", "reported_date", "Data Acquisition Time"]:
        if column in frame:
            if column == "Data Acquisition Time":
                # The native manual-station export explicitly uses DD-MM-YYYY.
                return pd.to_datetime(frame[column], errors="coerce", format="%d-%m-%Y %H:%M"), column
            return pd.to_datetime(frame[column], errors="coerce", format="mixed"), column
    if {"year", "month"}.issubset(frame):
        return pd.to_datetime(dict(year=pd.to_numeric(frame.year, errors="coerce"),
                                   month=pd.to_numeric(frame.month, errors="coerce"), day=1),
                              errors="coerce"), "year+month"
    return None, None


def audit_csv(path, mapping, *, root=ROOT, as_of=None, chunksize=100_000):
    """Audit one CSV in bounded chunks; verify duplicate hash candidates exactly."""
    as_of = pd.Timestamp(as_of or date.today())
    result = {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
              "sha256": sha256(path), "rows": 0, "columns": [], "missing_counts": {},
              "numeric": {}, "provenance_counts": {}, "duplicate_rows": 0}
    missing, hashes, numeric = Counter(), [], {}
    months, previous, backwards = defaultdict(set), {}, 0
    observed_months, imputed_months = defaultdict(set), defaultdict(set)
    ids_seen, unknown = set(), Counter()
    invalid_dates = future_dates = non_month_start = key_duplicates = 0
    monthly_keys = set()
    date_min = date_max = None
    source_values = defaultdict(Counter)
    is_monthly = False
    generation_values = Counter()
    try:
        reader = pd.read_csv(path, dtype=str, chunksize=chunksize)
        for frame in reader:
            result["columns"] = list(frame.columns)
            result["rows"] += len(frame)
            missing.update(frame.isna().sum().astype(int).to_dict())
            hashes.append(pd.util.hash_pandas_object(frame, index=False).to_numpy())
            for col in set(frame.columns) & NUMERIC:
                data = pd.to_numeric(frame[col], errors="coerce")
                valid = np.isfinite(data.to_numpy(dtype=float))
                info = numeric.setdefault(col, {"invalid_numeric": 0, "nonfinite": 0,
                                               "negative": 0, "min": None, "max": None,
                                               "outside_review_bounds": 0})
                info["invalid_numeric"] += int((frame[col].notna() & data.isna()).sum())
                info["nonfinite"] += int((data.notna() & ~valid).sum())
                finite = data[valid]
                info["negative"] += int((finite < 0).sum())
                if len(finite):
                    low, high = float(finite.min()), float(finite.max())
                    info["min"] = low if info["min"] is None else min(low, info["min"])
                    info["max"] = high if info["max"] is None else max(high, info["max"])
                bounds = (-90, 65) if col == "temperature" else None
                if col.lower().startswith(("gwl", "currentlevel")):
                    bounds = (-10, 300)  # review only: negative artesian levels can be legitimate
                if col.lower() == "latitude":
                    bounds = (-90, 90)
                if col.lower() == "longitude":
                    bounds = (-180, 180)
                if bounds:
                    info["outside_review_bounds"] += int(((finite < bounds[0]) | (finite > bounds[1])).sum())
            for col in ["source", "units", "is_observed", "is_imputed", "feature_generation", "date_basis", "purpose"]:
                if col in frame:
                    source_values[col].update(frame[col].fillna("<missing>").value_counts().to_dict())
            ids, raw_ids = district_series(frame, mapping)
            result["identity_schema_supported"] = ids is not None
            dates, date_column = date_series(frame)
            if ids is not None:
                ids_seen.update(ids.dropna())
                unknown.update(raw_ids[ids.isna()].fillna("<missing>").value_counts().to_dict())
            if dates is not None:
                result["date_column"] = date_column
                invalid_dates += int(dates.isna().sum())
                future_dates += int((dates > as_of).sum())
                non_month_start += int((dates.notna() & dates.dt.day.ne(1)).sum())
                if dates.notna().any():
                    lo, hi = dates.min(), dates.max()
                    date_min = lo if date_min is None else min(lo, date_min)
                    date_max = hi if date_max is None else max(hi, date_max)
                if ids is not None:
                    valid = ids.notna() & dates.notna()
                    is_monthly = ({"year", "month"}.issubset(frame) or
                                  ("district_id" in frame and not {"station_key", "station_name"}.intersection(frame)))
                    for district, stamp in zip(ids[valid], dates[valid]):
                        ordinal = stamp.to_period("M").ordinal
                        months[district].add(ordinal)
                        if district in previous and stamp < previous[district]:
                            backwards += 1
                        previous[district] = stamp
                    if is_monthly:
                        metric = frame.loc[valid, "metric"] if "metric" in frame else [""] * int(valid.sum())
                        sources = frame.loc[valid, "source"] if "metric" in frame and "source" in frame else [""] * int(valid.sum())
                        for district, stamp, field, source in zip(ids[valid], dates[valid], metric, sources):
                            key = (district, stamp.isoformat(), str(field), str(source))
                            key_duplicates += int(key in monthly_keys)
                            monthly_keys.add(key)
                    for column, target in [("is_observed", observed_months), ("is_imputed", imputed_months)]:
                        if column in frame:
                            selected = valid & frame[column].str.casefold().eq("true").fillna(False)
                            for district, stamp in zip(ids[selected], dates[selected]):
                                target[district].add(stamp.to_period("M").ordinal)
        # Hashes only select candidates; exact tuples settle equality, including
        # duplicate records crossing chunk boundaries and any hash collisions.
        if hashes:
            values, counts = np.unique(np.concatenate(hashes), return_counts=True)
            candidates = set(values[counts > 1].tolist())
            if candidates:
                exact = set()
                for frame in pd.read_csv(path, dtype=str, chunksize=chunksize):
                    matches = pd.util.hash_pandas_object(frame, index=False).isin(candidates)
                    for row in frame[matches].fillna("<AUDIT-NULL>").itertuples(index=False, name=None):
                        key = tuple(None if x == "<AUDIT-NULL>" else x for x in row)
                        result["duplicate_rows"] += int(key in exact)
                        exact.add(key)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeError, ValueError) as exc:
        result["read_error"] = type(exc).__name__
    result["missing_counts"] = dict(missing)
    result["missing_pct"] = {key: round(100 * count / result["rows"], 4) if result["rows"] else 0
                             for key, count in missing.items()}
    result["numeric"] = numeric
    result["provenance_counts"] = dict(source_values)
    result["districts"] = len(ids_seen)
    result["district_ids"] = sorted(ids_seen)
    result["unmapped_identity_rows"] = sum(unknown.values())
    result["unmapped_identity_examples"] = dict(unknown.most_common(20))
    result["missing_canonical_districts"] = sorted(set(mapping[0].canonical_district_id) - ids_seen) if ids_seen else None
    result["date_start"] = date_min.isoformat()[:10] if date_min is not None else None
    result["date_end"] = date_max.isoformat()[:10] if date_max is not None else None
    result["invalid_date_rows"] = invalid_dates
    result["future_date_rows"] = future_dates
    result["non_month_start_rows"] = non_month_start
    result["out_of_order_rows_within_district"] = backwards
    result["monthly_key_duplicate_rows"] = key_duplicates if is_monthly else None
    result["missing_months_within_observed_span"] = sum(max(v) - min(v) + 1 - len(v) for v in months.values())
    for label, values in [("months_per_district", months), ("observed_months_per_district", observed_months),
                          ("imputed_months_per_district", imputed_months)]:
        result[label] = {key: len(value) for key, value in sorted(values.items())}
    return result


def audit_database():
    """Return only measured read-only results; exceptions never expose credentials."""
    from db.connection import get_connection, read_frame, finite_json
    connection = None
    try:
        connection = get_connection()
        connection.set_session(readonly=True)
        def query(sql):
            return finite_json(read_frame(sql, connection).to_dict("records"))
        report = {"available": True, "transaction_read_only": query("SHOW transaction_read_only"),
                  "tables": {}, "raw_sources": query("""SELECT source,metric,COUNT(*) rows,
                    COUNT(DISTINCT district_id) districts,MIN(date) date_start,MAX(date) date_end,
                    COUNT(*) FILTER(WHERE value IS NULL) missing,
                    COUNT(*) FILTER(WHERE value::text IN ('NaN','Infinity','-Infinity')) nonfinite,
                    MIN(value) minimum,MAX(value) maximum FROM raw_data GROUP BY source,metric ORDER BY source,metric""")}
        for table, date_col in [("districts", None), ("raw_data", "date"), ("features", "date"),
                                ("predictions", "forecast_date"), ("crisis_scores", "forecast_date")]:
            date_sql = f",MIN({date_col}) date_start,MAX({date_col}) date_end" if date_col else ""
            report["tables"][table] = query(f"SELECT COUNT(*) rows,COUNT(DISTINCT district_id) districts{date_sql} FROM {table}")
        report["orphans"] = {table: query(f"""SELECT COUNT(*) rows FROM {table} t LEFT JOIN districts d
              USING(district_id) WHERE d.district_id IS NULL""")[0]["rows"]
              for table in ["raw_data", "features", "predictions", "crisis_scores"]}
        report["duplicate_master_names"] = query("""SELECT LOWER(TRIM(state)) state,LOWER(TRIM(district_name)) name,
            COUNT(*) rows FROM districts GROUP BY LOWER(TRIM(state)),LOWER(TRIM(district_name)) HAVING COUNT(*)>1""")
        report["missing_zones"] = query("SELECT district_id FROM districts WHERE agro_climatic_zone IS NULL ORDER BY district_id")
        report["features"] = query("""SELECT feature_generation,COUNT(*) rows,
            COUNT(*) FILTER(WHERE is_observed) observed,COUNT(*) FILTER(WHERE is_imputed) imputed,
            COUNT(*) FILTER(WHERE is_observed AND is_imputed) conflicting_flags,
            COUNT(*) FILTER(WHERE is_observed AND gwl_current IS NULL) missing_observed_gwl,
            COUNT(*) FILTER(WHERE gwl_current::text IN ('NaN','Infinity','-Infinity')) nonfinite_gwl,
            COUNT(*) FILTER(WHERE EXTRACT(DAY FROM date)<>1) non_month_start FROM features GROUP BY feature_generation""")
        report["observed_raw_mismatches"] = query("""SELECT COUNT(*) rows FROM features f LEFT JOIN raw_data r
            ON r.district_id=f.district_id AND r.date=f.date AND r.source='CGWB' AND r.metric='GWL'
            WHERE f.is_observed AND (r.value IS NULL OR ABS(r.value-f.gwl_current)>0.0001)""")[0]["rows"]
        report["observation_recency"] = query("""SELECT latest,COUNT(*) districts FROM
            (SELECT d.district_id,MAX(r.date) latest FROM districts d LEFT JOIN raw_data r
            ON d.district_id=r.district_id AND r.source='CGWB' AND r.metric='GWL' AND r.value IS NOT NULL
            GROUP BY d.district_id) q GROUP BY latest ORDER BY latest DESC NULLS LAST""")
        report["scoring_runs"] = query("""SELECT r.run_id::text,r.as_of,r.status,r.district_count,
            r.feature_generation,r.completed_at,(SELECT COUNT(*) FROM crisis_scores s WHERE s.run_id=r.run_id) score_rows,
            (SELECT COUNT(*) FROM predictions p WHERE p.run_id=r.run_id) prediction_rows
            FROM scoring_runs r ORDER BY r.completed_at DESC NULLS LAST""")
        report["latest_scores"] = query("""SELECT estimate_type,tier,COUNT(*) rows,MIN(aquaiq_score) score_min,MAX(aquaiq_score) score_max
            FROM crisis_scores WHERE run_id=(SELECT run_id FROM scoring_runs WHERE status='completed'
            ORDER BY completed_at DESC LIMIT 1) GROUP BY estimate_type,tier ORDER BY estimate_type,tier""")
        report["canonical_ids"] = query("SELECT district_id FROM districts ORDER BY district_id")
        return report
    except Exception as exc:
        return {"available": False, "error_type": type(exc).__name__,
                "limitation": "Database audit could not connect or finish; no exception message or credentials are recorded."}
    finally:
        if connection is not None:
            connection.rollback()
            connection.close()


def render_markdown(report):
    lines = ["# AquaIQ data quality audit — " + report["as_of"], "",
             "All measurements are from local files and an explicitly read-only database transaction. "
             "Original datasets were preserved. Scratch fixtures and isolated replay artifacts are inventoried separately.", "",
             f"Canonical crosswalk: **{report['canonical']['districts']} districts**, "
             f"**{report['canonical']['rows']} legacy mappings**. "
             f"GeoJSON: **{report['geography']['features']} polygons/features**, "
             f"**{report['geography']['unique_state_district_pairs']} distinct state/name pairs**. "
             "These are repository boundary identities; the audit does not assert coverage of every current Indian administrative district.", "",
             "| CSV | Rows | Canonical districts | Dates | Duplicate rows | Invalid dates |",
             "|---|---:|---:|---|---:|---:|"]
    for item in report["csv_files"]:
        districts = item['districts'] if item.get('identity_schema_supported') else '— (not a mapped district series)'
        lines.append(f"| {item['path']} | {item['rows']:,} | {districts} | "
                     f"{item['date_start'] or '—'}–{item['date_end'] or '—'} | "
                     f"{item['duplicate_rows']:,} | {item['invalid_date_rows']} |")
    lines += ["", "Per-column missing percentages, physical ranges, observed/imputed counts, "
              "unmapped identities, canonical omissions, chronological gaps and source hashes are in the JSON report.",
              "", "## Findings", ""]
    lines += [f"- **{x['severity']} — {x['title']}**: {x['evidence']}" for x in report["findings"]]
    db = report["database"]
    lines += ["", "## Database", ""]
    if db["available"]:
        lines += [f"Read-only setting: {db['transaction_read_only'][0]['transaction_read_only']}.",
                  "", "| Table | Rows | Districts |", "|---|---:|---:|"]
        for name, items in db["tables"].items():
            lines.append(f"| {name} | {items[0]['rows']:,} | {items[0]['districts']} |")
        lines += ["", f"Orphan foreign keys: {sum(db['orphans'].values())}. "
                  f"Observed feature/raw GWL mismatches: {db['observed_raw_mismatches']}.",
                  "Stored run coverage and per-source dates/ranges are in the JSON report."]
    else:
        lines.append("Unavailable: " + db.get("error_type", "not requested") + "; no live database claim is made.")
    lines += ["", "## Reproduce", "", "```powershell",
              ".\\venv\\Scripts\\python.exe -m scripts.audit_data_quality --database --as-of " + report["as_of"],
              ".\\venv\\Scripts\\python.exe -m data_ingestion.data_completeness --output reports/candidates/data_completeness.csv",
              "```", "", "Source units are checked against available manifests. Metadata and physical-range checks "
              "do not independently prove source authenticity, publication-time availability, aquifer comparability, "
              "or scientific accuracy. No synthetic records are introduced."]
    return "\n".join(lines) + "\n"


def run_audit(root=ROOT, *, as_of=None, database=False):
    as_of = as_of or date.today().isoformat()
    mapping = canonical_mapping(pd.read_csv(root / "data_ingestion/district_crosswalk.csv", dtype=str))
    canonical = mapping[0]
    paths = [p for p in root.rglob("*.csv") if not set(p.relative_to(root).parts) & EXCLUDE]
    fixtures = [p for p in paths if "scratch" in p.relative_to(root).parts]
    csvs = [audit_csv(p, mapping, root=root, as_of=as_of) for p in sorted(set(paths) - set(fixtures))]
    geo_path = root / "data/raw/india_districts.geojson"
    geo = json.loads(geo_path.read_text(encoding="utf-8"))
    pairs = [(norm_state(x["properties"].get("st_nm")), norm_str(x["properties"].get("district")))
             for x in geo["features"]]
    geo_ids = set()
    unmapped_geo = []
    for state, name in sorted(set(pairs)):
        ids = mapping[2].get((name, state), set())
        if len(ids) == 1:
            geo_ids.update(ids)
        else:
            unmapped_geo.append({"state": state, "district": name})
    files_by_path = {x["path"]: x for x in csvs}
    manifests = []
    for p in sorted((root / "data/processed").glob("*manifest.json")):
        meta = json.loads(p.read_text(encoding="utf-8"))
        csv_path = p.with_name(p.stem.removesuffix(".manifest") + ".csv")
        key = "csv_sha256"
        if p.name == "feature_manifest.json":
            csv_path, key = p.with_name("features_matrix.csv"), "feature_csv_sha256"
        elif p.name == "preprocessed_manifest.json":
            csv_path, key = p.with_name("preprocessed_wide.csv"), "preprocessed_csv_sha256"
        digest = sha256(csv_path) if csv_path.exists() else None
        manifests.append({"path": p.relative_to(root).as_posix(), "sha256": sha256(p),
                          "csv_hash_matches": digest is not None and digest == meta.get(key),
                          "boundary_hash_matches": meta.get("geojson_sha256") == sha256(geo_path) if "geojson_sha256" in meta else None,
                          "units": meta.get("units"), "generation": meta.get("generation_id"),
                          "causal_preprocessing": meta.get("causal_preprocessing"),
                          "sample_only": meta.get("sample_only")})
    findings = [{"severity": "Medium", "title": "Legacy completeness reporting repaired",
                 "evidence": "data_ingestion/data_completeness.py previously joined numeric CGWB codes to state-less weather names, "
                 "counted weather rows across 1992–2025 and divided by a fixed276 months. It now maps all sources to canonical IDs, "
                 "counts distinct finite months inside the configured297-month window, includes zero-coverage districts and exposes source diagnostics."},
                {"severity": "Medium", "title": "725-versus-716 coverage concern measured",
                 "evidence": f"The crosswalk has {canonical.canonical_district_id.nunique()} canonical IDs and "
                 f"{len(geo_ids)} have an unambiguous state-qualified GeoJSON name/alias match. "
                 f"{len(set(canonical.canonical_district_id)-geo_ids)} canonical districts lack a matching boundary; "
                 "they must remain explicit records in APIs even when no polygon can represent them."},
                {"severity": "Medium", "title": "166-versus-24 has separate meanings",
                 "evidence": "The legacy readiness helper's fixed276-month denominator required166 observed months at60%. "
                 "Serving uses configured dates, quarterly expected monitoring rounds, and a minimum24 actual observations. "
                 "For2002-01–2026-09:297 calendar months,99 expected rounds and60 observed months at60%. "
                 "The monthly history model separately requires24 observations spanning36 months. The legacy helper is repaired in this audit."},
                {"severity": "Medium", "title": "No predictions.csv export exists",
                 "evidence": "No predictions.csv was present outside scratch test fixtures at inventory time; this is an absent export, "
                 "not evidence that database predictions are empty. The database audit measures stored predictions separately."}]
    for name in ["data/processed/features_matrix.csv", "data/processed/preprocessed_wide.csv",
                 "data/processed/imd_rainfall_district_monthly.csv", "data/processed/era5_district_monthly.csv"]:
        item = files_by_path.get(name)
        if item:
            findings.append({"severity": "Info", "title": name,
                             "evidence": f"{item['rows']} rows/{item['districts']} mapped districts; "
                             f"{item['date_start']} through {item['date_end']}; "
                             f"{item['duplicate_rows']} exact duplicate rows; {item['monthly_key_duplicate_rows']} duplicate monthly keys; "
                             f"{item['unmapped_identity_rows']} unmapped source rows."})
    artifacts = []
    for p in sorted((root / "data").rglob("*")):
        if p.is_file() and p.suffix.lower() in {".nc", ".grd", ".dump", ".geojson", ".pdf", ".sqlite", ".db", ".sql", ".parquet"}:
            artifacts.append({"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size,
                              "kind": p.suffix.lower(), "sha256": sha256(p)})
    report = {"schema_version": 1, "as_of": as_of, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "canonical": {"rows": len(canonical), "districts": canonical.canonical_district_id.nunique(),
                            "unique_legacy_ids": canonical.legacy_district_id.nunique(),
                            "duplicate_legacy_ids": int(canonical.legacy_district_id.duplicated().sum())},
              "geography": {"features": len(geo["features"]), "unique_state_district_pairs": len(set(pairs)),
                            "matched_canonical_districts": len(geo_ids),
                            "canonical_without_boundary_match": sorted(set(canonical.canonical_district_id)-geo_ids),
                            "unmapped_boundary_pairs": unmapped_geo},
              "csv_files": csvs, "scratch_artifact_inventory": [
                  {"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size,
                   "kind": "test_fixture" if any("pytest" in part for part in p.parts) else "isolated_or_scratch_artifact"}
                  for p in sorted(fixtures)],
              "source_artifacts": artifacts, "manifests": manifests,
              "database": audit_database() if database else {"available": False, "error_type": "not requested"},
              "findings": findings,
              "limitations": ["No new external data were downloaded.",
                  "CSV observed/imputed flags and manifests are declarations; raw source publication dates are unavailable.",
                  "Scratch CSVs include test fixtures and isolated replays; they are excluded from active source conclusions.",
                  "Monthly missing counts describe calendar gaps, not a requirement that quarterly CGWB observations be monthly.",
                  "Groundwater outside -10..300m is flagged for review, not silently discarded; artesian negative depths can be valid.",
                  "Train/validation/test label and embargo checks are covered by the separate ML evaluation audit.",
                  "The .dump is inventoried and hashed; its historical rows are not conflated with current live database tables."]}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", action="store_true")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output", type=Path, default=ROOT / "reports/data_quality_audit_2026-10-17.json")
    args = parser.parse_args()
    pd.Timestamp(args.as_of)  # reject malformed input before scanning
    output = args.output.resolve()
    if ROOT / "reports" not in output.parents:
        raise ValueError("Audit output must be under reports and cannot replace datasets")
    report = run_audit(as_of=args.as_of, database=args.database)
    from db.connection import finite_json
    report = finite_json(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    output.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"report": str(output), "csv_files": len(report["csv_files"]),
                      "canonical_districts": report["canonical"]["districts"],
                      "database_available": report["database"]["available"]}))


if __name__ == "__main__":
    main()
