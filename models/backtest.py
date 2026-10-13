"""Causal model validation and ensemble calibration; never publishes checkpoints.

The calibration uses actual held-forward XGBoost predictions and the same pure
component calculation as serving. Candidate weights are reported, not silently
installed in config. Synthetic output remains a separate smoke-test report.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from models import xgboost_model as forecast
from models.ensemble import components_from_history, depth_to_score

CONFIG = forecast.CONFIG
CONFIG_PATH = ROOT / "config.yaml"
HORIZON_MONTHS = forecast.FORECAST_HORIZON
get_connection = forecast.get_connection
nash_sutcliffe_efficiency = forecast.nash_sutcliffe_efficiency


def load_feature_matrix(allow_synthetic=False):
    # Explicit synthetic mode is deterministic even when a real DB is available.
    if allow_synthetic:
        df = _generate_synthetic_features()
        df.attrs.update(data_source="synthetic", feature_generation_id="synthetic-smoke-only")
        return df
    return forecast.load_feature_matrix()


def _generate_synthetic_features():
    rng = np.random.default_rng(42)
    rows = []
    for district in range(4):
        dates = pd.date_range("2002-01-01", "2024-12-01", freq="MS")
        gwl = 8 + district + np.arange(len(dates)) * .01 + 2 * np.sin(np.arange(len(dates)) * 2 * np.pi / 12) + rng.normal(0, .2, len(dates))
        for index, date in enumerate(dates):
            rain = float(max(0, 80 + 60 * np.sin((date.month - 7) * 2 * np.pi / 12)))
            et = 90.0
            rows.append({"district_id": f"SMOKE-{district}", "date": date, "gwl_current": gwl[index],
                "gwl_lag_3mo": gwl[index - 3] if index >= 3 else np.nan,
                "gwl_lag_6mo": gwl[index - 6] if index >= 6 else np.nan,
                "rainfall_current": rain, "rainfall_3mo_avg": rain,
                "monsoon_deficit_pct": 0.0, "temperature": 25.0, "evapotranspiration": et,
                "water_balance_proxy": rain - et,
                "crop_season_flag": "Kharif" if 6 <= date.month <= 10 else "Rabi" if date.month >= 11 or date.month <= 3 else "Zaid",
                "is_observed": True, "is_imputed": False, "feature_generation": "synthetic-smoke-only"})
    return pd.DataFrame(rows)


def causal_calibration_predictions(df, years=None, params=None):
    """Fit on labels available before each calibration year, with a six-month embargo."""
    prepared = forecast.create_target(forecast.encode_crop_season(df))
    features = forecast.get_feature_columns(prepared)
    prepared["predicted_gwl_6mo"] = np.nan
    prepared["prediction_train_target_cutoff"] = pd.NaT
    years = years or CONFIG.get("testing", {}).get("backtest_years", [2015, 2016, 2018, 2019])
    # Final test labels are never used for fitting or choosing ensemble weights.
    development_end = pd.Timestamp(CONFIG["date_range"]["test_start"])
    for year in years:
        cutoff = pd.Timestamp(year - 1, 6, 30)
        train, test = forecast.temporal_split(prepared, cutoff, f"{year}-01-01", f"{year}-12-31")
        train = train[train["target_date"] < development_end]
        test = test[test["target_date"] < development_end]
        if train.empty or test.empty:
            continue
        model = forecast.new_model(params)
        model.fit(train[features], train["target_gwl_6mo"])
        prepared.loc[test.index, "predicted_gwl_6mo"] = model.predict(test[features])
        prepared.loc[test.index, "prediction_train_target_cutoff"] = cutoff
    # Preserve all observed history, including origins lacking a future label.
    # Components must receive the same evidence available to live scoring.
    extra = ['target_date','target_gwl_6mo','target_is_observed','target_is_imputed','seasonal_naive_6mo',
             'predicted_gwl_6mo','prediction_train_target_cutoff']
    result = df.merge(prepared[['district_id','date',*extra]],on=['district_id','date'],how='left',validate='one_to_one')
    result['target_is_observed'] = result['target_is_observed'].fillna(False).astype(bool)
    result.attrs.update(df.attrs)
    return result


def _compute_component_scores(df, years=None, as_of=None):
    """Only score rows carrying a genuine causal prediction and observed future label."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    if as_of is not None:
        df = df[df["date"] <= pd.Timestamp(as_of)].copy()
    if "target_gwl_6mo" not in df:
        prepared = forecast.create_target(df)
        extra = ['target_date','target_gwl_6mo','target_is_observed']
        df = df.merge(prepared[['district_id','date',*extra]],on=['district_id','date'],how='left',validate='one_to_one')
        df['target_is_observed'] = df['target_is_observed'].fillna(False).astype(bool)
    columns = ["district_id", "date", "target_date", "gwl_actual", "gwl_future",
               "lr_score", "xgb_score", "drought_score", "fuzzy_score", "target_score"]
    if "predicted_gwl_6mo" not in df or "prediction_train_target_cutoff" not in df:
        return pd.DataFrame(columns=columns)
    results = []
    for district, group in df.groupby("district_id"):
        group = group.sort_values("date")
        observed_origins = set(group.loc[forecast.observed_mask(group),'date'])
        history_rows = group.set_index("date")["gwl_current"]
        for _, row in group.iterrows():
            if row['date'] not in observed_origins:
                continue
            if years is not None and row["date"].year not in years:
                continue
            if not row.get("target_is_observed", False) or not np.isfinite(row["predicted_gwl_6mo"]):
                continue
            cutoff = pd.Timestamp(row["prediction_train_target_cutoff"])
            first_allowed = (cutoff.to_period("M") + forecast.EMBARGO_MONTHS + 1).to_timestamp()
            if pd.isna(cutoff) or row["date"] < first_allowed:
                raise ValueError("Calibration prediction uses labels unavailable at its forecast origin.")
            if as_of is not None and row["target_date"] > pd.Timestamp(as_of):
                continue
            history = history_rows.loc[:row["date"]].dropna()
            if len(history) < 12:
                continue
            anomaly = row.get("monsoon_deficit_pct", np.nan)
            if not np.isfinite(anomaly):
                continue
            history_frame = group.loc[group["date"] <= row["date"]]
            components = components_from_history(history_frame, predicted_depth=float(row["predicted_gwl_6mo"]))
            values = [components[k] for k in ["lr_trend", "xgb_risk", "drought_frequency", "fuzzy_logic"]]
            if any(value is None for value in values) or not np.isfinite(values).all():
                continue
            results.append({"district_id": district, "date": row["date"], "target_date": row["target_date"],
                "gwl_actual": row["gwl_current"], "gwl_future": row["target_gwl_6mo"],
                "lr_score": values[0], "xgb_score": values[1], "drought_score": values[2], "fuzzy_score": values[3],
                "target_score": depth_to_score(row["target_gwl_6mo"])})
    return pd.DataFrame(results, columns=columns)


