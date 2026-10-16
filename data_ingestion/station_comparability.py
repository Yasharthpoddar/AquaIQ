"""Offline, conservative comparison of CGWB station snapshots.

No station database is created. A normalized location fingerprint is a matching
aid, not a verified globally unique well ID. Exact matches do not establish that
two records measured the same aquifer or unchanged well construction.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"state_name", "block", "village", "latitude", "longitude",
            "gwl_m_bgl", "units", "source_sha256", "source_file", "source_month"}


def _name(value):
    value = "" if pd.isna(value) else str(value)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def candidate_output(path, inputs=()):
    """Require a new file under this checkout's candidate/update folders."""
    path = Path(path).resolve()
    allowed = (ROOT / "reports/candidates", ROOT / "data/raw/updates")
    if not any(path.is_relative_to(base.resolve()) for base in allowed):
        raise ValueError("Output must be inside reports/candidates or data/raw/updates")
    if path in {Path(item).resolve() for item in inputs} or path.exists():
        raise ValueError("Output already exists or aliases an input; choose a new candidate path")
    return path


def prepare_snapshot(frame, *, as_of):
    """Validate source rows; exclude ambiguous location/date readings.

    Audited CSV rejection reasons remain authoritative. Raw extracted CSVs can
    be compared, but have no canonical district until independently mapped.
    """
    missing = REQUIRED - set(frame)
    if missing or not ({"observation_date", "reported_date"} & set(frame)):
        raise ValueError(f"Station snapshot lacks required fields: {sorted(missing)} and/or observation date")
    frame = frame.copy().reset_index(drop=True)
    if frame.empty:
        raise ValueError("Station snapshot is empty")
    cutoff = pd.Timestamp(as_of).normalize()
    if pd.isna(cutoff) or cutoff > pd.Timestamp.today().normalize():
        raise ValueError("as_of must be a valid date no later than today")
    reasons = [[] for _ in range(len(frame))]

    def reject(mask, reason):
        for index in frame.index[pd.Series(mask, index=frame.index).fillna(True)]:
            reasons[index].append(reason)

    for col in ("latitude", "longitude", "gwl_m_bgl"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if "observation_date" in frame:
        frame["actual_date"] = pd.to_datetime(frame.observation_date, format="%Y-%m-%d", errors="coerce")
        if "reported_date" in frame:
            reported = pd.to_datetime(frame.reported_date, format="%d-%m-%Y", errors="coerce")
            reject(reported.isna() | reported.ne(frame.actual_date), "reported_and_audited_date_mismatch")
    else:
        frame["actual_date"] = pd.to_datetime(frame.reported_date, format="%d-%m-%Y", errors="coerce")
    reject(frame.actual_date.isna(), "invalid_observation_date")
    reject(frame.actual_date.gt(cutoff), "future_observation")
    reject(frame.actual_date.dt.strftime("%Y-%m").ne(frame.source_month), "source_month_mismatch")
    reject(~np.isfinite(frame.latitude) | ~frame.latitude.between(6, 38)
           | ~np.isfinite(frame.longitude) | ~frame.longitude.between(68, 98), "invalid_coordinates")
    reject(~np.isfinite(frame.gwl_m_bgl) | frame.gwl_m_bgl.lt(0), "invalid_depth")
    reject(frame.units.ne("m_bgl"), "unverified_units")
    reject(~frame.source_sha256.fillna("").astype(str).str.fullmatch(r"[0-9a-fA-F]{64}"), "missing_source_digest")
    reject(frame.source_file.fillna("").astype(str).str.strip().eq(""), "missing_source_file")
    for col in ("state_name", "block", "village"):
        frame[f"normal_{col}"] = frame[col].map(_name)
        reject(frame[f"normal_{col}"].eq(""), f"missing_{col}")
    if "audit_reason" in frame:
        reject(frame.audit_reason.fillna("").astype(str).str.strip().ne(""), "source_audit_rejected")
    for col in ("district_id", "aquifer", "station_id"):
        if col not in frame:
            frame[col] = ""
        frame[col] = frame[col].fillna("").astype(str).str.strip()
    # District names are deliberately excluded: district splits/renames do not
    # identify a well. Coordinates are never snapped to a nearby station.
    frame["location_key"] = ["|".join((state, block, village, f"{lat:.5f}", f"{lon:.5f}"))
                             for state, block, village, lat, lon in zip(
                                 frame.normal_state_name, frame.normal_block,
                                 frame.normal_village, frame.latitude, frame.longitude)]
    identity = ["location_key", "actual_date"]
    conflicts = frame.groupby(identity, dropna=False).gwl_m_bgl.transform("nunique").gt(1)
    reject(conflicts, "conflicting_station_date_depths")
    for col in ("district_id", "aquifer", "station_id"):
        normalized = frame[col].map(_name) if col == "aquifer" else frame[col]
        reject(normalized.groupby(frame.location_key).transform("nunique").gt(1), f"ambiguous_{col}")
    duplicate = frame.duplicated(identity + ["gwl_m_bgl"], keep="first") & ~conflicts
    reject(duplicate, "duplicate_station_date_reading")
    frame["comparison_rejection"] = [";".join(values) for values in reasons]
    accepted = frame.loc[frame.comparison_rejection.eq("")].copy()
    months = accepted.actual_date.dt.to_period("M").unique()
    if len(months) > 1:
        raise ValueError("Each snapshot must contain one observation month; split multi-month CSVs first")
    summary = {"input_rows": len(frame), "accepted_readings": len(accepted),
               "excluded_rows": int(frame.comparison_rejection.ne("").sum()),
               "exclusion_reasons": dict(Counter(reason for values in reasons for reason in values)),
               "month": str(months[0]) if len(months) else None,
               "source_audit_present": "audit_reason" in frame}
    return accepted, frame, summary


def _station_means(frame):
    if frame.empty:
        return pd.DataFrame(columns=["location_key", "gwl_m_bgl", "first_date", "last_date", "district_id", "aquifer", "station_id"])
    return frame.groupby("location_key", as_index=False).agg(
        gwl_m_bgl=("gwl_m_bgl", "mean"), first_date=("actual_date", "min"),
        last_date=("actual_date", "max"), district_id=("district_id", "first"),
        aquifer=("aquifer", "first"), station_id=("station_id", "first"))


def compare_snapshots(snapshots, *, as_of):
    """Compare consecutive months; report paired changes separately from means."""
    if len(snapshots) < 2:
        raise ValueError("At least two independently dated station snapshots are required")
    prepared = [prepare_snapshot(frame, as_of=as_of) for frame in snapshots]
    if any(item[2]["month"] is None for item in prepared):
        raise ValueError("Every snapshot requires at least one valid station reading")
    prepared.sort(key=lambda item: item[2]["month"])
    if len({item[2]["month"] for item in prepared}) != len(prepared):
        raise ValueError("Snapshots must represent distinct observation months")
    pairs, rows = [], []
    for earlier, later in zip(prepared, prepared[1:]):
        a, b = _station_means(earlier[0]), _station_means(later[0])
        joined = a.merge(b, on="location_key", suffixes=("_before", "_after"))
        exclusions, accepted = Counter(), []
        for row in joined.to_dict("records"):
            reason = None
            if row["last_date_before"] >= row["first_date_after"]:
                reason = "overlapping_observation_dates"
            for field in ("district_id", "aquifer", "station_id"):
                old, new = row[f"{field}_before"], row[f"{field}_after"]
                if field == "aquifer":
                    old, new = _name(old), _name(new)
                if old != new:
                    reason = f"{field}_mismatch_or_missing_counterpart"
                    break
            if reason:
                exclusions[reason] += 1
                continue
            row["depth_change_m"] = float(row["gwl_m_bgl_after"] - row["gwl_m_bgl_before"])
            row["aquifer_metadata_consistent"] = bool(row["aquifer_before"])
            row["source_station_id_present"] = bool(row["station_id_before"])
            accepted.append(row)
            rows.append({**row, "month_before": earlier[2]["month"], "month_after": later[2]["month"]})
        matched = len(accepted)
        changes = [row["depth_change_m"] for row in accepted]
        district_rows = []
        districts = sorted(set(a.district_id) | set(b.district_id))
        for district in districts:
            if not district:
                continue
            own_a, own_b = a[a.district_id.eq(district)], b[b.district_id.eq(district)]
            own = [row for row in accepted if row["district_id_before"] == district]
            district_rows.append({"district_id": district, "stations_before": len(own_a),
                "stations_after": len(own_b), "matched_stations": len(own),
                "matched_mean_depth_change_m": float(np.mean([r["depth_change_m"] for r in own])) if own else None,
                "all_station_mean_change_m": float(own_b.gwl_m_bgl.mean() - own_a.gwl_m_bgl.mean()) if len(own_a) and len(own_b) else None,
                "composition_changed": set(own_a.location_key) != set(own_b.location_key)})
        pairs.append({"month_before": earlier[2]["month"], "month_after": later[2]["month"],
            "same_calendar_month": earlier[2]["month"][-2:] == later[2]["month"][-2:],
            "stations_before": len(a), "stations_after": len(b), "exact_location_matches": len(joined),
            "matched_stations": matched, "unmatched_before": len(a) - matched,
            "unmatched_after": len(b) - matched, "pair_exclusions": dict(exclusions),
            "overlap_fraction_before": matched / len(a), "overlap_fraction_after": matched / len(b),
            "matched_mean_depth_change_m": float(np.mean(changes)) if changes else None,
            "all_station_mean_change_m": float(b.gwl_m_bgl.mean() - a.gwl_m_bgl.mean()),
            "composition_changed": set(a.location_key) != set(b.location_key), "districts": district_rows})
    matched_columns = ["location_key", "gwl_m_bgl_before", "first_date_before", "last_date_before",
        "district_id_before", "aquifer_before", "station_id_before", "gwl_m_bgl_after", "first_date_after",
        "last_date_after", "district_id_after", "aquifer_after", "station_id_after", "depth_change_m",
        "aquifer_metadata_consistent", "source_station_id_present", "month_before", "month_after"]
    return {"status": "comparison_only", "calibrated": False, "snapshots": [item[2] for item in prepared],
        "pairs": pairs, "limitations": [
            "Location fingerprints are matching aids, not globally unique or independently verified well IDs.",
            "Positive depth change means a deeper water table. Neither paired nor aggregate changes establish a cause or recovery.",
            "Aquifer and well-construction continuity remain unverified when absent from source metadata.",
            "Different calendar months include seasonal effects; this tool does not estimate a long-term trend.",
            "Raw station_records have no canonical district mapping; unassigned rows cannot provide district statistics.",
            "No station persistence table, database ingestion, model changes or production publication is implemented."]}, pd.DataFrame(rows, columns=matched_columns)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", nargs="+", type=Path)
    parser.add_argument("--as-of", default=str(pd.Timestamp.today().date()))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--matched-output", type=Path)
    args = parser.parse_args(argv)
    if not args.snapshots:
        print(json.dumps({"status": "offline_plan", "required": sorted(REQUIRED),
            "dates": "observation_date (YYYY-MM-DD) or reported_date (DD-MM-YYYY)",
            "next": "Provide two or more verified audited station CSVs from distinct months."}, indent=2))
        return 0
    outputs = [candidate_output(path, args.snapshots) for path in (args.output, args.matched_output) if path]
    if len(set(outputs)) != len(outputs):
        raise ValueError("Candidate outputs must be distinct")
    report, matches = compare_snapshots([pd.read_csv(path) for path in args.snapshots], as_of=args.as_of)
    report["sources"] = [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in args.snapshots]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if args.matched_output:
        args.matched_output.parent.mkdir(parents=True, exist_ok=True)
        matches.to_csv(args.matched_output, index=False)
    printed = report if args.output is None else {"status": report["status"],
        "report": str(args.output), "snapshots": report["snapshots"],
        "pairs": [{key: value for key, value in pair.items() if key != "districts"} for pair in report["pairs"]]}
    print(json.dumps(printed, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
