"""Synthetic-only acceptance tests for the isolated direct-six-month ledger.

These fixtures never load a dataset, estimator, checkpoint, database or network.
The HGB number is explicitly a synthetic placeholder rather than fitted output.
"""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from models import shadow_ledger as shadow


ISSUED = "2026-10-18T12:00:00+00:00"
AFTER_LABEL = "2027-04-05T12:00:00+00:00"


def ledger_path(workspace, name="synthetic"):
    return workspace / "reports" / "candidates" / ("shadow_" + name)


@pytest.fixture
def snapshot():
    units = {
        "gwl_current": "m_bgl", "gwl_lag_3mo": "m_bgl", "gwl_lag_6mo": "m_bgl",
        "rainfall_current": "mm/month", "rainfall_3mo_avg": "mm/month",
        "monsoon_deficit_pct": "percent", "temperature": "degC",
        "evapotranspiration": "mm/month", "water_balance_proxy": "mm/month",
        "seasonal_reference": "m_bgl",
    }
    values = {"gwl_current": 10., "gwl_lag_3mo": 11., "gwl_lag_6mo": 9.,
              "rainfall_current": 120., "rainfall_3mo_avg": 100.,
              "monsoon_deficit_pct": -5., "temperature": 27.,
              "evapotranspiration": 80., "water_balance_proxy": 40.,
              "seasonal_reference": 9.}
    inputs = {}
    for name, value in values.items():
        month = "2026-06" if name == "gwl_lag_3mo" else (
            "2026-03" if name in {"gwl_lag_6mo", "seasonal_reference"} else "2026-09")
        month_end = {"2026-03": "2026-03-31", "2026-06": "2026-06-30",
                     "2026-09": "2026-09-30"}[month]
        inputs[name] = {
            "value": value, "units": units[name], "month": month,
            "source_id": "SYNTHETIC-source", "version_id": "synthetic-v1",
            "observed_at": month + "-15T08:00:00+05:30",
            "period_end": month_end + "T23:59:59+05:30",
            "available_at": "2026-10-03T12:00:00+00:00", "is_observed": True,
        }
    return {
        "district_id": "SYNTHETIC-D1", "origin_month": "2026-09",
        "evidence_kind": "synthetic_fixture",
        "panel": {
            "panel_id": "SYNTHETIC-fixed-panel", "version_id": "panel-v1",
            "geography_sha256": "a" * 64, "registered_at": "2026-08-01T00:00:00Z",
            "units": "m_bgl", "datum": "below_ground_level",
            "wells": [{"well_id": "SYNTHETIC-W1", "weight": .5},
                      {"well_id": "SYNTHETIC-W2", "weight": .5}],
        },
        "sources": [{"source_id": "SYNTHETIC-source", "version_id": "synthetic-v1",
                     "sha256": "b" * 64, "published_at": "2026-10-02T12:00:00Z",
                     "received_at": "2026-10-03T12:00:00Z"}],
        "inputs": inputs, "synthetic_hgb_prediction": 9.5,
    }


@pytest.fixture
def ledger(tmp_path):
    return shadow.FileLedger.create(ledger_path(tmp_path), lane="synthetic",
                                    campaign_id="SYNTHETIC-campaign", workspace=tmp_path,
                                    clock=lambda: ISSUED)


@pytest.fixture
def label(snapshot):
    return {
        "district_id": snapshot["district_id"], "month": "2027-03", "depth_m_bgl": 8.5,
        "units": "m_bgl", "datum_verified": True,
        "panel_sha256": shadow.panel_fingerprint(snapshot["panel"]),
        "observed_start_at": "2027-03-25T10:00:00+05:30",
        "observed_end_at": "2027-03-25T11:00:00+05:30",
        "available_at": "2027-04-03T12:00:00Z",
        "source": {"source_id": "SYNTHETIC-label-source", "version_id": "label-v1",
                   "sha256": "c" * 64, "published_at": "2027-04-01T12:00:00Z",
                   "received_at": "2027-04-02T12:00:00Z"},
        "label_id": "SYNTHETIC-label-D1-2027-03", "revision_id": "v1",
        "is_observed": True, "is_imputed": False, "evidence_kind": "synthetic_fixture",
    }


