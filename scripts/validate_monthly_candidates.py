"""Development-only monthly model comparisons without publishing a model.

The default command prints an offline plan. Explicit --run loads verified local
features, excludes 2020 onward before forming any labels, and evaluates fixed
calendar-date panel folds. The sole output is an experimental candidate report.
Development residuals are not independent uncertainty-calibration evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.connection import finite_json
from models import climate_forecast as climate
from models import xgboost_model as source_model
from models.climate_inputs import forecast_weather
from models.xgboost_model import load_feature_matrix, observed_mask, _write_json

FINAL_PERIOD_START = pd.Timestamp("2020-01-01")
FOLDS = (
    {"fold": 1, "train_target_cutoff": "2010-12-31",
     "evaluation_origin_start": "2011-07-01", "evaluation_target_end": "2013-12-31"},
    {"fold": 2, "train_target_cutoff": "2013-12-31",
     "evaluation_origin_start": "2014-07-01", "evaluation_target_end": "2016-12-31"},
    {"fold": 3, "train_target_cutoff": "2016-12-31",
     "evaluation_origin_start": "2017-07-01", "evaluation_target_end": "2019-12-31"},
)
MIN_TRAINING_PAIRS = 30
MIN_EVALUATION_PAIRS = 6


def candidate_output(path: Path) -> Path:
    """Only a dedicated report directory may be written, including via symlinks."""
    path = Path(path).resolve()
    allowed = (ROOT / "reports/candidates/monthly_validation").resolve()
    protected = [(ROOT / name).resolve() for name in ("data", "models")]
    if (path.suffix.lower() != ".json" or not path.is_relative_to(allowed)
            or any(path.is_relative_to(directory) for directory in protected)):
        raise ValueError("Output must be a .json report inside reports/candidates/monthly_validation; "
                         "active models, input data and previous training reports are protected.")
    return path


def development_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Exclude the final period before label joins or any weather evaluation."""
    if (not frame.attrs.get("feature_generation_id")
            or frame.attrs.get("data_source") in (None, "unknown", "synthetic")):
        raise ValueError("Candidate validation requires verified real feature provenance.")
    if "date" not in frame:
        raise ValueError("Feature dates are required.")
    dates = pd.to_datetime(frame.date, errors="raise")
    if dates.isna().any():
        raise ValueError("Feature dates cannot be missing.")
    result = frame.loc[dates < FINAL_PERIOD_START].copy()
    result["date"] = dates.loc[result.index]
    result.attrs.update(frame.attrs)
    if result.empty:
        raise ValueError("No pre-2020 development features are available.")
    return result.sort_values(["district_id", "date"]).reset_index(drop=True)


def select_folds(choice="all") -> list[dict]:
    if str(choice) not in {"all", "1", "2", "3"}:
        raise ValueError("Fold must be all, 1, 2 or 3.")
    return [dict(fold) for fold in FOLDS if choice == "all" or str(fold["fold"]) == str(choice)]


