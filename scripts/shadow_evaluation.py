"""Offline-first commands for the isolated direct-six-month shadow ledger.

No estimator is fitted or loaded. Only ``demo`` uses a private synthetic clock;
the prospective command interface has no issuance timestamp or clock override.
"""
from __future__ import annotations

import argparse
import calendar
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("The JSON input must be one object, not a batch or scalar.")
    return value


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def offline_plan():
    from models.shadow_ledger import locked_contract
    return {
        "mode": "offline_plan", "database_used": False, "network_used": False,
        "model_fitted_or_loaded": False, "production_changes_made": False,
        "locked_contract": locked_contract(),
        "actions": ["init", "record", "label", "evaluate", "verify", "demo"],
        "execution": "Mutating actions require --run and an explicit --ledger path.",
        "real_hgb_status": "abstain: shadow_artifact_not_approved",
        "prerequisites": [
            "Explicit approval for a separate deterministic shadow-artifact workflow.",
            "Registered fixed well panels, verified m_bgl datum and acquisition provenance.",
            "Point-in-time source versions, publication, receipt and input availability timestamps.",
            "A preregistered issuance, lead, coverage and confirmatory analysis protocol.",
        ],
        "warning": "Infrastructure and synthetic examples establish no prospective skill.",
    }


def _month_shift(month, months):
    year, number = map(int, month.split("-"))
    quotient, remainder = divmod(year * 12 + number - 1 + months, 12)
    return f"{quotient:04d}-{remainder + 1:02d}"


def synthetic_snapshot(*, district_id="SYNTHETIC-D1", origin_month="2030-09", version="synthetic-v1", current=10.):
    """Entirely invented values, sources, geography and wells; no dataset reads."""
    following = _month_shift(origin_month, 1)
    units = {
        "gwl_current": "m_bgl", "gwl_lag_3mo": "m_bgl", "gwl_lag_6mo": "m_bgl",
        "rainfall_current": "mm/month", "rainfall_3mo_avg": "mm/month",
        "monsoon_deficit_pct": "percent", "temperature": "degC",
        "evapotranspiration": "mm/month", "water_balance_proxy": "mm/month",
        "seasonal_reference": "m_bgl",
    }
    values = {"gwl_current": current, "gwl_lag_3mo": 11., "gwl_lag_6mo": 9.,
              "rainfall_current": 120., "rainfall_3mo_avg": 100.,
              "monsoon_deficit_pct": -5., "temperature": 27.,
              "evapotranspiration": 80., "water_balance_proxy": 40., "seasonal_reference": 9.}
    inputs = {}
    for name, value in values.items():
        month = _month_shift(origin_month, -3) if name == "gwl_lag_3mo" else (
            _month_shift(origin_month, -6) if name in {"gwl_lag_6mo", "seasonal_reference"} else origin_month)
        year, number = map(int, month.split("-"))
        final_day = calendar.monthrange(year, number)[1]
        inputs[name] = {
            "value": value, "units": units[name], "month": month,
            "source_id": "SYNTHETIC-source", "version_id": version,
            "observed_at": month + "-15T08:00:00+05:30",
            "period_end": month + f"-{final_day:02d}T23:59:59+05:30",
            "available_at": following + "-03T12:00:00Z", "is_observed": True,
        }
    return {
        "district_id": district_id, "origin_month": origin_month, "evidence_kind": "synthetic_fixture",
        "panel": {
            "panel_id": "SYNTHETIC-fixed-panel", "version_id": "synthetic-panel-v1",
            "geography_sha256": "a" * 64, "registered_at": "2030-01-01T00:00:00Z",
            "units": "m_bgl", "datum": "below_ground_level",
            "wells": [{"well_id": "SYNTHETIC-W1", "weight": .5}, {"well_id": "SYNTHETIC-W2", "weight": .5}],
        },
        "sources": [{"source_id": "SYNTHETIC-source", "version_id": version,
                     "sha256": hashlib.sha256(version.encode()).hexdigest(),
                     "published_at": following + "-02T12:00:00Z", "received_at": following + "-03T12:00:00Z"}],
        "inputs": inputs,
        "synthetic_hgb_prediction": 9.5,
    }


def synthetic_label(snapshot):
    from models.shadow_ledger import panel_fingerprint
    month = _month_shift(snapshot["origin_month"], 6)
    following = _month_shift(month, 1)
    return {
        "district_id": snapshot["district_id"], "month": month, "depth_m_bgl": 8.5,
        "units": "m_bgl", "datum_verified": True, "panel_sha256": panel_fingerprint(snapshot["panel"]),
        "observed_start_at": month + "-25T10:00:00+05:30", "observed_end_at": month + "-25T11:00:00+05:30",
        "available_at": following + "-03T12:00:00Z",
        "source": {"source_id": "SYNTHETIC-label-source", "version_id": "synthetic-label-v1", "sha256": "c" * 64,
                   "published_at": following + "-01T12:00:00Z", "received_at": following + "-02T12:00:00Z"},
        "label_id": f"SYNTHETIC-label-{snapshot['district_id']}-{month}", "revision_id": "v1",
        "is_observed": True, "is_imputed": False, "evidence_kind": "synthetic_fixture",
    }


def _demo_directory(path):
    destination = Path(path).resolve()
    base = (ROOT / "reports/candidates").resolve()
    if not destination.is_relative_to(base) or not destination.relative_to(base).parts:
        raise ValueError("The demo must be inside reports/candidates/shadow_*.")
    if not destination.relative_to(base).parts[0].startswith("shadow_"):
        raise ValueError("The demo must be inside reports/candidates/shadow_*.")
    destination.mkdir(parents=True, exist_ok=False)
    return destination