def _normalized_initial():
    weights = CONFIG["model_hyperparameters"]["ensemble"]["initial_weights"]
    total = sum(weights.values())
    return {key: float(value / total) for key, value in weights.items()}


def fit_ensemble_weights(df, as_of=None):
    samples = _compute_component_scores(df, CONFIG.get("testing", {}).get("backtest_years"), as_of)
    if samples.empty:
        print("No causal model calibration samples; retaining explicitly uncalibrated initial weights.")
        return _normalized_initial()
    names = ["linear_regression_trend", "xgboost_risk", "drought_frequency", "fuzzy_logic"]
    X = samples[["lr_score", "xgb_score", "drought_score", "fuzzy_score"]].to_numpy(dtype=float)
    y = samples["target_score"].to_numpy(dtype=float)
    initial = np.array([_normalized_initial()[name] for name in names])
    result = minimize(lambda weights: np.mean(np.abs(y - X @ weights)), initial, method="SLSQP",
                      bounds=[(0., 1.)] * 4, constraints={"type": "eq", "fun": lambda weights: weights.sum() - 1},
                      options={"maxiter": 500, "ftol": 1e-9})
    if not result.success or not np.isfinite(result.x).all():
        raise RuntimeError(f"Weight calibration failed: {result.message}")
    fitted = np.maximum(result.x, 0)
    fitted /= fitted.sum()
    return dict(zip(names, map(float, fitted)))


def run_walkforward_validation(df):
    prepared = forecast.create_target(forecast.encode_crop_season(df))
    # Development windows only: the configured final-test labels stay untouched.
    prepared = prepared[prepared["target_date"] < pd.Timestamp(CONFIG["date_range"]["test_start"])].copy()
    return forecast.run_purged_walkforward_validation(prepared, forecast.get_feature_columns(prepared))


def should_write_config(data_source):
    """No backtest ever mutates production config; promotion is a separate validated action."""
    return False


def save_to_config(fitted_weights, walkforward_results, data_source):
    """Compatibility name: writes a report, never config/checkpoints."""
    path = ROOT / "reports" / ("synthetic_backtest_smoke.json" if data_source == "synthetic" else "backtest_results.json")
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "data_source": data_source,
              "candidate_ensemble_weights": fitted_weights, "weights_promoted": False,
              "walkforward_validation": walkforward_results}
    forecast._write_json(path, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", action="store_true")
    args = parser.parse_args(argv)
    df = load_feature_matrix(args.synthetic)
    params = {"n_estimators": 5, "max_depth": 2} if args.synthetic else None
    calibrated = causal_calibration_predictions(df, params=params)
    weights = fit_ensemble_weights(calibrated)
    if args.synthetic:
        # Tiny explicit smoke fold, not the real performance report.
        results = forecast.run_purged_walkforward_validation(
            forecast.create_target(forecast.encode_crop_season(df)), forecast.CANONICAL_FEATURE_COLS,
            [{"fold_name": "synthetic-smoke", "train_target_cutoff": "2013-06-30",
              "test_origin_start": "2014-01-01", "test_origin_end": "2014-12-31"}])
    else:
        results = run_walkforward_validation(df)
    return save_to_config(weights, results, df.attrs.get("data_source", "unknown"))


if __name__ == "__main__":
    main()
