"""Independent label provenance and chronology checks; no calibration claims."""
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

MODULE = Path(__file__).resolve().parents[1] / "models/crisis_validation.py"
spec = importlib.util.spec_from_file_location("crisis_validation_under_test", MODULE)
crisis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crisis)


def score(**changes):
    row = {"district_id": "GJ-Gandhinagar", "score": 84, "tier": "Crisis",
        "evidence_as_of": "2025-12-31", "published_at": "2026-01-01", "target_date": "2026-07-01",
        "model_version": "candidate-test-only", "scoring_signature": "test-signature", "evidence_kind": "district"}
    row.update(changes)
    return row


def evidence(**changes):
    row = {"district_id": "GJ-Gandhinagar", "target_date": "2026-07-01", "label": "Warning",
        "assessed_at": "2026-07-01", "available_at": "2026-07-02", "source_url": "https://example.gov.in/assessment",
        "source_sha256": "a" * 64, "evidence_id": "test-only-assessment-not-real-ground-truth",
        "label_definition": "Synthetic test fixture of an externally adjudicated four-tier assessment",
        "mapping_provenance": "Synthetic test contract; never production evidence",
        "independent_of_aquaiq": True, "derivation_method": "independent_external_assessment",
        "geography_version": "canonical-test-fixture"}
    row.update(changes)
    return row


def evaluate(scores=None, labels=None):
    return crisis.evaluate_scores(pd.DataFrame(scores or [score()]), pd.DataFrame(labels or [evidence()]),
        as_of="2026-10-15", geography_version="canonical-test-fixture")


def test_diagnostics_report_agreement_without_claiming_calibration():
    report = evaluate()
    assert report["matched_cases"] == 1
    assert report["overall"]["exact_agreement"] == 0
    assert report["overall"]["within_one_tier"] == 1
    assert report["overall"]["confusion_matrix_actual_rows_predicted_columns"]["Warning"]["Crisis"] == 1
    assert report["overall"]["per_tier"]["Safe"]["precision"] is None
    assert not report["calibrated"]
    assert not report["weights_changed"]
    assert not report["score_is_probability"]


def test_exact_target_date_matching_no_nearest_month_join():
    report = evaluate(labels=[evidence(target_date="2026-06-30")])
    assert report["status"] == "no_exact_target_matches"
    assert report["matched_cases"] == 0
    assert report["overall"]["exact_agreement"] is None


def test_separate_zone_diagnostics():
    report = evaluate([score(), score(district_id="GJ-Other", score=30, tier="Safe", evidence_kind="zone_fallback")],
        [evidence(), evidence(district_id="GJ-Other", label="Safe", evidence_id="fixture-2")])
    assert report["overall"]["exact_agreement"] == .5
    assert report["by_evidence_kind"]["zone_fallback"]["exact_agreement"] == 1


@pytest.mark.parametrize("change,match", [
    ({"evidence_as_of": "2026-01-02"}, "prospective"),
    ({"published_at": "2026-08-01"}, "prospective"),
    ({"target_date": "2027-01-01"}, "future"),
    ({"target_date": "2026-02-30"}, "valid YYYY"),
    ({"score": float("inf")}, "finite integers"),
    ({"score": 84.5}, "finite integers"),
    ({"tier": "Safe"}, "boundaries"),
    ({"evidence_kind": "inferred"}, "evidence_kind"),
])
def test_bad_scores_and_future_leak_are_rejected(change, match):
    with pytest.raises(ValueError, match=match):
        evaluate(scores=[score(**change)])


@pytest.mark.parametrize("change,match", [
    ({"independent_of_aquaiq": False}, "independence"),
    ({"derivation_method": "depth_to_score"}, "independent external"),
    ({"derivation_method": "fuzzy_logic"}, "independent external"),
    ({"derivation_method": "xgboost_predictions"}, "independent external"),
    ({"source_sha256": "missing"}, "SHA256"),
    ({"source_url": ""}, "missing source_url"),
    ({"source_url": "http://example.gov.in"}, "HTTPS"),
    ({"mapping_provenance": ""}, "missing mapping_provenance"),
    ({"label": "Over-exploited"}, "externally mapped"),
    ({"assessed_at": "2026-06-30"}, "target_date <= assessed_at"),
    ({"available_at": "2026-06-30"}, "target_date <= assessed_at"),
    ({"available_at": "2027-01-01"}, "future"),
    ({"geography_version": "different"}, "canonical geography"),
])
def test_independent_provenance_and_outcome_chronology_are_required(change, match):
    with pytest.raises(ValueError, match=match):
        evaluate(labels=[evidence(**change)])


def test_duplicate_cases_cannot_inflate_agreement():
    with pytest.raises(ValueError, match="duplicate district"):
        evaluate(scores=[score(), score()])
    with pytest.raises(ValueError, match="duplicate district"):
        evaluate(labels=[evidence(), evidence(evidence_id="another")])
    with pytest.raises(ValueError, match="Evidence IDs"):
        evaluate(labels=[evidence(), evidence(district_id="GJ-Other")])


def test_missing_metadata_is_not_invented():
    incomplete = score()
    incomplete.pop("target_date")
    with pytest.raises(ValueError, match="target_date"):
        evaluate(scores=[incomplete])


def test_no_labels_means_readiness_not_artificial_ground_truth():
    report = crisis.evaluate_scores(pd.DataFrame(), None, as_of="2026-10-15", geography_version="canonical")
    assert report["status"] == "independent_evidence_required"
    assert "overall" not in report
    assert not report["calibrated"]


def test_future_evaluation_cutoff_is_not_a_future_label_escape():
    with pytest.raises(ValueError, match="no later than today"):
        crisis.evaluate_scores(pd.DataFrame([score()]), pd.DataFrame([evidence()]),
            as_of="2099-01-01", geography_version="canonical-test-fixture")


def test_output_guards_and_default_offline_plan(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(crisis, "ROOT", tmp_path)
    candidate = tmp_path / "reports/candidates/new.json"
    assert crisis._output(candidate, []) == candidate
    with pytest.raises(ValueError):
        crisis._output(tmp_path / "models/model.json", [])
    candidate.parent.mkdir(parents=True)
    candidate.write_text("keep")
    with pytest.raises(ValueError):
        crisis._output(candidate, [])
    assert crisis.main([]) == 2
    assert "independent_evidence_required" in capsys.readouterr().out


def test_cli_does_not_accept_only_one_side():
    with pytest.raises(ValueError, match="both"):
        crisis.main(["--scores", "unused.csv"])