def later_ledger(tmp_path, *, lane="synthetic"):
    ledger = shadow.FileLedger.open(ledger_path(tmp_path), workspace=tmp_path,
                                    clock=lambda: AFTER_LABEL)
    assert ledger.header["lane"] == lane
    return ledger


def real_schema_metadata(snapshot, label=None, *, keep_stub=False):
    """Exercise real-schema validation using isolated test metadata only."""
    snapshot = copy.deepcopy(snapshot)
    snapshot["evidence_kind"] = "real_observation"
    snapshot["district_id"] = "FIXTURE-D1"
    snapshot["panel"]["panel_id"] = "FIXTURE-panel"
    for index, well in enumerate(snapshot["panel"]["wells"]):
        well["well_id"] = "FIXTURE-W" + str(index + 1)
    for source in snapshot["sources"]:
        source["source_id"] = "FIXTURE-source"
    for item in snapshot["inputs"].values():
        if "source_id" in item:
            item["source_id"] = "FIXTURE-source"
    if not keep_stub:
        snapshot.pop("synthetic_hgb_prediction", None)
    if label is None:
        return snapshot
    label = copy.deepcopy(label)
    label.update(evidence_kind="real_observation", district_id=snapshot["district_id"],
                 panel_sha256=shadow.panel_fingerprint(snapshot["panel"]))
    label["source"]["source_id"] = "FIXTURE-label-source"
    return snapshot, label


def test_snapshot_archives_three_fixed_predictions_and_no_skill_claim(ledger, snapshot):
    envelope = ledger.append_forecast(snapshot)
    predictions = envelope["record"]["predictions"]
    assert set(predictions) == {"hist_gradient_boosting", "persistence", "seasonal_naive"}
    assert predictions["hist_gradient_boosting"]["prediction_m_bgl"] == 9.5
    assert predictions["persistence"]["prediction_m_bgl"] == 10.
    assert predictions["seasonal_naive"]["prediction_m_bgl"] == 9.
    assert all(row["status"] == "predicted" for row in predictions.values())
    report = ledger.evaluate(persist=False)
    assert report["sufficient_for_operational_use"] is False
    assert not report["cases"]
    assert report["pending"]


@pytest.mark.parametrize("timestamp", ["2026-10-18T12:00:00", "not-a-date"])
def test_issuance_requires_timezone_aware_clock(tmp_path, snapshot, timestamp):
    with pytest.raises((ValueError, TypeError)):
        ledger = shadow.FileLedger.create(ledger_path(tmp_path, "bad_clock"), lane="synthetic",
                                          campaign_id="SYNTHETIC-campaign", workspace=tmp_path,
                                          clock=lambda: timestamp)
        ledger.append_forecast(snapshot)


@pytest.mark.parametrize("field", ["available_at", "observed_at", "period_end"])
def test_forecast_rejects_future_or_late_input_not_just_calendar_leakage(ledger, snapshot, field):
    snapshot["inputs"]["rainfall_current"][field] = "2026-10-19T12:00:00Z"
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)
    assert ledger.forecasts() == []


@pytest.mark.parametrize("field", ["published_at", "received_at"])
def test_source_publication_and_receipt_must_precede_issuance(ledger, snapshot, field):
    snapshot["sources"][0][field] = "2026-10-19T12:00:00Z"
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)
    assert ledger.forecasts() == []


def test_late_receipt_cannot_be_hidden_by_earlier_available_at(ledger, snapshot):
    snapshot["sources"][0]["received_at"] = "2026-10-04T12:00:00Z"
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)


