"""Read-only historical evaluation of the exploratory monthly projection.

Fits are recreated at fixed rolling calendar cutoffs, then compared only with
verified future observations. This report does not promote a model or alter
scoring, features, checkpoints, configuration, or the database.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.monthly_projection import MODEL_VERSION, fit_projection, predict_depth
from models.xgboost_model import observed_mask

YEARS = (2012, 2015, 2018, 2020)
ORIGIN_MONTHS = (1, 5, 8, 11)
HORIZONS = (1, 2, 3, 4, 5, 6, 60, 69, 75)


def metrics(frame, prediction_column):
    if frame.empty:
        return {"n": 0, "districts": 0, "rmse_m": None, "mae_m": None,
                "median_absolute_error_m": None, "bias_m": None}
    errors = frame[prediction_column].to_numpy() - frame.actual.to_numpy()
    return {"n": len(frame), "districts": int(frame.district_id.nunique()),
            "rmse_m": float(np.sqrt(np.mean(errors ** 2))),
            "mae_m": float(np.mean(np.abs(errors))),
            "median_absolute_error_m": float(np.median(np.abs(errors))),
            "bias_m": float(np.mean(errors))}


def summarize(frame):
    paired = frame[np.isfinite(frame.seasonal_naive)] if len(frame) else frame
    result = {"projection": metrics(frame, "projection"),
              "persistence_baseline": metrics(frame, "persistence"),
              "seasonal_paired_comparison": {
                  "projection": metrics(paired, "projection"),
                  "persistence_baseline": metrics(paired, "persistence"),
                  "seasonal_naive_baseline": metrics(paired, "seasonal_naive")}}
    if len(frame):
        result["actual_target_date_range"] = [frame.target.min(), frame.target.max()]
        result["actual_months_since_last_measurement_range"] = [
            int(frame.actual_lead.min()), int(frame.actual_lead.max())]
    return result


def evaluate(source):
    columns = ["district_id", "date", "gwl_current", "is_observed", "is_imputed"]
    source_frame = pd.read_csv(source, usecols=columns, parse_dates=["date"])
    depths = pd.to_numeric(source_frame.gwl_current, errors="coerce")
    observed = source_frame.loc[observed_mask(source_frame) & np.isfinite(depths)
                                & (depths >= 0)].copy()
    observed["gwl_current"] = depths.loc[observed.index]
    if observed.duplicated(["district_id", "date"]).any():
        raise ValueError("Duplicate verified district-month observations.")
    cutoffs = [pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)
               for year in YEARS for month in ORIGIN_MONTHS]
    candidates = {horizon: 0 for horizon in HORIZONS}
    missing_labels = {horizon: 0 for horizon in HORIZONS}
    rows, fits, rejected = [], 0, 0
    for _, (district, frame) in enumerate(observed.groupby("district_id", sort=True)):
        frame = frame.sort_values("date").reset_index(drop=True)
        truth = frame.set_index("date").gwl_current
        for cutoff in cutoffs:
            fit = fit_projection(frame, cutoff)
            if fit is None:
                rejected += 1
                continue
            fits += 1
            known = frame[frame.date <= cutoff]
            targets = [(cutoff.to_period("M") + horizon).to_timestamp() for horizon in HORIZONS]
            predictions = predict_depth(fit, targets)
            for horizon, target, prediction in zip(HORIZONS, targets, predictions):
                candidates[horizon] += 1
                if target not in truth.index:
                    missing_labels[horizon] += 1
                    continue
                seasonal_rows = known[known.date.dt.month.eq(target.month)]
                seasonal = float(seasonal_rows.gwl_current.iloc[-1]) if len(seasonal_rows) else np.nan
                actual_lead = (target.year - fit["origin"].year) * 12 + target.month - fit["origin"].month
                rows.append({"district_id": district, "cutoff": cutoff.date().isoformat(),
                             "target": target.date().isoformat(), "horizon": horizon,
                             "actual_lead": actual_lead, "actual": float(truth.loc[target]),
                             "projection": float(prediction), "persistence": fit["last_observed_gwl"],
                             "seasonal_naive": seasonal})
        if (_ + 1) % 100 == 0:
            print(f"Evaluated {_ + 1} districts, {fits} historical fits", flush=True)
    result = pd.DataFrame(rows, columns=["district_id", "cutoff", "target", "horizon", "actual_lead",
                                        "actual", "projection", "persistence", "seasonal_naive"])
    return {"created_at": datetime.now(timezone.utc).isoformat(),
            "model_version": MODEL_VERSION, "source": str(source), "units": "m_bgl",
            "projection_source_sha256": hashlib.sha256((ROOT / "models/monthly_projection.py").read_bytes()).hexdigest(),
            "feature_csv_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "protocol": {
                "fit_cutoffs": [cutoff.date().isoformat() for cutoff in cutoffs],
                "forecast_horizons_months": list(HORIZONS),
                "fit_evidence": "Only explicitly observed finite nonnegative depths available after each completed calendar month; no imputed values.",
                "evaluation_labels": "Only explicitly observed finite future district-month depths; missing monthly labels are omitted, never filled.",
                "persistence_baseline": "Last actual depth available at fit cutoff.",
                "seasonal_naive_baseline": "Latest same-calendar-month actual depth available at fit cutoff; paired comparisons use identical available labels.",
                "stale_gap_evaluation": "60, 69 and 75 months beyond historical cutoff, with no intervening updates. Actual lead from latest measurement is also reported.",
                "candidate_fits": fits, "insufficient_history_fits": rejected,
                "districts_with_observations": int(observed.district_id.nunique()),
                "observed_months": len(observed),
                "observed_date_range": [observed.date.min().date().isoformat(), observed.date.max().date().isoformat()],
                "limitations": [
                    "The selected quarterly historical origins produce correlated and sometimes overlapping evaluation labels.",
                    "Groundwater measurements concentrate in January, May, August and November; many monthly horizons have sparse validation coverage.",
                    "Historical comparisons do not verify current 2026 conditions or future 2027 estimates.",
                    "Availability is approximated by completed measurement months; original release dates and later data revisions are unknown.",
                    "This is an internal evaluation of a predefined exploratory method, not independent calibration or evidence of operational readiness.",
                    "Climate, pumping, changes in monitored wells and future interventions are excluded."]},
            "short_horizons_1_to_6_months": summarize(result[result.horizon <= 6]),
            "long_gaps_60_69_75_months": summarize(result[result.horizon >= 60]),
            "by_horizon_months": {str(horizon): {
                "candidate_targets": candidates[horizon], "missing_observed_labels": missing_labels[horizon],
                **summarize(result[result.horizon == horizon])} for horizon in HORIZONS},
            "assessment": {"status": "exploratory_historical_evaluation",
                           "sufficient_for_operational_use": False,
                           "current_period_accuracy_established": False}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/processed/features_matrix.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/monthly_projection_evaluation.json")
    args = parser.parse_args(argv)
    report = evaluate(args.input.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output),
                      "short_horizons": report["short_horizons_1_to_6_months"],
                      "long_gaps": report["long_gaps_60_69_75_months"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
