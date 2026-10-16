"""Archive forecasts now, or evaluate them later using independent actual data.

Default execution only prints an offline plan. --run --district ID archives the
complete current forecast with a read-only DB session. --run --archive FILE
--labels CSV evaluates local evidence only. Active data/models are never changed.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def validation_module():
    spec = importlib.util.spec_from_file_location("aquaiq_prospective_validation", ROOT/"models/prospective_validation.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def file_sha(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def candidate_directory():
    directory = (ROOT/"reports/candidates/prospective_forecasts").resolve()
    protected = [(ROOT/name).resolve() for name in ("data", "models", "scripts", "tests")]
    if not directory.is_relative_to(ROOT.resolve()) or any(directory.is_relative_to(path) for path in protected):
        raise ValueError("Prospective archives must remain inside the repository's candidate reports.")
    return directory


def write_new(directory, filename, value):
    destination = (directory/filename).resolve()
    if destination.parent != directory or destination.suffix != ".json":
        raise ValueError("Invalid prospective candidate filename.")
    encoded = json.dumps(value, indent=2, allow_nan=False)
    directory.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded+"\n")
    return destination


def archive_current(districts, module, *, now=None):
    """Read canonical evidence; issue time is the real clock with no CLI override."""
    from db.connection import get_connection
    from models import climate_forecast as climate
    from models.ensemble import select_evidence, feature_generation, CONFIG
    if not districts or len(set(districts)) != len(districts):
        raise ValueError("Select explicit unique canonical district IDs.")
    generation = feature_generation()
    checkpoint = climate.CHECKPOINT_PATH
    _, card = climate.load_bundle(checkpoint, expected_generation=generation)
    pointer = read_json(checkpoint)
    processed = ROOT/CONFIG["paths"]["data_processed"]
    manifest_path, features_path = processed/"feature_manifest.json", processed/"features_matrix.csv"
    manifest = read_json(manifest_path)
    if (manifest.get("generation_id") != generation or file_sha(features_path) != manifest.get("feature_csv_sha256")
            or pointer.get("model_sha256") != card.get("model_sha256")):
        raise ValueError("Current model/data artifact identities do not match.")
    common = {"model_sha256": card["model_sha256"], "model_card_file_sha256": pointer["card_sha256"],
        "feature_generation_id": generation, "feature_csv_sha256": manifest["feature_csv_sha256"],
        "feature_manifest_sha256": file_sha(manifest_path), "config_sha256": file_sha(ROOT/"config.yaml"),
        "geography_sha256": file_sha(ROOT/CONFIG["paths"]["geojson_boundaries"])}
    directory, outputs = candidate_directory(), []
    connection = get_connection()
    try:
        connection.set_session(readonly=True, autocommit=False)
        for district in districts:
            issued = module._time(now or datetime.now(timezone.utc))
            today = issued.tz_convert(module.INDIA).date().isoformat()
            evidence = select_evidence(district, as_of=today, conn=connection)
            forecast = climate.forecast_from_evidence(evidence)
            # Re-read issue time after inference so the recorded timestamp never
            # predates the actual production of this forecast.
            issued = module._time(now or datetime.now(timezone.utc))
            record = module.create_record(forecast, card, {**common, "district_id": district}, issued_at=issued)
            name = "forecast-"+issued.strftime("%Y%m%dT%H%M%S%fZ")+"-"+hashlib.sha256(district.encode()).hexdigest()[:12]+".json"
            outputs.append(str(write_new(directory, name, record)))
    finally:
        connection.close()
    return {"mode": "current_forecasts_archived", "archives": outputs, "production_changes_made": False,
            "accuracy_evaluated": False, "labels_created": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Explicitly archive or evaluate; defaults offline.")
    parser.add_argument("--district", action="append", help="Explicit canonical district ID; repeat to select several.")
    parser.add_argument("--archive", type=Path, action="append", help="Existing immutable forecast record for local evaluation.")
    parser.add_argument("--labels", type=Path, help="Independent observed-label CSV for local evaluation.")
    args = parser.parse_args(argv)
    if not args.run:
        result = {"mode": "offline_plan", "database_used": False, "network_used": False,
            "production_changes_made": False,
            "archive": "--run --district GJ-Gandhinagar (uses current India date; backdating is unavailable)",
            "evaluate_later": "--run --archive forecast.json --labels independently_measured.csv",
            "label_columns": ["district_id", "month", "depth_m_bgl", "is_observed", "is_imputed", "units",
                "observed_at", "available_at", "source", "source_record_id", "source_sha256", "geography_sha256", "evidence_origin"],
            "label_policy": "Timezone-aware observation/publication timestamps; evidence_origin=independent_measurement; matching canonical geography SHA256.",
            "warning": "No real labels are generated. Future targets remain pending until independent observations become available."}
    else:
        module = validation_module()
        if args.archive or args.labels:
            if args.district or not args.archive or args.labels is None:
                parser.error("Evaluation requires --archive and --labels, without --district.")
            import pandas as pd
            records = [read_json(path) for path in args.archive]
            labels = pd.read_csv(args.labels, keep_default_na=False)
            report = module.evaluate_records(records, labels)
            report["input_archive_sha256"] = [file_sha(path) for path in args.archive]
            report["input_label_csv_sha256"] = file_sha(args.labels)
            name = "evaluation-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+".json"
            destination = write_new(candidate_directory(), name, report)
            result = {"mode": "prospective_local_evaluation", "output": str(destination),
                      "matched_targets": report["matched_targets"], "pending_targets": report["pending_targets"],
                      "production_changes_made": False}
        else:
            if not args.district:
                parser.error("Archiving requires explicit --district canonical IDs.")
            result = archive_current(args.district, module)
    print(json.dumps(result, indent=2, allow_nan=False))
    return result


if __name__ == "__main__":
    main()