def test_incomplete_monthly_input_cannot_claim_month_start_availability(ledger, snapshot):
    weather = snapshot["inputs"]["rainfall_current"]
    weather["available_at"] = "2026-09-01T00:00:00Z"
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)


@pytest.mark.parametrize("name", ["rainfall_current", "rainfall_3mo_avg", "monsoon_deficit_pct",
                                  "temperature", "evapotranspiration", "water_balance_proxy"])
def test_monthly_weather_cannot_use_partial_month_disguised_as_full_total(ledger, snapshot, name):
    snapshot["inputs"][name]["period_end"] = "2026-09-20T23:59:59+05:30"
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)
    assert ledger.forecasts() == []


def test_input_joins_exact_source_revision_and_calendar_lag(ledger, snapshot):
    changed = copy.deepcopy(snapshot)
    changed["inputs"]["gwl_lag_3mo"]["version_id"] = "not-the-archived-version"
    with pytest.raises(ValueError):
        ledger.append_forecast(changed)
    changed = copy.deepcopy(snapshot)
    changed["inputs"]["gwl_lag_6mo"]["month"] = "2026-04"
    with pytest.raises(ValueError):
        ledger.append_forecast(changed)


@pytest.mark.parametrize("name,model,reason", [
    ("gwl_current", "persistence", "missing_or_unobserved_origin"),
    ("seasonal_reference", "seasonal_naive", "missing_or_unobserved_seasonal"),
])
def test_missing_baselines_are_recorded_abstentions(ledger, snapshot, name, model, reason):
    snapshot["inputs"][name] = {"value": None, "missing_reason": "synthetic unavailable reading"}
    record = ledger.append_forecast(snapshot)["record"]
    prediction = record["predictions"][model]
    assert prediction["status"] == "abstained"
    assert prediction["prediction_m_bgl"] is None
    assert reason in prediction["reason_codes"]
    assert len(ledger.forecasts()) == 1


@pytest.mark.parametrize("name,model", [("gwl_current", "persistence"),
                                       ("seasonal_reference", "seasonal_naive")])
def test_unobserved_values_do_not_become_observed_baselines(ledger, snapshot, name, model):
    snapshot["inputs"][name]["is_observed"] = False
    snapshot["inputs"][name]["observed_at"] = (
        "2026-08-15T08:00:00+05:30" if name == "gwl_current" else "2026-02-15T08:00:00+05:30")
    row = ledger.append_forecast(snapshot)["record"]["predictions"][model]
    assert row["status"] == "abstained" and row["prediction_m_bgl"] is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_nonfinite_or_boolean_depths_are_rejected(ledger, snapshot, value):
    snapshot["inputs"]["gwl_current"]["value"] = value
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)


def test_panel_is_registered_before_issue_and_uses_unambiguous_wells(ledger, snapshot):
    changed = copy.deepcopy(snapshot)
    changed["panel"]["registered_at"] = "2026-10-19T00:00:00Z"
    with pytest.raises(ValueError):
        ledger.append_forecast(changed)
    changed = copy.deepcopy(snapshot)
    changed["panel"]["wells"][1]["well_id"] = changed["panel"]["wells"][0]["well_id"]
    with pytest.raises(ValueError):
        ledger.append_forecast(changed)


def test_duplicate_schedule_slot_cannot_be_reissued_with_revised_source(ledger, snapshot):
    first = ledger.append_forecast(snapshot)
    revised = copy.deepcopy(snapshot)
    revised["sources"][0].update(version_id="synthetic-v2", sha256="d" * 64)
    for row in revised["inputs"].values():
        row["version_id"] = "synthetic-v2"
    revised["inputs"]["gwl_current"]["value"] = 12.
    with pytest.raises(FileExistsError):
        ledger.append_forecast(revised)
    assert ledger.forecasts() == [first]


def test_separate_districts_have_distinct_slots(ledger, snapshot):
    ledger.append_forecast(snapshot)
    second = copy.deepcopy(snapshot)
    second["district_id"] = "SYNTHETIC-D2"
    ledger.append_forecast(second)
    assert len(ledger.forecasts()) == 2


