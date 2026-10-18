"""Read saved predictions and legacy source records; never fit or alter source data.

Default writes raw_lineage.json once beside this script. --verify-only recomputes
the audit and compares the saved JSON without writing anything. No DB imports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EXPERIMENT = ROOT / "reports/candidates/six_month_selection_20261017/experiment_v2"
INPUTS = [
    ROOT / "data/raw/cgwb_combined.csv",
    ROOT / "data_ingestion/district_crosswalk.csv",
    ROOT / "data_ingestion/ingest_cgwb.py",
    ROOT / "preprocessing/pipeline.py",
    ROOT / "preprocessing/features.py",
    ROOT / "data/processed/feature_manifest.json",
    ROOT / "data/processed/imd_rainfall_district_monthly.manifest.json",
    ROOT / "data/processed/era5_district_monthly.manifest.json",
    EXPERIMENT / "primary_observed_origin_predictions.csv",
    EXPERIMENT / "protocol.json",
]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint():
    return {str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path) for path in INPUTS}


def describe(series):
    return {str(k): float(v) for k, v in series.describe().items()}


def iso(value):
    return pd.Timestamp(value).isoformat()


def run():
    before = fingerprint()
    cases = pd.read_csv(EXPERIMENT / "primary_observed_origin_predictions.csv", parse_dates=["date", "target_date"])
    crosswalk = pd.read_csv(ROOT / "data_ingestion/district_crosswalk.csv", dtype=str)
    if crosswalk.groupby("legacy_district_id").canonical_district_id.nunique().gt(1).any():
        raise ValueError("Ambiguous canonical crosswalk")
    mapping = crosswalk.set_index("legacy_district_id").canonical_district_id.to_dict()
    raw = pd.read_csv(INPUTS[0], dtype={"district_code": str},
                      usecols=["date", "district_code", "station_name", "latitude", "longitude", "currentlevel"])
    raw["reported_date"] = pd.to_datetime(raw.date, errors="coerce")
    raw["month"] = raw.reported_date.dt.to_period("M").dt.to_timestamp()
    raw["district_id"] = raw.district_code.str.strip().map(mapping)
    raw["currentlevel"] = pd.to_numeric(raw.currentlevel, errors="coerce")
    raw = raw.loc[np.isfinite(raw.currentlevel) & raw.reported_date.notna() & raw.district_id.notna()].copy()
    # Location/name proxies can merge distinct wells; they are not certified IDs.
    raw["proxy"] = (raw.station_name.astype(str).str.strip().str.casefold() + "|"
                    + pd.to_numeric(raw.latitude, errors="coerce").round(5).astype(str) + "|"
                    + pd.to_numeric(raw.longitude, errors="coerce").round(5).astype(str))
    monthly = raw.groupby(["district_id", "month"]).agg(
        value=("currentlevel", "mean"), n=("currentlevel", "size"),
        proxy_wells=("proxy", "nunique"), first=("reported_date", "min"), last=("reported_date", "max"))
    panels = raw.groupby(["district_id", "month"]).proxy.agg(set).to_dict()
    rows = []
    for case in cases.itertuples():
        origin_key = (case.district_id, case.date)
        target_key = (case.district_id, case.target_date)
        seasonal_key = (case.district_id, case.target_date - pd.DateOffset(months=12))
        origin, target, seasonal = (monthly.loc[key] for key in (origin_key, target_key, seasonal_key))
        op, tp, sp = (panels[key] for key in (origin_key, target_key, seasonal_key))
        rows.append({"district_id": case.district_id, "date": case.date, "target_date": case.target_date,
            "origin_first": origin["first"], "origin_last": origin["last"],
            "target_first": target["first"], "target_last": target["last"],
            "origin_error": abs(origin.value - case.persistence),
            "target_error": abs(target.value - case.actual),
            "seasonal_error": abs(seasonal.value - case.seasonal_naive),
            "jaccard_origin_target": len(op & tp) / len(op | tp),
            "jaccard_seasonal_target": len(sp & tp) / len(sp | tp),
            "origin_target_overlap": len(op & tp), "seasonal_target_overlap": len(sp & tp),
            "all_three_overlap": len(op & tp & sp),
            "identical_origin_target": op == tp, "identical_seasonal_target": sp == tp})
    joined = pd.DataFrame(rows)
    if joined[["origin_error", "target_error", "seasonal_error"]].max().max() > 1e-5:
        raise ValueError("Saved primary values are not reproduced within storage rounding")

    target_keys = cases[["district_id", "target_date"]].rename(columns={"target_date": "month"})
    target_raw = raw.merge(target_keys, on=["district_id", "month"], how="inner", validate="many_to_one")
    proxy_month = target_raw.groupby(["district_id", "month", "proxy"], as_index=False).agg(
        value=("currentlevel", "mean"), row_count=("currentlevel", "size"),
        unique_values=("currentlevel", "nunique"), unique_reported_dates=("reported_date", "nunique"))
    repeated = proxy_month.unique_values.eq(1) & proxy_month.unique_reported_dates.gt(1)
    equal_proxy = proxy_month.groupby(["district_id", "month"]).value.mean()
    reading_weighted = target_raw.groupby(["district_id", "month"]).currentlevel.mean()
    aggregate_difference = (equal_proxy - reading_weighted).abs()
    later_cases = cases.loc[cases.target_date.dt.year.ge(2022)].copy()
    later_rows = []
    for district, selected in later_cases.groupby("district_id", sort=True):
        own = target_raw.loc[target_raw.district_id.eq(district) & target_raw.month.dt.year.ge(2022)]
        own_proxy_month = proxy_month.loc[proxy_month.district_id.eq(district) & proxy_month.month.dt.year.ge(2022)]
        constant = own_proxy_month.unique_values.eq(1) & own_proxy_month.unique_reported_dates.gt(1)
        own_means = own.groupby("month").currentlevel.mean()
        later_rows.append({"district_id": district, "cases": len(selected),
            "target_periods": selected.target_date.dt.strftime("%Y-%m").tolist(),
            "source_rows": len(own), "unique_proxy_wells": own.proxy.nunique(),
            "source_reported_first": iso(own.reported_date.min()), "source_reported_last": iso(own.reported_date.max()),
            "proxy_months": len(own_proxy_month),
            "constant_value_multiple_reported_dates_proxy_months": int(constant.sum()),
            "rows_in_those_proxy_months": int(own_proxy_month.loc[constant, "row_count"].sum()),
            "target_monthly_mean_min": float(own_means.min()), "target_monthly_mean_max": float(own_means.max()),
            "target_equals_origin_at_1e_5": int(np.isclose(selected.actual, selected.persistence, rtol=0, atol=1e-5).sum()),
            "target_equals_seasonal_at_1e_5": int(np.isclose(selected.actual, selected.seasonal_naive, rtol=0, atol=1e-5).sum())})

    faridabad = cases.loc[cases.district_id.eq("HR-Faridabad")].iloc[0]
    faridabad_panels = {}
    for label, date in (("origin", faridabad.date), ("target", faridabad.target_date),
                        ("seasonal", faridabad.target_date - pd.DateOffset(months=12))):
        own = raw.loc[raw.district_id.eq("HR-Faridabad") & raw.month.eq(date)]
        station = own.groupby("proxy", as_index=False).agg(value=("currentlevel", "mean"),
            source_rows=("currentlevel", "size"), first=("reported_date", "min"), last=("reported_date", "max"))
        faridabad_panels[label] = {"month": date.date().isoformat(), "reading_weighted_mean": float(own.currentlevel.mean()),
            "proxy_wells": [{**record, "first": iso(record["first"]), "last": iso(record["last"])}
                            for record in station.to_dict("records")]}

    result = {
        "purpose": "Read-only source-lineage diagnostics; no fitting, retuning, reselection or rescoring against modified labels.",
        "input_sha256": before,
        "primary_cases": len(cases), "raw_monthly_rejoin_cases": len(joined),
        "mean_join": {"implementation": "ingest_cgwb.aggregate_well_readings averages all finite raw currentlevel rows per mapped district/calendar month; higher-frequency wells receive more weight.",
            "max_absolute_difference_m": {key: float(joined[f"{key}_error"].max()) for key in ("origin", "target", "seasonal")},
            "all_627_rejoined_values_within_1e_5_m": bool(joined[["origin_error", "target_error", "seasonal_error"]].max().max() <= 1e-5),
            "storage_rounding_note": "Differences up to about 3.34e-6 m are consistent with stored aggregate float precision; no source values are changed.",
            "target_equal_proxy_mean_sensitivity": {"cases_different_by_more_than_1e_5_m": int(aggregate_difference.gt(1e-5).sum()),
                "absolute_difference_m": describe(aggregate_difference),
                "meaning": "Descriptive weighting sensitivity only. Name/location proxies can merge wells; alternate target means were not substituted or scored."}},
        "date_buckets": {"meaning": "Source date is a reported raw date, not independently certified fresh field acquisition. Ingestion replaces its day with day 1.",
            "origins_last_reported_date_after_saved_month_start": int(joined.origin_last.gt(joined.date).sum()),
            "targets_last_reported_date_after_saved_month_start": int(joined.target_last.gt(joined.target_date).sum()),
            "origin_last_reported_day_offset": describe((joined.origin_last - joined.date).dt.days),
            "target_last_reported_day_offset": describe((joined.target_last - joined.target_date).dt.days),
            "latest_target_minus_latest_origin_days": describe((joined.target_last - joined.origin_last).dt.days),
            "horizon": "Exactly six calendar-month bucket offsets, not exactly six months from actual acquisition or forecast issue time."},
        "proxy_panel_composition": {"proxy_definition": "Casefolded trimmed station_name plus latitude/longitude rounded to five decimal places. No certified stable well ID; same-location wells and renaming/relocation may be conflated or split.",
            "jaccard_origin_target": describe(joined.jaccard_origin_target),
            "jaccard_seasonal_target": describe(joined.jaccard_seasonal_target),
            "no_shared_origin_target": int(joined.origin_target_overlap.eq(0).sum()),
            "no_shared_seasonal_target": int(joined.seasonal_target_overlap.eq(0).sum()),
            "any_proxy_shared_all_three": int(joined.all_three_overlap.gt(0).sum()),
            "identical_origin_target_panels": int(joined.identical_origin_target.sum()),
            "identical_seasonal_target_panels": int(joined.identical_seasonal_target.sum()),
            "faridabad": faridabad_panels},
        "repeated_measurement_patterns": {"target_source_rows": len(target_raw), "target_proxy_months": len(proxy_month),
            "constant_value_multiple_reported_dates_proxy_months": int(repeated.sum()),
            "rows_in_those_proxy_months": int(proxy_month.loc[repeated, "row_count"].sum()),
            "target_equals_origin_at_1e_5": int(np.isclose(cases.actual, cases.persistence, rtol=0, atol=1e-5).sum()),
            "target_equals_seasonal_at_1e_5": int(np.isclose(cases.actual, cases.seasonal_naive, rtol=0, atol=1e-5).sum()),
            "2022_and_2023": later_rows,
            "interpretation": "Repeated same-value source rows on distinct reported dates may be true stable readings, source carry-forward, republication or duplicates across records. Available metadata cannot distinguish these; is_observed marks finite source monthly evidence, not independently certified fresh acquisition."},
        "issuance_availability": {"known": "No future calendar row is used by causal preprocessing. Lag joins are exact month offsets; normal uses preceding years; transformations are fixed by the saved protocol.",
            "unverified": "No raw/provider publication timestamps, per-value revision vintages or archived as-of snapshots establish operational availability. Full-origin-month rainfall totals and ERA5 monthly means/totals cannot be known at the saved month-start bucket. Groundwater reported dates also generally follow that bucket.",
            "required": "Separate observation month, reported acquisition timestamp, provider publication timestamp, retrieval timestamp, revision ID and actual forecast issued_at. Enforce max(feature available_at) <= issued_at and commit predictions before target acquisition. Report effective lead from issued_at to the target observation window."},
        "units": {"canonical": "feature_manifest declares groundwater m_bgl, rainfall/ET mm/month and temperature degC. No target scaling is applied in the saved selection.",
            "legacy_limit": "The legacy currentlevel header has no unit or datum annotation and no source transport manifest. Repository conventions do not independently certify original measurement datum.",
            "new_source_limit": "The separate Gujarat header establishes metres but not below-ground datum; RL_MSL is entirely null. Keep it separate until datum is certified."},
    }
    if before != fingerprint():
        raise RuntimeError("An audit input changed while it was being read")
    result["inputs_unchanged_after_read"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    output = HERE / "raw_lineage.json"
    if not args.verify_only and output.exists():
        parser.error(f"Refusing to overwrite {output}; use --verify-only")
    result = run()
    if args.verify_only:
        if result != json.loads(output.read_text(encoding="utf-8")):
            raise RuntimeError("Recomputed raw-lineage audit differs from saved summary")
        print("Verified raw_lineage.json; all audit inputs unchanged; no files written.")
    else:
        with output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
        print(f"Saved {output}; all audit inputs unchanged; no models fitted.")


if __name__ == "__main__":
    main()
