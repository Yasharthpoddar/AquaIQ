"""Observed-target, six-calendar-month GWL forecasts and verified model bundles.

Rebuild causal physical-unit features first, then run:
python -m models.xgboost_model --train-cutoff 2019-12-31
python -m models.xgboost_model --eval
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import uuid

import numpy as np
import pandas as pd
import yaml
from dotenv import load_dotenv
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
XGB_PARAMS = CONFIG["model_hyperparameters"]["xgboost"]
CHECKPOINT_PATH = ROOT / CONFIG["paths"]["xgboost_checkpoint"]
MODEL_CARD_PATH = CHECKPOINT_PATH.parent / "aquaiq_xgb_model_card.json"
FORECAST_HORIZON = 6
EMBARGO_MONTHS = 6
DEFAULT_TRAIN_CUTOFF = CONFIG["date_range"]["train_end"]
FEATURE_UNITS = {"gwl": "m_bgl", "rainfall": "mm/month", "evapotranspiration": "mm/month", "temperature": "degC"}
CANONICAL_FEATURE_COLS = [
    "gwl_current", "gwl_lag_3mo", "gwl_lag_6mo", "rainfall_current",
    "rainfall_3mo_avg", "monsoon_deficit_pct", "temperature", "evapotranspiration",
    "water_balance_proxy", "season_Kharif", "season_Rabi", "season_Zaid",
]


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def get_connection():
    from db.connection import get_connection as connect
    return connect()


def _parse_bool(series):
    values = series.astype("string").str.strip().str.lower()
    return values.map({"true": True, "1": True, "false": False, "0": False}).astype("boolean")


def observed_mask(df):
    """Unknown flags never imply an observed target, including truthy 'False'."""
    if "is_observed" in df:
        return _parse_bool(df["is_observed"]).fillna(False).astype(bool)
    if "is_imputed" in df:
        return _parse_bool(df["is_imputed"]).eq(False).fillna(False).astype(bool)
    return pd.Series(False, index=df.index, dtype=bool)


def encode_crop_season(df):
    df = df.copy()
    if "crop_season_flag" in df:
        for season in ["Kharif", "Rabi", "Zaid"]:
            df[f"season_{season}"] = (df["crop_season_flag"] == season).astype(float)
        df = df.drop(columns="crop_season_flag")
    return df


def get_feature_columns(df):
    missing = set(CANONICAL_FEATURE_COLS) - set(df.columns)
    if missing:
        raise ValueError(f"Incomplete model feature schema: {sorted(missing)}")
    return list(CANONICAL_FEATURE_COLS)


def validate_feature_generation(df, manifest):
    if manifest.get("sample_only", False):
        raise ValueError("Sample-only feature artifacts cannot be used for production training or loading.")
    if manifest.get("units") != FEATURE_UNITS or manifest.get("causal_preprocessing") is not True:
        raise ValueError("Features require a causal physical-unit manifest; rebuild preprocessing.")
    generation = manifest.get("generation_id")
    if not isinstance(generation, str) or not generation:
        raise ValueError("Missing feature generation identity.")
    required = {"district_id", "date", "feature_generation", "is_observed", "is_imputed"}
    if required - set(df.columns):
        raise ValueError(f"Feature provenance/schema missing: {sorted(required - set(df.columns))}")
    if df.empty or df["feature_generation"].isna().any() or set(df["feature_generation"].astype(str)) != {generation}:
        raise ValueError("Unknown or mixed feature generations; rebuild atomically.")
    for column in ["is_observed", "is_imputed"]:
        if _parse_bool(df[column]).isna().any():
            raise ValueError(f"Unknown observation provenance in {column}.")
    if (observed_mask(df) & _parse_bool(df["is_imputed"]).fillna(False)).any():
        raise ValueError("Feature row cannot be both observed and imputed.")
    if df.duplicated(["district_id", "date"]).any():
        raise ValueError("Duplicate district-month feature keys.")
    date = pd.to_datetime(df["date"], errors="raise")
    if date.isna().any() or (date.dt.day != 1).any():
        raise ValueError("Feature dates must be valid calendar month starts.")
    lower = max(pd.Timestamp(CONFIG["date_range"]["start"]), pd.Timestamp(manifest["date_start"]))
    upper = min(pd.Timestamp(CONFIG["date_range"]["end"]), pd.Timestamp(manifest["date_end"]))
    if lower > upper or ((date < lower) | (date > upper)).any():
        raise ValueError("Feature rows outside the configured generation range.")
    encoded = encode_crop_season(df)
    get_feature_columns(encoded)
    for column in CANONICAL_FEATURE_COLS:
        numeric = pd.to_numeric(encoded[column], errors="coerce")
        if np.isinf(numeric.to_numpy(dtype=float)).any():
            raise ValueError(f"Infinite values in {column}.")
    for column in ["gwl_current", "gwl_lag_3mo", "gwl_lag_6mo", "rainfall_current", "evapotranspiration"]:
        if (pd.to_numeric(encoded[column], errors="coerce").dropna() < 0).any():
            raise ValueError(f"Negative physical values in {column}.")
    return generation


def dataframe_hash(df):
    canonical = df.sort_values(["district_id", "date"])
    columns = sorted(c for c in canonical.columns if c != "id")
    digest = hashlib.sha256("|".join(columns).encode())
    digest.update(pd.util.hash_pandas_object(canonical[columns], index=False).values.tobytes())
    return digest.hexdigest()


def load_feature_matrix():
    """Load one verified generation, without unrelated CSV provenance merges."""
    processed = ROOT / CONFIG["paths"]["data_processed"]
    manifest_path = processed / "feature_manifest.json"
    if not manifest_path.exists():
        raise ValueError("Feature manifest missing. Rebuild physical-unit causal features before training.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    csv_path = processed / "features_matrix.csv"
    if csv_path.exists():
        if sha256_file(csv_path) != manifest.get("feature_csv_sha256"):
            raise ValueError("Feature CSV checksum differs from generation manifest.")
        df = pd.read_csv(csv_path, parse_dates=["date"])
        source = "verified features_matrix.csv"
    else:
        from db.connection import read_frame
        conn = get_connection()
        try:
            df = read_frame("SELECT * FROM features ORDER BY district_id, date", conn)
        finally:
            conn.close()
        source = "features table (PostgreSQL)"
    df["date"] = pd.to_datetime(df["date"])
    generation = validate_feature_generation(df, manifest)
    df["is_observed"] = observed_mask(df)
    df["is_imputed"] = _parse_bool(df["is_imputed"]).astype(bool)
    df.attrs.update(data_source=source, feature_generation_id=generation,
                    feature_manifest=manifest, data_sha256=dataframe_hash(df))
    print(f"Loaded {len(df):,} rows; generation {generation}")
    return df


def create_target(df):
    """Join exactly t+6 calendar months; never use the sixth following row."""
    df = df.sort_values(["district_id", "date"]).copy()
    attrs = df.attrs.copy()
    df["date"] = pd.to_datetime(df["date"])
    if df.duplicated(["district_id", "date"]).any():
        raise ValueError("Duplicate district-month rows cannot form unique labels.")
    target = df[["district_id", "date", "gwl_current"]].copy()
    target["target_is_observed"] = observed_mask(df).to_numpy()
    target = target.rename(columns={"date": "target_date", "gwl_current": "target_gwl_6mo"})
    df["target_date"] = df["date"] + pd.DateOffset(months=FORECAST_HORIZON)
    df = df.merge(target, on=["district_id", "target_date"], how="left", validate="one_to_one")
    df["target_is_observed"] = df["target_is_observed"].fillna(False).astype(bool)
    df["target_is_imputed"] = ~df["target_is_observed"]
    seasonal = target.rename(columns={"target_date": "seasonal_date", "target_gwl_6mo": "seasonal_naive_6mo",
                                      "target_is_observed": "seasonal_is_observed"})
    df["seasonal_date"] = df["date"] - pd.DateOffset(months=FORECAST_HORIZON)
    df = df.merge(seasonal, on=["district_id", "seasonal_date"], how="left", validate="one_to_one")
    df.loc[~df["seasonal_is_observed"].fillna(False).astype(bool), "seasonal_naive_6mo"] = np.nan
    df = df.drop(columns=["seasonal_date", "seasonal_is_observed"])
    valid = np.isfinite(pd.to_numeric(df["gwl_current"], errors="coerce")) & np.isfinite(pd.to_numeric(df["target_gwl_6mo"], errors="coerce"))
    df = df.loc[valid].copy()
    df.attrs.update(attrs)
    return df


def temporal_split(df, train_target_cutoff, test_origin_start, test_origin_end, embargo_months=EMBARGO_MONTHS):
    cutoff, start = pd.Timestamp(train_target_cutoff), pd.Timestamp(test_origin_start)
    first_allowed = (cutoff.to_period("M") + embargo_months + 1).to_timestamp()
    if start < first_allowed:
        raise ValueError(f"Test origins must start on/after {first_allowed.date()} for label-availability embargo.")
    observed = df["target_is_observed"].fillna(False).astype(bool)
    train = df.loc[observed & (df["target_date"] <= cutoff)].copy()
    test = df.loc[observed & (df["date"] >= start) & (df["date"] <= pd.Timestamp(test_origin_end))].copy()
    if not train.empty and not test.empty and train["target_date"].max() >= test["date"].min():
        raise ValueError("Training labels overlap test forecast origins.")
    return train, test


def heldout_origin_start(train_cutoff):
    embargo_end = (pd.Timestamp(train_cutoff).to_period("M") + EMBARGO_MONTHS + 1).to_timestamp()
    # The configured final test dates refer to labels, not forecast origins.
    final_test_origin = pd.Timestamp(CONFIG["date_range"]["test_start"]) - pd.DateOffset(months=FORECAST_HORIZON)
    return max(embargo_end, final_test_origin)


def new_model(params=None):
    import xgboost as xgb
    return xgb.XGBRegressor(**{**XGB_PARAMS, **(params or {}), "objective": "reg:squarederror", "verbosity": 0,
                               "n_jobs": min(4, os.cpu_count() or 1)})


def _resolved_target_variation(y_true):
    """Distinguish target variation from a few float64 rounding units.

    Even repeated decimal values can have nonzero variance after subtracting a
    rounded mean. Range avoids that artifact; the small scale-aware tolerance
    also covers adjacent representable floats. This is a numerical guard, not
    an estimate of instrument precision or a statistical variance threshold.
    """
    if len(y_true) < 2:
        return False
    scale = max(1., float(np.max(np.abs(y_true))))
    tolerance = 8 * np.finfo(float).eps * scale
    return bool(np.ptp(y_true) > tolerance)


def nash_sutcliffe_efficiency(y_true, y_pred):
    y_true, y_pred = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    if not _resolved_target_variation(y_true):
        return None
    denominator = np.sum((y_true - np.mean(y_true)) ** 2)
    return None if denominator == 0 else float(1 - np.sum((y_true - y_pred) ** 2) / denominator)


def metrics(y_true, y_pred):
    y_true, y_pred = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    if not len(y_true) or not (np.isfinite(y_true).all() and np.isfinite(y_pred).all()):
        raise ValueError("Metrics require finite predictions and observed targets.")
    return {"n": len(y_true), "rmse_m": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "mae_m": float(mean_absolute_error(y_true, y_pred)),
            "r2": float(r2_score(y_true, y_pred)) if _resolved_target_variation(y_true) else None,
            "nse": nash_sutcliffe_efficiency(y_true, y_pred)}


def evaluate_model(model, test, feature_cols):
    if test.empty:
        return {"n_test_observed": 0, "status": "unavailable", "reason": "No observed held-out targets at supported origins."}
    y = test["target_gwl_6mo"].to_numpy(dtype=float)
    prediction = np.asarray(model.predict(test[feature_cols]), dtype=float)
    paired = np.isfinite(pd.to_numeric(test["seasonal_naive_6mo"], errors="coerce"))
    return {"status": "evaluated", "n_test_observed": len(test),
        "origin_start": test["date"].min().date().isoformat(), "origin_end": test["date"].max().date().isoformat(),
        "target_start": test["target_date"].min().date().isoformat(), "target_end": test["target_date"].max().date().isoformat(),
        "xgboost": metrics(y, prediction), "persistence_baseline": metrics(y, test["gwl_current"]),
        "seasonal_comparison": {"n": int(paired.sum()),
            "xgboost": metrics(y[paired], prediction[paired]) if paired.any() else None,
            "persistence_baseline": metrics(y[paired], test.loc[paired, "gwl_current"]) if paired.any() else None,
            "seasonal_naive_baseline": metrics(y[paired], test.loc[paired, "seasonal_naive_6mo"]) if paired.any() else None}}


DEFAULT_FOLDS = [
    {"fold_name": "expanding-2014", "train_target_cutoff": "2013-06-30", "test_origin_start": "2014-01-01", "test_origin_end": "2016-12-31"},
    {"fold_name": "drought-2018", "train_target_cutoff": "2017-06-30", "test_origin_start": "2018-01-01", "test_origin_end": "2019-12-31"},
    {"fold_name": "recent-2020", "train_target_cutoff": "2019-06-30", "test_origin_start": "2020-01-01", "test_origin_end": "2021-06-30"},
]


def run_purged_walkforward_validation(df, feature_cols, folds=None):
    results = []
    for fold in folds or DEFAULT_FOLDS:
        train, test = temporal_split(df, fold["train_target_cutoff"], fold["test_origin_start"], fold["test_origin_end"])
        record = {"fold": fold["fold_name"], **{k: v for k, v in fold.items() if k != "fold_name"},
                  "embargo_months": EMBARGO_MONTHS, "n_train_observed": len(train)}
        if train.empty or test.empty:
            record.update(status="unavailable", reason="No observed train/test labels.", n_test_observed=len(test))
        else:
            model = new_model()
            model.fit(train[feature_cols], train["target_gwl_6mo"])
            record.update(evaluate_model(model, test, feature_cols))
            record["max_train_target_date"] = train["target_date"].max().date().isoformat()
            record["max_train_origin"] = train["date"].max().date().isoformat()
        results.append(record)
        print(f"{record['fold']}: {record['status']}; observed train={len(train):,}, test={len(test):,}")
    return results


def publish_model_bundle(model, card, checkpoint_path=CHECKPOINT_PATH):
    """Expose a fully written, matching model/card through one atomic pointer."""
    checkpoint_path = Path(checkpoint_path)
    bundle_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex[:12]}"
    directory = checkpoint_path.parent / "bundles" / bundle_id
    directory.mkdir(parents=True, exist_ok=False)
    model_path, card_path = directory / "model.json", directory / "model_card.json"
    model.save_model(str(model_path))
    card = {**card, "bundle_schema_version": 1, "model_sha256": sha256_file(model_path), "bundle_id": bundle_id}
    _write_json(card_path, card)
    manifest = {"bundle_schema_version": 1, "model_path": model_path.relative_to(checkpoint_path.parent).as_posix(),
                "card_path": card_path.relative_to(checkpoint_path.parent).as_posix(),
                "model_sha256": card["model_sha256"], "card_sha256": sha256_file(card_path)}
    _load_bundle_files(model_path, card_path, manifest, card["feature_generation_id"])
    _write_json(checkpoint_path, manifest)
    _write_json(checkpoint_path.parent / "aquaiq_xgb_model_card.json", card)
    return card


def _load_bundle_files(model_path, card_path, manifest, expected_generation=None):
    if sha256_file(model_path) != manifest.get("model_sha256") or sha256_file(card_path) != manifest.get("card_sha256"):
        raise ValueError("Checkpoint/card checksum mismatch; refusing to serve.")
    card = json.loads(Path(card_path).read_text(encoding="utf-8"))
    if card.get("model_sha256") != manifest["model_sha256"] or card.get("bundle_schema_version") != 1:
        raise ValueError("Invalid matching model card.")
    if card.get("features") != CANONICAL_FEATURE_COLS or card.get("feature_schema_sha256") != _json_hash(CANONICAL_FEATURE_COLS):
        raise ValueError("Checkpoint feature schema/order differs from serving contract.")
    if card.get("units") != FEATURE_UNITS or card.get("horizon_months") != FORECAST_HORIZON:
        raise ValueError("Checkpoint units/horizon differ from validated contract.")
    if not card.get("feature_generation_id") or (expected_generation and card["feature_generation_id"] != expected_generation):
        raise ValueError("Checkpoint trained on a different feature generation; retrain.")
    if card.get("data_source") in {"synthetic", "unknown", None} or not card.get("train_target_cutoff"):
        raise ValueError("Synthetic or unproven checkpoint is not a production bundle.")
    cutoff = pd.Timestamp(card["train_target_cutoff"])
    latest_label = pd.Timestamp(card.get("max_train_target_date"))
    latest_origin = pd.Timestamp(card.get("max_train_origin"))
    if (pd.isna(cutoff) or pd.isna(latest_label) or pd.isna(latest_origin)
            or latest_label > cutoff
            or latest_origin + pd.DateOffset(months=FORECAST_HORIZON) > latest_label):
        raise ValueError("Checkpoint training dates violate its cutoff or calendar horizon.")
    import xgboost as xgb
    model = xgb.XGBRegressor()
    model.load_model(str(model_path))
    if model.get_booster().feature_names != CANONICAL_FEATURE_COLS or model.n_features_in_ != len(CANONICAL_FEATURE_COLS):
        raise ValueError("Stored model features differ from model card.")
    return model, card


def load_model_bundle(checkpoint_path=CHECKPOINT_PATH, expected_generation=None):
    checkpoint_path = Path(checkpoint_path)
    manifest = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if manifest.get("bundle_schema_version") != 1:
        raise ValueError("Legacy/unverified checkpoint. Rebuild features and train verified bundle.")
    paths = []
    for key in ["model_path", "card_path"]:
        path = (checkpoint_path.parent / manifest[key]).resolve()
        if not path.is_relative_to(checkpoint_path.parent.resolve()):
            raise ValueError("Checkpoint manifest path escapes its directory.")
        paths.append(path)
    return _load_bundle_files(*paths, manifest, expected_generation)


def train_production_model(df, feature_cols, train_cutoff=DEFAULT_TRAIN_CUTOFF, wf_results=None, checkpoint_path=None):
    generation = df.attrs.get("feature_generation_id")
    if not generation or df.attrs.get("data_source") in {"synthetic", "unknown", None}:
        raise ValueError("Production training requires a verified real feature generation.")
    cutoff = pd.Timestamp(train_cutoff)
    start = heldout_origin_start(cutoff)
    train, test = temporal_split(df, cutoff, start, CONFIG["date_range"]["end"])
    if train.empty:
        raise ValueError("No observed training labels available at requested cutoff.")
    model = new_model()
    model.fit(train[feature_cols], train["target_gwl_6mo"])
    heldout = evaluate_model(model, test, feature_cols)
    if heldout["status"] != "evaluated":
        raise ValueError("No independent observed holdout for cutoff; choose an earlier cutoff.")
    beats_persistence = heldout['xgboost']['rmse_m'] < heldout['persistence_baseline']['rmse_m']
    assessment = {'status':'limited_evidence' if heldout['n_test_observed'] < 100 else 'evaluated',
        'observed_holdout_samples':heldout['n_test_observed'], 'beats_persistence_on_holdout':beats_persistence,
        'sufficient_for_operational_use':False,
        'limitations':['Historical data only; current operational forecasting requires fresh observations.',
            'Risk weights are project defaults until separately calibrated and independently evaluated.']}
    if not beats_persistence:
        assessment['limitations'].append('XGBoost does not outperform persistence on the final held-out sample.')
    if heldout['n_test_observed'] < 100:
        assessment['limitations'].append('Fewer than 100 held-out observed targets; nationwide accuracy is not established.')
    card = {"model_name": "AquaIQ XGBoost GWL Forecaster", "version": "3.0-calendar-observed",
        "created_at": datetime.now(timezone.utc).isoformat(), "task": "six-calendar-month GWL forecast",
        "horizon_months": FORECAST_HORIZON, "features": feature_cols, "validation_assessment":assessment,
        "feature_schema_sha256": _json_hash(feature_cols), "units": FEATURE_UNITS,
        "feature_generation_id": generation, "data_sha256": df.attrs.get("data_sha256", dataframe_hash(df)),
        "data_source": df.attrs["data_source"], "hyperparameters": XGB_PARAMS,
        "train_target_cutoff": cutoff.date().isoformat(), "max_train_target_date": train["target_date"].max().date().isoformat(),
        "max_train_origin": train["date"].max().date().isoformat(), "n_train_observed": len(train),
        "evaluation_protocol": {"embargo_months": EMBARGO_MONTHS, "target_policy": "explicitly observed only",
            "strategy": "training labels available before cutoff; test origins follow six-month embargo",
            "folds": wf_results or [], "production_heldout": heldout}}
    return model, publish_model_bundle(model, card, checkpoint_path or CHECKPOINT_PATH)


def evaluate_saved_checkpoint(df, checkpoint_path=CHECKPOINT_PATH):
    model, card = load_model_bundle(checkpoint_path, df.attrs.get("feature_generation_id"))
    cutoff = pd.Timestamp(card["train_target_cutoff"])
    start = heldout_origin_start(cutoff)
    _, test = temporal_split(df, cutoff, start, CONFIG["date_range"]["end"])
    return {"bundle_id": card["bundle_id"], "feature_generation_id": card["feature_generation_id"],
            "train_target_cutoff": card["train_target_cutoff"], "evaluation": evaluate_model(model, test, card["features"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval", action="store_true")
    parser.add_argument("--train-cutoff", default=DEFAULT_TRAIN_CUTOFF)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT_PATH)
    args = parser.parse_args(argv)
    df = create_target(encode_crop_season(load_feature_matrix()))
    columns = get_feature_columns(df)
    if args.eval:
        result = evaluate_saved_checkpoint(df, args.checkpoint)
        _write_json(ROOT / "reports" / "xgboost_saved_evaluation.json", result)
    else:
        # Development validation cannot touch production holdout target dates.
        development = df[df["target_date"] <= pd.Timestamp(args.train_cutoff)].copy()
        folds = run_purged_walkforward_validation(development, columns)
        _, card = train_production_model(df, columns, args.train_cutoff, folds, args.checkpoint)
        result = {"bundle_id": card["bundle_id"], "heldout": card["evaluation_protocol"]["production_heldout"]}
    print(json.dumps(result, indent=2, allow_nan=False))
    return result


if __name__ == "__main__":
    main()