def test_nested_caller_mutations_cannot_rewrite_archived_predictions(ledger, snapshot):
    archived = ledger.append_forecast(snapshot)
    original = copy.deepcopy(archived)
    snapshot["inputs"]["gwl_current"]["value"] = 999.
    snapshot["panel"]["wells"][0]["weight"] = .99
    archived["record"]["predictions"]["persistence"]["prediction_m_bgl"] = 999.
    assert ledger.forecasts() == [original]
    ledger.verify()


def test_archive_reopen_preserves_bytes_and_detects_tampering(tmp_path, ledger, snapshot):
    ledger.append_forecast(snapshot)
    path = ledger_path(tmp_path)
    before = {file.relative_to(path): file.read_bytes() for file in path.rglob("*") if file.is_file()}
    reopened = shadow.FileLedger.open(path, workspace=tmp_path, clock=lambda: ISSUED)
    reopened.verify()
    assert before == {file.relative_to(path): file.read_bytes() for file in path.rglob("*") if file.is_file()}
    # Corrupt only a forecast payload, never a source dataset or real artifact.
    target = next(file for file in path.rglob("*.json")
                  if b"prediction_m_bgl" in file.read_bytes())
    data = json.loads(target.read_text(encoding="utf-8"))
    target.write_text(json.dumps({**data, "synthetic_tamper": True}), encoding="utf-8")
    with pytest.raises(ValueError):
        reopened.verify()


@pytest.mark.parametrize("other_lane", ["prospective", "retrospective"])
def test_existing_ledger_cannot_be_relabelled_as_another_evidence_lane(tmp_path, ledger, other_lane):
    with pytest.raises((ValueError, TypeError)):
        shadow.FileLedger.open(ledger_path(tmp_path), lane=other_lane,
                               campaign_id="SYNTHETIC-campaign", workspace=tmp_path,
                               clock=lambda: ISSUED)
    assert shadow.FileLedger.open(ledger_path(tmp_path), workspace=tmp_path,
                                  clock=lambda: ISSUED).header["lane"] == "synthetic"


def test_synthetic_predictions_cannot_enter_prospective_lane(tmp_path, snapshot):
    ledger = shadow.FileLedger.create(ledger_path(tmp_path, "prospective"), lane="prospective",
                                     campaign_id="preregistered-campaign", workspace=tmp_path,
                                     clock=lambda: ISSUED)
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)
    snapshot = real_schema_metadata(snapshot, keep_stub=True)
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)


def test_real_candidate_abstains_without_approved_shadow_artifact(tmp_path, snapshot):
    ledger = shadow.FileLedger.create(ledger_path(tmp_path, "prospective"), lane="prospective",
                                     campaign_id="preregistered-campaign", workspace=tmp_path,
                                     clock=lambda: ISSUED)
    snapshot = real_schema_metadata(snapshot)
    row = ledger.append_forecast(snapshot)["record"]["predictions"]["hist_gradient_boosting"]
    assert row["status"] == "abstained" and row["prediction_m_bgl"] is None
    assert "shadow_artifact_not_approved" in row["reason_codes"]


def test_prospective_issuance_timestamp_cannot_be_caller_backdated(tmp_path, snapshot):
    ledger = shadow.FileLedger.create(ledger_path(tmp_path, "prospective"), lane="prospective",
                                     campaign_id="preregistered-campaign", workspace=tmp_path,
                                     clock=lambda: ISSUED)
    snapshot = real_schema_metadata(snapshot)
    snapshot["issued_at"] = "2026-10-17T00:00:00Z"
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)


def test_late_arriving_measured_label_matches_only_after_receipt(tmp_path, ledger, snapshot, label):
    ledger.append_forecast(snapshot)
    with pytest.raises(ValueError):
        ledger.append_label(label)
    later = later_ledger(tmp_path)
    later.append_label(label)
    report = later.evaluate(persist=False)
    assert len(report["cases"]) == 1
    assert report["sufficient_for_operational_use"] is False