def fold_pairs(pairs: pd.DataFrame, specification: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff = pd.Timestamp(specification["train_target_cutoff"])
    start = pd.Timestamp(specification["evaluation_origin_start"])
    end = pd.Timestamp(specification["evaluation_target_end"])
    first_allowed = (cutoff.to_period("M") + 7).to_timestamp()
    if start < first_allowed or end >= FINAL_PERIOD_START or end < start:
        raise ValueError("Fold must preserve a six-month embargo and exclude 2020 onward.")
    training = pairs.loc[pairs.target_date <= cutoff].copy()
    evaluation = pairs.loc[(pairs.origin_date >= start) & (pairs.target_date <= end)].copy()
    return training, evaluation


def model_parameters(n_jobs=1, trees=240) -> dict:
    if isinstance(n_jobs, bool) or not isinstance(n_jobs, int) or not 1 <= n_jobs <= 4:
        raise ValueError("n_jobs must be between 1 and 4.")
    if isinstance(trees, bool) or not isinstance(trees, int) or not 1 <= trees <= 2000:
        raise ValueError("trees must be between 1 and 2000.")
    return {**climate.PARAMETERS, "n_jobs": n_jobs, "n_estimators": trees}


def _default_model(**parameters):
    import xgboost as xgb
    return xgb.XGBRegressor(**parameters)


def _counts(pairs):
    counts = pairs.groupby("horizon_months").size() if len(pairs) else pd.Series(dtype=int)
    return {str(h): int(counts.get(float(h), 0)) for h in range(1, 7)}


def _fingerprint(frame, columns):
    digest = hashlib.sha256("|".join(columns).encode())
    digest.update(pd.util.hash_pandas_object(frame[columns], index=False).values.tobytes())
    return digest.hexdigest()


def assumed_weather_cases(model, frame, pairs, fold):
    """Optional per-case development residuals using the serving weather policy.

    This intentionally uses the same public input builders as the existing
    evaluator; it never substitutes observed future weather into predictions.
    """
    districts = {key: rows.copy() for key, rows in frame.groupby("district_id")}
    records = []
    for (district_id, origin), labels in pairs.groupby(["district_id", "origin_date"], sort=True):
        district = districts[district_id]
        cutoff = pd.Timestamp(origin) + pd.offsets.MonthEnd(0)
        weather = forecast_weather(district, cutoff)
        depth = float(labels.iloc[0].origin_gwl)
        inputs, _ = climate.origin_inputs(district, origin, cutoff, depth)
        if weather["status"] != "available" or inputs is None:
            continue
        predicted = np.maximum(0., depth + model.predict(climate.feature_rows(origin, weather["path"], inputs)))
        if len(predicted) != 6 or not np.isfinite(predicted).all():
            raise ValueError("Candidate model returned invalid six-month predictions.")
        known = district.loc[(district.date <= origin) & observed_mask(district)].sort_values("date")
        for label in labels.itertuples():
            horizon = int(label.horizon_months)
            same_month = known.loc[known.date.dt.month == label.target_date.month, "gwl_current"]
            seasonal = float(same_month.iloc[-1]) if len(same_month) else None
            prediction = float(predicted[horizon - 1])
            records.append({"fold": fold, "split": "development_evaluation",
                            "district_id": str(district_id), "origin_date": origin.date().isoformat(),
                            "target_date": label.target_date.date().isoformat(), "horizon_months": horizon,
                            "actual_gwl_m_bgl": float(label.actual_gwl), "predicted_gwl_m_bgl": prediction,
                            "residual_m": float(label.actual_gwl) - prediction,
                            "persistence_gwl_m_bgl": depth, "seasonal_gwl_m_bgl": seasonal})
    return records


def validate_candidates(frame, *, fold="all", n_jobs=1, trees=240, include_cases=False,
                        model_factory=None, evaluator=None) -> dict:
    """Fit only in memory and report paired development metrics; never publish."""
    parameters = model_parameters(n_jobs, trees)
    frame = development_frame(frame)
    pairs = climate.prepare_pairs(frame)
    factory = model_factory or _default_model
    evaluate = evaluator or climate.evaluate_assumed_weather
    report = {
        "version": "1.0-monthly-candidate-development", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "development_only", "feature_generation_id": frame.attrs["feature_generation_id"],
        "data_source": frame.attrs["data_source"], "development_rows": len(frame),
        "development_start": frame.date.min().date().isoformat(),
        "development_end": frame.date.max().date().isoformat(),
        "development_pairs": len(pairs), "development_pairs_sha256": _fingerprint(pairs, list(pairs.columns)),
        "parameters": parameters, "features": list(climate.FEATURES), "folds": [],
        "production_changes_made": False, "model_published": False,
        "validation_assessment": {"sufficient_for_operational_use": False,
            "status": "experimental_development_comparison",
            "limitations": ["2020 onward is excluded before labels and weather evaluation; this report does not re-evaluate that already-inspected period.",
                           "Weather uses historical same-month assumptions available at each observed origin.",
                           "Observed origins do not validate estimated current levels or zone fallback.",
                           "Development errors cannot establish current accuracy or independently calibrate prediction intervals.",
                           "Publication dates and source revisions are not available; historical data vintages are not reconstructed."]},
        "protocol": {"embargo_months": 6, "final_period_excluded_from": "2020-01-01",
                     "split_unit": "calendar_target_and_origin_dates_across_all_districts",
                     "training_weather": "realized historical conditional covariates",
                     "evaluation_weather": "origin_available_historical_climatology",
                     "minimum_training_pairs": MIN_TRAINING_PAIRS,
                     "minimum_evaluation_pairs": MIN_EVALUATION_PAIRS,
                     "cases_exported": bool(include_cases)},
    }
    for specification in select_folds(fold):
        training, evaluation = fold_pairs(pairs, specification)
        training_counts, evaluation_counts = _counts(training), _counts(evaluation)
        missing_train = [int(h) for h, count in training_counts.items() if count == 0]
        missing_eval = [int(h) for h, count in evaluation_counts.items() if count == 0]
        result = {**specification, "training_pairs": len(training), "evaluation_pairs": len(evaluation),
                  "training_districts": int(training.district_id.nunique()),
                  "evaluation_districts": int(evaluation.district_id.nunique()),
                  "training_counts_by_horizon": training_counts, "evaluation_counts_by_horizon": evaluation_counts,
                  "missing_training_horizons": missing_train, "missing_evaluation_horizons": missing_eval,
                  "training_inputs_sha256": _fingerprint(training, climate.FEATURES + ["target_delta"]),
                  "evaluation_cases_sha256": _fingerprint(evaluation, ["district_id", "origin_date", "target_date", "horizon_months"])}
        reasons = []
        if missing_train:
            reasons.append("missing_training_horizons")
        if len(training) < MIN_TRAINING_PAIRS:
            reasons.append("insufficient_training_pairs")
        if len(evaluation) < MIN_EVALUATION_PAIRS:
            reasons.append("insufficient_evaluation_pairs")
        if reasons:
            result.update(status="skipped", reasons=reasons)
        else:
            model = factory(**parameters)
            model.fit(training[climate.FEATURES], training.target_delta)
            # Bound even evaluation metadata to this fold; future rows never
            # enter weather builders, including unrelated development periods.
            weather_frame = frame.loc[frame.date <= pd.Timestamp(specification["evaluation_target_end"])].copy()
            summary = evaluate(model, weather_frame, evaluation)
            usable = summary.get("status") == "evaluated_assumed_weather" and summary.get("n", 0) > 0
            result.update(status="evaluated_development" if usable else "unavailable", evaluation=summary,
                          horizon_coverage="partial" if missing_eval else "all_six")
            if include_cases:
                records = assumed_weather_cases(model, weather_frame, evaluation, specification["fold"])
                if len(records) != summary.get("n", 0):
                    raise ValueError("Candidate per-case export differs from assumed-weather evaluation coverage.")
                result["cases"] = records
            del model
        report["folds"].append(result)
    return finite_json(report)


def _load_verified_features():
    """Require local artifacts so the shared loader cannot fall back to DB."""
    processed = source_model.ROOT / source_model.CONFIG["paths"]["data_processed"]
    if not (processed / "features_matrix.csv").is_file() or not (processed / "feature_manifest.json").is_file():
        raise ValueError("Verified local features_matrix.csv and feature_manifest.json are required; database fallback is disabled.")
    return load_feature_matrix()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Explicitly fit in-memory candidate models and write a dedicated report.")
    parser.add_argument("--fold", choices=["all", "1", "2", "3"], default="all")
    parser.add_argument("--n-jobs", type=int, default=1)
    parser.add_argument("--trees", type=int, default=240)
    parser.add_argument("--include-cases", action="store_true", help="Export development residuals; these are not independent calibration data.")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "reports/candidates/monthly_validation/development_evaluation.json")
    args = parser.parse_args(argv)
    try:
        output = candidate_output(args.output)
        parameters = model_parameters(args.n_jobs, args.trees)
        specifications = select_folds(args.fold)
    except ValueError as error:
        parser.error(str(error))
    if not args.run:
        print(json.dumps({"mode": "offline_plan", "feature_loading_performed": False,
                          "model_fitting_performed": False, "production_changes_made": False,
                          "output": str(output), "parameters": parameters, "folds": specifications,
                          "final_period_excluded_from": "2020-01-01",
                          "warning": "Development results are experimental; no independent current-period validation or uncertainty calibration is performed."}, indent=2))
        return 0
    report = validate_candidates(_load_verified_features(), fold=args.fold, n_jobs=args.n_jobs,
                                 trees=args.trees, include_cases=args.include_cases)
    # Recheck after model work in case the path was changed into a symlink.
    _write_json(candidate_output(output), report)
    print(json.dumps({"output": str(output), "mode": report["mode"],
                      "folds": [{"fold": item["fold"], "status": item["status"],
                                 "training_pairs": item["training_pairs"],
                                 "evaluation_pairs": item["evaluation_pairs"]} for item in report["folds"]],
                      "model_published": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
