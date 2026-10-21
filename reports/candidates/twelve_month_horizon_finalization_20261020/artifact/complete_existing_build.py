"""Complete packaging of the already fitted research model, without fitting.

The initial builder's exact-old-model parity assumption failed. Retain every
original output, verify the new immutable artifact independently, and disclose
that failure rather than refitting to chase the historical predictions.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from models import research_horizon as horizon

ARTIFACT = Path(__file__).resolve().parent
RUN = ARTIFACT.parent
OLD = ROOT / "reports/candidates/twelve_month_horizon_20261020"
CONFIG = ROOT / "research/twelve_month_app.json"


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)


def measure(actual, predicted):
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    error = predicted - actual
    sst = float(np.square(actual - actual.mean()).sum())
    return {"n": len(actual), "MAE_m": float(np.abs(error).mean()),
        "RMSE_m": float(np.sqrt(np.square(error).mean())), "bias_m": float(error.mean()),
        "R2": float(1 - np.square(error).sum() / sst) if sst > 1e-12 else None}


def main():
    if CONFIG.exists() or (ARTIFACT / "manifest.json").exists() or (RUN / "artifact_build.json").exists():
        raise FileExistsError("Completion is create-only")
    plan = json.loads((RUN / "build_plan.json").read_text())
    contract = plan["contract"]
    if sha(contract) != plan["contract_sha256"]:
        raise ValueError("Frozen contract changed")
    for path, expected in plan["input_sha256"].items():
        if horizon.sha256_file(ROOT / path) != expected:
            raise ValueError("Pre-fit source changed: " + path)
    if horizon.sha256_file(RUN / "build_application_research.py") != plan["builder_sha256"]:
        raise ValueError("Preserve the original builder that produced the model")
    features = contract["features"]
    card_path = ARTIFACT / "xgb_fixed_2021_card.json"
    model, card = horizon.load_research_model(card_path, 12, contract["protocol_sha256"], features)
    if (card["configuration_sha256"] != plan["contract_sha256"]
            or card["parameters"] != plan["parameters"] or card["train_n"] != 164):
        raise ValueError("New artifact contract mismatch")
    full = pd.read_csv(OLD / "cohorts/strict_features.csv", parse_dates=["date"])
    subset = full.loc[full.district_id.eq("TS-Adilabad")].copy()
    old_train, _, _ = horizon.split_fold(horizon.build_cases(full, 12), 2024, 12)
    new_train, _, _ = horizon.split_fold(horizon.build_cases(subset, 12), 2024, 12)
    old_card = json.loads((OLD / "evaluation/models/exact_name_coordinate/xgb_expanding_2024_card.json").read_text())
    ids = hashlib.sha256("\n".join(sorted(new_train.case_id)).encode()).hexdigest()
    identity = {"training_case_ids_and_order_equal": old_train.case_id.tolist() == new_train.case_id.tolist(),
        "features_equal_including_missing_values": bool(np.allclose(old_train[features], new_train[features], equal_nan=True, rtol=0, atol=0)),
        "training_labels_equal": bool(np.array_equal(old_train.target_value, new_train.target_value)),
        "old_training_case_ids_sha256_matches": ids == old_card["training_case_ids_sha256"],
        "new_card_training_case_ids_sha256_matches": sha(new_train.case_id.tolist()) == card["training_case_ids_sha256"],
        "locked_parameters_equal": card["parameters"] == old_card["settings"]["parameters"]}
    if not all(identity.values()):
        raise ValueError("Training identity verification failed")
    snapshot = pd.read_csv(ARTIFACT / "features.csv", parse_dates=["date"])
    cases = horizon.build_cases(snapshot, 12)
    eligible = cases.loc[cases.date.between("2023-01-01", "2024-12-01")
        & cases.reference_eligible & np.isfinite(cases[features]).all(axis=1)].copy()
    saved = pd.read_csv(ARTIFACT / "historical_checks.csv")
    if eligible.case_id.tolist() != saved.case_id.tolist() or len(eligible) != 24:
        raise ValueError("Fixed historical check membership differs")
    prediction = model.predict(eligible[features]).astype(float)
    if not np.allclose(prediction, saved.fixed_xgb_2021, rtol=0, atol=1e-8):
        raise ValueError("New artifact does not reproduce its own archived predictions")
    if not np.array_equal(eligible.gwl_current, eligible.seasonal_naive):
        raise ValueError("Annual baseline equivalence failed")
    old = pd.read_csv(OLD / "evaluation/exact_name_coordinate_predictions.csv")
    parity = saved.loc[saved.target_date.str.startswith("2024")].merge(
        old[["case_id", "xgb_expanding"]], on="case_id", validate="one_to_one")
    delta = float(np.max(np.abs(parity.fixed_xgb_2021 - parity.xgb_expanding)))
    provenance = json.loads((ARTIFACT / "input_provenance.json").read_text())
    if len(snapshot) != 233 or len(provenance["rows"]) != 233:
        raise ValueError("Snapshot/provenance row count mismatch")
    manifest = {"schema_version": 1, "contract_sha256": plan["contract_sha256"],
        "card_path": card_path.name, "card_sha256": horizon.sha256_file(card_path),
        "snapshot_path": "features.csv", "snapshot_sha256": horizon.sha256_file(ARTIFACT / "features.csv"),
        "input_provenance_path": "input_provenance.json", "input_provenance_sha256": horizon.sha256_file(ARTIFACT / "input_provenance.json"),
        "provenance_path": "provenance.json", "provenance_sha256": horizon.sha256_file(ARTIFACT / "provenance.json")}
    write(ARTIFACT / "manifest.json", manifest)
    CONFIG.parent.mkdir(exist_ok=True)
    write(CONFIG, {"contract": contract, "contract_sha256": plan["contract_sha256"],
        "manifest_path": str((ARTIFACT / "manifest.json").relative_to(ROOT)).replace("\\", "/"),
        "manifest_sha256": horizon.sha256_file(ARTIFACT / "manifest.json")})
    result = {"schema_version": 1, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "fit_count": 1, "completion_fit_count": 0, "family": "xgboost", "train_n": 164,
        "complete_train_n": 158, "training_missing_by_feature": new_train[features].isna().sum().to_dict(),
        "training_target_cutoff": "2021-12-31", "max_train_target": "2021-12-01",
        "max_train_origin": "2020-12-01", "first_allowed_origin": "2023-01",
        "model_created_at_utc": card["created_at_utc"], "fit_started_at_utc": None,
        "fit_timing_caveat": "The first builder stopped after fitting/reloading; only the card's recorded completion time survived, so no start time is invented",
        "snapshot_rows": 233, "input_provenance_rows": 233,
        "training_identity_checks": identity,
        "plan_sha256": horizon.sha256_file(RUN / "build_plan.json"),
        "configuration_sha256": plan["contract_sha256"], "descriptor_sha256": horizon.sha256_file(CONFIG),
        "model_sha256": card["model_sha256"], "card_sha256": manifest["card_sha256"],
        "manifest_sha256": horizon.sha256_file(ARTIFACT / "manifest.json"),
        "reload_predictions_equal": True,
        "old_2024_checkpoint_parity": {"n": len(parity), "passed": delta <= 1e-8,
            "max_abs_difference_m": delta,
            "initial_builder_exit_code": 1, "initial_evidence_retained": True,
            "confirmed_runtime_difference": "Old fitting runner wrapped fits in threadpool_limits(limits=1); initial new builder omitted that outer context and kept explicit n_jobs=4",
            "cause": "Exact cause of numerical/model differences remains unproved; do not claim old-fit reproduction",
            "action": "Preserve this new one-fit artifact and its own results; no refit or tuning to chase old predictions"},
        "own_historical_24_case_check": {"fixed_xgb": measure(eligible.target_value, prediction),
            "annual_baseline": measure(eligible.target_value, eligible.gwl_current)},
        "interpretation": "Own fixed-cutoff check, not the original expanding comparison; annual baseline is substantially better; no tuning or model selection",
        "prospective_forecasts_issued": 0, "active_pointer_changes": 0, "database_accessed": False,
        "source_downloads": 0, "hgb_fitted": False, "shadow_artifact_approved": False,
        "completion_script_sha256": horizon.sha256_file(Path(__file__))}
    write(RUN / "artifact_build.json", result)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