def test_label_revisions_append_and_never_change_forecast_snapshot(tmp_path, ledger, snapshot, label):
    forecast = ledger.append_forecast(snapshot)
    later = later_ledger(tmp_path)
    first = later.append_label(label)
    revised = copy.deepcopy(label)
    revised.update(depth_m_bgl=8., revision_id="v2", supersedes_sha256=first["record"]["record_sha256"])
    revised["source"].update(version_id="label-v2", sha256="d" * 64,
                             published_at="2027-04-04T10:00:00Z", received_at="2027-04-04T12:00:00Z")
    revised["available_at"] = "2027-04-04T13:00:00Z"
    second = later.append_label(revised)
    assert first != second
    assert len(later.labels()) == 2
    assert later.forecasts() == [forecast]
    first_report = later.evaluate(label_policy="first", persist=False)
    latest_report = later.evaluate(label_policy="latest", persist=False)
    assert len(first_report["cases"]) == len(latest_report["cases"]) == 1
    assert first_report["cases"] != latest_report["cases"]
    later.verify()


def test_label_revision_requires_parent_identity(tmp_path, ledger, snapshot, label):
    ledger.append_forecast(snapshot)
    later = later_ledger(tmp_path)
    later.append_label(label)
    revised = copy.deepcopy(label)
    revised.update(depth_m_bgl=8., revision_id="v2")
    revised["source"].update(version_id="label-v2", sha256="d" * 64)
    with pytest.raises((ValueError, FileExistsError)):
        later.append_label(revised)
    assert len(later.labels()) == 1


@pytest.mark.parametrize("field,value", [("is_observed", False), ("is_imputed", True),
                                        ("units", "m"), ("datum_verified", False),
                                        ("observed_end_at", "2027-04-01T00:00:00Z"),
                                        ("depth_m_bgl", float("nan")),
                                        ("evidence_kind", "real_observation")])
def test_label_provenance_and_observation_month_are_required(tmp_path, ledger, snapshot, label, field, value):
    ledger.append_forecast(snapshot)
    later = later_ledger(tmp_path)
    label[field] = value
    with pytest.raises(ValueError):
        later.append_label(label)


def test_mismatched_well_panel_cannot_enter_paired_evaluation(tmp_path, ledger, snapshot, label):
    ledger.append_forecast(snapshot)
    later = later_ledger(tmp_path)
    label["panel_sha256"] = "f" * 64
    later.append_label(label)
    report = later.evaluate(persist=False)
    assert len(report["cases"]) == 1
    assert report["cases"][0]["paired_eligible"] is False
    assert "well_panel_mismatch" in report["cases"][0]["reason_codes"]
    assert report["sufficient_for_operational_use"] is False


def test_repeated_evaluation_cannot_overwrite_an_existing_snapshot(tmp_path, ledger, snapshot, label):
    ledger.append_forecast(snapshot)
    later = later_ledger(tmp_path)
    later.append_label(label)
    directory = ledger_path(tmp_path)
    first = later.evaluate(persist=True)
    before = {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()}
    try:
        second = later.evaluate(persist=True)
    except FileExistsError:
        second = first
    assert second["cases"] == first["cases"]
    assert all(path.read_bytes() == content for path, content in before.items())


def test_missing_baseline_remains_in_coverage_but_out_of_paired_skill(tmp_path, ledger, snapshot, label):
    snapshot["inputs"]["seasonal_reference"] = {"value": None, "missing_reason": "not acquired"}
    ledger.append_forecast(snapshot)
    later = later_ledger(tmp_path)
    later.append_label(label)
    report = later.evaluate(persist=False)
    assert len(report["cases"]) == 1
    assert report["cases"][0]["paired_eligible"] is False
    assert report["cohorts"]["synthetic"]["n"] == 1
    assert report["cohorts"]["synthetic"]["paired_n"] == 0
    assert all(row["n"] == 0 for row in report["cohorts"]["synthetic"]["models"].values())