def run_demo(path):
    """Synthetic integration exercise; the fake HGB number is never a model."""
    from models.shadow_ledger import FileLedger
    directory = _demo_directory(path)
    clock = ["2030-10-18T12:00:00Z"]
    ledger = FileLedger.create(directory / "ledger", lane="synthetic", campaign_id="SYNTHETIC-demo",
                               workspace=ROOT, clock=lambda: clock[0])
    first = synthetic_snapshot()
    write_new(directory / "SYNTHETIC_forecast_fixture.json", first)
    label = synthetic_label(first)
    write_new(directory / "SYNTHETIC_label_fixture.json", label)
    archived = ledger.append_forecast(first)
    original = copy.deepcopy(archived)
    checks = {}

    def rejected(name, snapshot, expected):
        try:
            ledger.append_forecast(snapshot)
        except expected as error:
            checks[name] = {"rejected": True, "error": str(error)}
        else:
            raise AssertionError(f"Synthetic safety exercise unexpectedly accepted: {name}")

    rejected("duplicate_issuance", first, FileExistsError)
    late = synthetic_snapshot(district_id="SYNTHETIC-late")
    late["inputs"]["rainfall_current"]["available_at"] = "2030-10-19T00:00:00Z"
    rejected("late_input", late, ValueError)
    revised = synthetic_snapshot(version="synthetic-v2", current=12.)
    rejected("source_revision_cannot_replace_existing_slot", revised, FileExistsError)
    missing = synthetic_snapshot(district_id="SYNTHETIC-missing-baseline")
    missing["inputs"]["seasonal_reference"] = {"value": None, "missing_reason": "SYNTHETIC not acquired"}
    missing_record = ledger.append_forecast(missing)
    checks["missing_baseline"] = missing_record["record"]["predictions"]["seasonal_naive"]

    # Advancing an admissible source history creates a distinct future slot;
    # neither revised source values nor caller mutations change the old record.
    clock[0] = "2030-11-18T12:00:00Z"
    ledger.append_forecast(synthetic_snapshot(origin_month="2030-10", version="synthetic-v2", current=12.))
    first["inputs"]["gwl_current"]["value"] = 999.
    archived["record"]["predictions"]["persistence"]["prediction_m_bgl"] = 999.
    stored = next(item for item in ledger.forecasts() if item["record"]["entry_id"] == original["record"]["entry_id"])
    if stored != original:
        raise AssertionError("Historical prediction changed after a caller/source mutation.")
    checks["historical_snapshot_immutable_after_revision_and_copy_mutation"] = True
    clock[0] = "2031-04-05T12:00:00Z"
    ledger.append_label(label)
    report = ledger.evaluate(label_policy="first", persist=True)
    result = {
        "mode": "SYNTHETIC_ONLY_DRY_RUN", "ledger": str(directory / "ledger"),
        "notice": "All wells, observations, versions, dates and HGB predictions are synthetic. The HGB slot is an untrained placeholder.",
        "model_fitted_or_loaded": False, "real_observations_read": False, "database_used": False,
        "production_changes_made": False, "prospective_skill_established": False,
        "checks": checks, "integrity": ledger.verify(),
        "evaluation": report,
    }
    write_new(directory / "SYNTHETIC_DEMO_SUMMARY.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="plan", choices=("plan", "init", "record", "label", "evaluate", "verify", "demo"))
    parser.add_argument("--run", action="store_true", help="Execute the selected isolated action; otherwise print the offline plan.")
    parser.add_argument("--ledger", type=Path, help="Explicit candidate ledger path, or a new synthetic-demo directory.")
    parser.add_argument("--lane", choices=("prospective", "retrospective", "synthetic"), help="Required when creating a ledger; never mix evidence lanes.")
    parser.add_argument("--campaign", help="Immutable campaign identity required when creating a ledger.")
    parser.add_argument("--input", type=Path, help="One forecast snapshot or observed-label JSON object; read only.")
    parser.add_argument("--label-policy", choices=("first", "latest"), default="first")
    args = parser.parse_args(argv)
    if args.action == "plan" or not args.run:
        result = offline_plan()
    else:
        from models.shadow_ledger import FileLedger
        if args.ledger is None:
            parser.error("Execution requires an explicit --ledger path.")
        if args.action == "demo":
            if args.input or args.lane not in (None, "synthetic"):
                parser.error("Demo creates synthetic fixtures only; --input and real lanes are forbidden.")
            result = run_demo(args.ledger)
        elif args.action == "init":
            if not args.lane or not args.campaign:
                parser.error("init requires --lane and --campaign.")
            ledger = FileLedger.create(args.ledger, lane=args.lane, campaign_id=args.campaign, workspace=ROOT)
            result = {"mode": "isolated_ledger_created", "ledger": str(args.ledger.resolve()), "integrity": ledger.verify()}
        else:
            ledger = FileLedger.open(args.ledger, workspace=ROOT)
            if args.action in ("record", "label"):
                if args.input is None:
                    parser.error(f"{args.action} requires --input JSON.")
                payload = read_json(args.input)
                result = ledger.append_forecast(payload) if args.action == "record" else ledger.append_label(payload)
            elif args.action == "evaluate":
                result = ledger.evaluate(label_policy=args.label_policy, persist=True)
            else:
                result = ledger.verify()
    print(json.dumps(result, indent=2, allow_nan=False))
    return result


if __name__ == "__main__":
    main()
