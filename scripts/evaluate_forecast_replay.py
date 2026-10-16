"""Plan or run local, candidate-only replay of AquaIQ's full monthly forecast.

No database calls, fitting, active model publication or serving interval changes
are made. --run must be explicit. Output files are new candidate reports only.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _uncertainty_module():
    # Loading by path also permits isolated staged test runs without installing
    # this candidate tool into the active checkout.
    location = ROOT/"models/uncertainty.py"
    spec = importlib.util.spec_from_file_location("aquaiq_uncertainty_replay", location)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def candidate_output(path):
    path = Path(path).resolve()
    allowed = (ROOT/"reports/candidates/forecast_replay").resolve()
    if path.suffix.lower() != ".json" or not path.is_relative_to(allowed):
        raise ValueError("Output must be a new .json inside reports/candidates/forecast_replay.")
    # Resolving both sides alone would allow a symlinked candidate directory to
    # point at active data/models; additionally pin output inside the real root.
    protected = [(ROOT/name).resolve() for name in ("data", "models", "scripts", "tests")]
    if (not allowed.is_relative_to(ROOT.resolve()) or any(path.is_relative_to(directory) for directory in protected)
            or path.exists()):
        raise ValueError("Candidate output must stay in this repository and cannot overwrite an existing file.")
    return path


def load_local_features(features_path, manifest_path):
    """Verify explicit CSV inputs without load_feature_matrix's DB fallback."""
    import pandas as pd
    from models.xgboost_model import (validate_feature_generation, observed_mask,
                                      dataframe_hash, _parse_bool)
    features_path, manifest_path = Path(features_path).resolve(), Path(manifest_path).resolve()
    if features_path == manifest_path or features_path.suffix.lower() != ".csv":
        raise ValueError("A distinct local CSV and feature manifest are required.")
    manifest = _json(manifest_path)
    if _sha(features_path) != manifest.get("feature_csv_sha256"):
        raise ValueError("Local feature CSV checksum differs from the generation manifest.")
    frame = pd.read_csv(features_path, parse_dates=["date"])
    generation = validate_feature_generation(frame, manifest)
    frame["is_observed"] = observed_mask(frame)
    frame["is_imputed"] = _parse_bool(frame.is_imputed).astype(bool)
    frame.attrs.update(feature_generation_id=generation, data_source="verified explicit local feature CSV",
                       data_sha256=dataframe_hash(frame))
    return frame


def load_zones(path, district_ids):
    if path is None:
        return {}
    import pandas as pd
    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    if {"district_id", "agro_climatic_zone"}-set(table):
        raise ValueError("Zone CSV requires district_id and agro_climatic_zone columns.")
    if table.district_id.duplicated().any() or table.district_id.str.strip().eq("").any():
        raise ValueError("Zone mapping has duplicate or empty canonical district identities.")
    if set(table.district_id)-set(district_ids):
        raise ValueError("Zone mapping includes unknown canonical districts.")
    return {row.district_id: row.agro_climatic_zone for row in table.itertuples()
            if row.agro_climatic_zone.strip()}