def test_genuine_post_archive_label_has_nominal_not_false_full_month_lead(tmp_path, snapshot, label):
    # Simulated real-schema metadata stays exclusively in this temporary test.
    prospective = shadow.FileLedger.create(ledger_path(tmp_path), lane="prospective",
                                          campaign_id="SYNTHETIC-campaign", workspace=tmp_path,
                                          clock=lambda: ISSUED)
    snapshot, label = real_schema_metadata(snapshot, label)
    prospective.append_forecast(snapshot)
    later = later_ledger(tmp_path, lane="prospective")
    later.append_label(label)
    report = later.evaluate(persist=False)
    assert len(report["cases"]) == 1
    assert report["cases"][0]["classification"] == "prospective_nominal_six_month"
    assert report["cases"][0]["paired_eligible"] is False  # HGB artifact unavailable.
    assert "prospective_six_full_month" not in report["cohorts"]
    assert report["sufficient_for_operational_use"] is False


def test_historical_backfill_never_becomes_prospective_by_changing_issue_metadata(tmp_path, snapshot, label):
    retrospective = shadow.FileLedger.create(ledger_path(tmp_path, "retrospective"), lane="retrospective",
                                            campaign_id="SYNTHETIC-historical", workspace=tmp_path,
                                            clock=lambda: AFTER_LABEL)
    snapshot, label = real_schema_metadata(snapshot, label)
    snapshot["issued_at"] = ISSUED
    retrospective.append_forecast(snapshot)
    retrospective.append_label(label)
    report = retrospective.evaluate(persist=False)
    assert len(report["cases"]) == 1
    assert report["cases"][0]["classification"] == "retrospective"
    assert set(report["cohorts"]) == {"retrospective"}
    assert report["sufficient_for_operational_use"] is False


@pytest.mark.parametrize("location", ["input", "source", "panel"])
def test_provenance_timestamps_cannot_silently_assume_a_timezone(ledger, snapshot, location):
    if location == "input":
        snapshot["inputs"]["gwl_current"]["available_at"] = "2026-10-03T12:00:00"
    elif location == "source":
        snapshot["sources"][0]["published_at"] = "2026-10-02T12:00:00"
    else:
        snapshot["panel"]["registered_at"] = "2026-08-01T00:00:00"
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)


@pytest.mark.parametrize("location", ["input", "source", "panel"])
@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_malformed_provenance_time_cannot_be_archived(ledger, snapshot, location, missing):
    container, field = (
        (snapshot["inputs"]["gwl_current"], "available_at") if location == "input" else
        (snapshot["sources"][0], "published_at") if location == "source" else
        (snapshot["panel"], "registered_at"))
    if missing:
        del container[field]
    else:
        container[field] = "not-a-timestamp"
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)
    assert ledger.forecasts() == []


@pytest.mark.parametrize("relative", ["data/shadow_ledger", "models/shadow_ledger",
                                      "reports/existing_report", "reports/candidates/not_shadow"])
def test_ledger_writer_cannot_touch_protected_or_unscoped_paths(tmp_path, relative):
    with pytest.raises(ValueError):
        shadow.FileLedger.create(tmp_path / relative, lane="synthetic", campaign_id="SYNTHETIC-campaign",
                                 workspace=tmp_path, clock=lambda: ISSUED)
    assert not (tmp_path / relative).exists()


def test_concurrent_duplicate_issuance_cannot_create_two_snapshots(tmp_path, ledger, snapshot):
    second_handle = shadow.FileLedger.open(ledger_path(tmp_path), workspace=tmp_path,
                                          clock=lambda: ISSUED)
    barrier = Barrier(2)

    def archive(handle):
        barrier.wait(timeout=5)
        try:
            return "archived", handle.append_forecast(copy.deepcopy(snapshot))
        except (FileExistsError, ValueError) as error:
            return "rejected", str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(archive, handle) for handle in (ledger, second_handle)]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(row[0] for row in results) == ["archived", "rejected"]
    assert len(ledger.forecasts()) == 1
    ledger.verify()


@pytest.mark.parametrize("weights", [[0., 1.], [-.1, 1.1], [.4, .4], [True, 0.],
                                     [float("nan"), .5], [float("inf"), .5]])
def test_invalid_or_ambiguous_well_weights_are_rejected(ledger, snapshot, weights):
    for well, weight in zip(snapshot["panel"]["wells"], weights):
        well["weight"] = weight
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)
    assert ledger.forecasts() == []


@pytest.mark.parametrize("field", ["observed_start_at", "observed_end_at", "available_at"])
def test_label_times_require_explicit_timezones(tmp_path, ledger, snapshot, label, field):
    ledger.append_forecast(snapshot)
    label[field] = label[field].split("T")[0] + "T00:00:00"
    with pytest.raises(ValueError):
        later_ledger(tmp_path).append_label(label)


def test_contract_preserves_selected_model_cutoff_and_configuration_hashes(ledger, snapshot):
    contract = ledger.header["contract"]
    assert contract["candidate"] == {
        "candidate_id": "hist_gradient_boosting-2-delta", "family": "hist_gradient_boosting",
        "target_form": "delta", "parameters": {"max_iter": 250, "learning_rate": .05,
            "max_leaf_nodes": 31, "min_samples_leaf": 50, "l2_regularization": 20.},
    }
    assert contract["train_target_cutoff"] == "2018-12-31"
    assert contract["training_pairs"] == 14817
    assert contract["random_state"] == 42 and contract["early_stopping"] is False
    assert contract["model_sha256"] is None
    assert contract["model_artifact_status"] == "not_approved_not_created"
    assert ledger.header["real_hgb_enabled"] is False
    archived = ledger.append_forecast(snapshot)["record"]
    assert archived["candidate_configuration_sha256"] == shadow.checksum(contract)
    assert archived["configuration_sha256"] == ledger.header["configuration_sha256"]
    assert archived["feature_pipeline_sha256"] == ledger.header["feature_pipeline_sha256"]


def label_revision(label, parent, revision_id="v2", depth=8.):
    revised = copy.deepcopy(label)
    revised.update(depth_m_bgl=depth, revision_id=revision_id,
                   supersedes_sha256=parent["record"]["record_sha256"])
    revised["source"].update(version_id="label-" + revision_id, sha256="d" * 64)
    return revised


def test_label_revision_cannot_fork_an_already_superseded_parent(tmp_path, ledger, snapshot, label):
    ledger.append_forecast(snapshot)
    later = later_ledger(tmp_path)
    first = later.append_label(label)
    later.append_label(label_revision(label, first))
    with pytest.raises((ValueError, FileExistsError)):
        later.append_label(label_revision(label, first, "v3", 7.5))
    assert len(later.labels()) == 2
    later.verify()


def test_equal_availability_timestamps_use_revision_lineage_for_first_and_latest(tmp_path, ledger, snapshot, label):
    ledger.append_forecast(snapshot)
    later = later_ledger(tmp_path)
    first = later.append_label(label)
    second = later.append_label(label_revision(label, first))
    third = later.append_label(label_revision(label, second, "v3", 7.5))
    assert first["record"]["available_at"] == second["record"]["available_at"]
    assert first["record"]["recorded_at_utc"] == second["record"]["recorded_at_utc"]
    first_report = later.evaluate(label_policy="first", persist=False)
    latest_report = later.evaluate(label_policy="latest", persist=False)
    assert first_report["cases"][0]["label_sha256"] == first["record"]["record_sha256"]
    assert latest_report["cases"][0]["label_sha256"] == third["record"]["record_sha256"]
    assert first_report["cases"][0]["actual_m_bgl"] == 8.5
    assert latest_report["cases"][0]["actual_m_bgl"] == 7.5