def _write_new(path, report):
    # Serialize before creating the destination. Exclusive creation prevents a
    # repeated command from silently replacing previously reviewed evidence.
    encoded = json.dumps(report, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as target:
        target.write(encoded+"\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Explicitly execute; default only prints an offline plan.")
    parser.add_argument("--protocol", type=Path, help="JSON with separate fit/development/calibration/evaluation ranges.")
    parser.add_argument("--features", type=Path, default=ROOT/"data/processed/features_matrix.csv")
    parser.add_argument("--manifest", type=Path, default=ROOT/"data/processed/feature_manifest.json")
    parser.add_argument("--checkpoint", type=Path, default=ROOT/"models/checkpoints/aquaiq_monthly_climate.json")
    parser.add_argument("--zones", type=Path, help="Optional canonical district_id,agro_climatic_zone CSV; required for zone replay.")
    parser.add_argument("--district", action="append", dest="districts", help="Limit forecast requests, retaining the entire panel for zone evidence.")
    parser.add_argument("--gaps", default="0,3,12,36", help="Uniform simulated measurement gaps, 0..120 months.")
    parser.add_argument("--splits", default="calibration,evaluation", help="Comma-separated reserved stages to replay.")
    parser.add_argument("--cases", type=Path, help="Calibrate/evaluate a prior replay report instead of running forecasts.")
    parser.add_argument("--model-metadata", type=Path, help="For --cases CSV: JSON with model hash, generation and training cutoff.")
    parser.add_argument("--alpha", type=float, default=.1)
    parser.add_argument("--min-cases", type=int, default=30)
    parser.add_argument("--min-origins", type=int, default=6)
    parser.add_argument("--min-districts", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT/"reports/candidates/forecast_replay/replay_candidate.json")
    args = parser.parse_args(argv)
    if not args.run:
        report = {"mode": "offline_plan", "execution_requested": False, "network_used": False,
                  "database_used": False, "production_changes_made": False,
                  "steps": ["Reserve separate fit, development, calibration and later evaluation calendar ranges.",
                            "Use a verified checkpoint trained no later than fit_end; never tune with calibration/evaluation data.",
                            "Pass --run --protocol ranges.json to replay the full monthly path from verified local CSV inputs.",
                            "Provide canonical zone CSV to replay fallback; otherwise insufficient districts are skipped.",
                            "Use --run --protocol ranges.json --cases replay.json to fit calibration-only intervals and test later coverage."],
                  "protocol_example": {"fit_start": "2002-01-01", "fit_end": "2010-12-31", "development_start": "2011-07-01",
                      "development_end": "2013-12-31", "calibration_start": "2014-01-01", "calibration_end": "2016-12-31",
                      "evaluation_start": "2017-01-01", "evaluation_end": "2019-12-31"},
                  "warning": "Example dates are illustrative and require an independently reserved matching model; no current coverage guarantee."}
        print(json.dumps(report, indent=2))
        return report
    if args.protocol is None:
        parser.error("--run requires an explicit temporal --protocol JSON.")
    u = _uncertainty_module()
    protocol = u.TemporalProtocol(**_json(args.protocol))
    destination = candidate_output(args.output)
    inputs = [args.protocol, args.cases, args.model_metadata] if args.cases else [args.protocol, args.features, args.manifest, args.checkpoint, args.zones]
    if destination in {Path(item).resolve() for item in inputs if item is not None}:
        parser.error("Candidate output aliases an input file.")
    if args.cases:
        if args.cases.suffix.lower() == ".csv":
            import pandas as pd
            if args.model_metadata is None:
                parser.error("CSV --cases requires explicit --model-metadata JSON.")
            model = _json(args.model_metadata)
            rows = pd.read_csv(args.cases, keep_default_na=False).to_dict("records")
        else:
            prior = _json(args.cases)
            if prior.get("version") != u.VERSION or prior.get("mode") != "candidate_full_path_replay" or prior.get("protocol") != asdict(protocol):
                raise ValueError("Input cases are not a matching full-path replay report.")
            model, rows = prior["model"], prior["cases"]
        if any(row.get("split") not in ("development", "calibration", "evaluation") for row in rows):
            raise ValueError("Case input contains an unknown or unlabelled temporal split.")
        calibration_cases = [row for row in rows if row.get("split") == "calibration"]
        evaluation_cases = [row for row in rows if row.get("split") == "evaluation"]
        intervals = u.fit_intervals(calibration_cases, protocol, model, alpha=args.alpha,
                                   min_cases=args.min_cases, min_origins=args.min_origins, min_districts=args.min_districts)
        report = {"version": u.VERSION, "mode": "candidate_interval_calibration_and_evaluation",
                  "source_cases_sha256": _sha(args.cases), "intervals": intervals,
                  "evaluation": u.evaluate_intervals(evaluation_cases, intervals, protocol, model),
                  "production_changes_made": False}
    else:
        # Import serving code only for an explicit run. No training entry point
        # or load_feature_matrix (which could fall back to PostgreSQL) is used.
        from unittest.mock import patch
        from models import climate_forecast as climate
        from models.ensemble import CONFIG
        frame = load_local_features(args.features, args.manifest)
        model, card = climate.load_bundle(args.checkpoint, expected_generation=frame.attrs["feature_generation_id"])
        metadata = {key: card[key] for key in ("model_sha256", "feature_generation_id", "train_target_cutoff")}
        protocol.validate_model(metadata)
        # Legacy cards do not record minimum training-label date. Requiring the
        # fit window to include the complete feature-history start is a safe
        # lower-bound check; the report still discloses unavailable data vintages.
        if u._date(protocol.fit_start, "fit_start") > frame.date.min():
            raise ValueError("Fit window must include the feature-history start; the saved card has no minimum-label date.")
        zones = load_zones(args.zones, frame.district_id.unique())
        provider = u.in_memory_evidence_provider(generation=metadata["feature_generation_id"], zones=zones,
            readiness_start=CONFIG["date_range"]["start"],
            minimum_observations=CONFIG["crisis_score"]["fallback_strategy"]["min_months_required"],
            minimum_coverage_pct=CONFIG["crisis_score"]["data_readiness_min_pct"],
            interval_months=CONFIG["crisis_score"].get("observation_interval_months", 3))
        try:
            gaps = tuple(int(item) for item in args.gaps.split(","))
        except ValueError as exc:
            raise ValueError("--gaps must be comma-separated integers.") from exc
        # The selected verified model is bound only for this serial, standalone
        # command, then restored. The actual serving forecast function (including
        # current-depth estimation and assumed weather) remains unmodified.
        with patch.object(climate, "load_bundle", return_value=(model, card)):
            report = u.replay_forecasts(frame, protocol, metadata, evidence_provider=provider,
                predictor=climate.forecast_from_evidence, splits=tuple(args.splits.split(",")),
                gaps=gaps, district_ids=args.districts)
        report["inputs"] = {"features_sha256": _sha(args.features), "manifest_sha256": _sha(args.manifest),
                            "checkpoint_sha256": _sha(args.checkpoint), "zones_sha256": _sha(args.zones) if args.zones else None}
        report["zone_policy"] = "canonical_zone_mapping_supplied" if zones else "no_zone_mapping_fallback_unavailable"
    report["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    _write_new(destination, report)
    summary = {"mode": report["mode"], "output": str(destination), "production_changes_made": False}
    if "summary" in report:
        summary["summary"] = report["summary"]
    else:
        summary["calibration_cases"] = report["intervals"]["calibration_cases"]
        summary["evaluation"] = {key: value for key, value in report["evaluation"].items() if key not in ("cases", "groups", "limitations")}
    print(json.dumps(summary, indent=2, allow_nan=False))
    return report


if __name__ == "__main__":
    main()