def test_concurrent_label_revisions_cannot_fork_one_parent(tmp_path, ledger, snapshot, label):
    ledger.append_forecast(snapshot)
    later = later_ledger(tmp_path)
    first = later.append_label(label)
    alternate = later_ledger(tmp_path)
    barrier = Barrier(2)

    def revise(handle, revision_id, depth):
        barrier.wait(timeout=5)
        try:
            return "archived", handle.append_label(label_revision(label, first, revision_id, depth))
        except (ValueError, FileExistsError) as error:
            return "rejected", str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(revise, later, "v2a", 8.),
                   executor.submit(revise, alternate, "v2b", 7.5)]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(item[0] for item in results) == ["archived", "rejected"]
    assert len(later.labels()) == 2
    later.verify()


@pytest.mark.parametrize("field", ["predictions", "model_sha256", "candidate",
                                   "model_configuration", "train_target_cutoff", "feature_values"])
def test_caller_cannot_supply_predictions_or_override_locked_model_fields(ledger, snapshot, field):
    snapshot[field] = {"unapproved": "caller override"}
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)
    assert ledger.forecasts() == []


@pytest.mark.parametrize("field", ["observed_at", "period_end", "available_at"])
def test_missing_value_cannot_carry_future_provenance_metadata(ledger, snapshot, field):
    snapshot["inputs"]["gwl_lag_3mo"] = {
        "value": None, "missing_reason": "unavailable at issuance",
        field: "2026-10-19T00:00:00Z",
    }
    with pytest.raises(ValueError):
        ledger.append_forecast(snapshot)
    assert ledger.forecasts() == []


@pytest.mark.parametrize("field", ["record_sha256", "schema_version", "kind", "entry_id", "identity",
                                   "ledger_sha256", "recorded_at_utc", "lane"])
def test_label_caller_cannot_override_reserved_ledger_fields(tmp_path, ledger, snapshot, label, field):
    ledger.append_forecast(snapshot)
    later = later_ledger(tmp_path)
    label[field] = "caller cannot set ledger identity"
    with pytest.raises(ValueError):
        later.append_label(label)
    assert later.labels() == []
    later.verify()  # Rejected metadata must also release its transient revision lock.


def test_six_full_month_lead_requires_actual_archive_before_acquisition_threshold(tmp_path, snapshot, label):
    snapshot, label = real_schema_metadata(snapshot, label)
    issued = "2026-09-18T12:00:00Z"
    prospective = shadow.FileLedger.create(ledger_path(tmp_path), lane="prospective",
                                          campaign_id="FIXTURE-full-lead", workspace=tmp_path,
                                          clock=lambda: issued)
    for name, item in snapshot["inputs"].items():
        if name not in {"gwl_current", "gwl_lag_3mo", "gwl_lag_6mo", "seasonal_reference"}:
            snapshot["inputs"][name] = {"value": None,
                "missing_reason": "complete origin-month weather unavailable at midmonth issuance"}
        else:
            item["available_at"] = "2026-09-17T12:00:00Z"
    snapshot["inputs"]["gwl_current"]["period_end"] = "2026-09-15T23:59:59+05:30"
    snapshot["sources"][0].update(published_at="2026-09-16T12:00:00Z",
                                  received_at="2026-09-17T12:00:00Z")
    forecast = prospective.append_forecast(snapshot)
    assert forecast["record"]["predictions"]["hist_gradient_boosting"]["status"] == "abstained"
    later = shadow.FileLedger.open(ledger_path(tmp_path), workspace=tmp_path, clock=lambda: AFTER_LABEL)
    later.append_label(label)
    report = later.evaluate(persist=False)
    assert report["cases"][0]["classification"] == "prospective_six_full_month"
    assert report["cases"][0]["paired_eligible"] is False
    assert report["cohorts"]["prospective_six_full_month"]["paired_n"] == 0
    assert report["sufficient_for_operational_use"] is False
