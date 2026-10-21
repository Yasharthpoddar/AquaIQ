"""Isolated historical horizons: calendar labels, leakage and artifact guards.

All observations in this module are synthetic test fixtures. No test fits a
model, loads production data, accesses a database or issues a forecast.
"""
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from models import research_horizon as research


def monthly_frame(start="2004-01-01", end="2016-12-01", districts=("A", "B")):
    panels = []
    for offset, district in enumerate(districts):
        dates = pd.date_range(start, end, freq="MS")
        panels.append(pd.DataFrame({
            "district_id": district,
            "date": dates,
            "gwl_current": 5. + 10. * offset + np.arange(len(dates)) * .025,
            "is_observed": pd.Series(True, index=range(len(dates)), dtype=object),
            "is_imputed": pd.Series(False, index=range(len(dates)), dtype=object),
            "months_since_observation": 0,
            "rainfall_current": 20. + dates.month,
        }))
    return pd.concat(panels, ignore_index=True)


def case_at(frame, date, district="A"):
    return frame.loc[(frame.district_id == district) &
                     (frame.date == pd.Timestamp(date))].iloc[0]


def test_twelve_month_target_is_exact_calendar_join_and_keeps_missing_cases():
    frame = monthly_frame(districts=("A",))
    frame = frame.loc[frame.date != pd.Timestamp("2011-02-01")].copy()
    cases = research.build_cases(frame, horizon_months=12)
    assert len(cases) == len(frame)
    assert (cases.target_date == cases.date + pd.DateOffset(months=12)).all()
    missing = case_at(cases, "2010-02-01")
    assert missing.target_date == pd.Timestamp("2011-02-01")
    assert pd.isna(missing.target_value) and not missing.target_is_observed
    present = case_at(cases, "2010-01-01")
    assert present.target_value == case_at(frame, "2011-01-01").gwl_current
    assert present.target_is_observed
    assert pd.isna(case_at(cases, "2016-12-01").target_value)


@pytest.mark.parametrize("observed,imputed", [
    (False, True), ("False", "True"), (None, False), ("unknown", False),
    (True, None), (True, "unknown"),
])
def test_only_finite_explicit_observations_create_target_labels(observed, imputed):
    frame = monthly_frame(districts=("A",))
    target = frame.date == pd.Timestamp("2011-01-01")
    frame.loc[target, "is_observed"] = observed
    frame.loc[target, "is_imputed"] = imputed
    row = case_at(research.build_cases(frame, horizon_months=12), "2010-01-01")
    assert not row.target_is_observed
    assert pd.isna(row.target_value)
    assert not row.reference_eligible


@pytest.mark.parametrize("depth", [np.nan, np.inf, -np.inf])
def test_nonfinite_observed_depths_are_not_labels(depth):
    frame = monthly_frame(districts=("A",))
    frame.loc[frame.date == pd.Timestamp("2011-01-01"), "gwl_current"] = depth
    row = case_at(research.build_cases(frame, horizon_months=12), "2010-01-01")
    assert not row.target_is_observed
    assert pd.isna(row.target_value)


@pytest.mark.parametrize("flag", ["is_observed", "is_imputed"])
def test_both_provenance_flags_are_required(flag):
    with pytest.raises(ValueError):
        research.build_cases(monthly_frame().drop(columns=flag), horizon_months=12)


def test_conflicting_provenance_cannot_silently_become_a_label():
    frame = monthly_frame()
    frame.loc[0, ["is_observed", "is_imputed"]] = [True, True]
    with pytest.raises(ValueError):
        research.build_cases(frame, horizon_months=12)


@pytest.mark.parametrize("defect", ["duplicate", "midmonth", "missing_date"])
def test_ambiguous_calendar_keys_are_rejected(defect):
    frame = monthly_frame()
    if defect == "duplicate":
        frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    elif defect == "midmonth":
        frame.loc[0, "date"] = pd.Timestamp("2004-01-15")
    else:
        frame.loc[0, "date"] = pd.NaT
    with pytest.raises(ValueError):
        research.build_cases(frame, horizon_months=12)


def test_annual_seasonal_naive_is_persistence_on_identical_observations():
    cases = research.build_cases(monthly_frame(), horizon_months=12)
    paired = cases.loc[cases.reference_eligible]
    assert len(paired)
    assert (paired.seasonal_date == paired.date).all()
    np.testing.assert_array_equal(paired.seasonal_naive, paired.gwl_current)
    assert cases.case_id.is_unique
    assert cases.case_id.str.endswith("|12").all()


def test_unobserved_origin_is_not_an_annual_reference():
    frame = monthly_frame(districts=("A",))
    frame.loc[frame.date == pd.Timestamp("2010-01-01"),
              ["is_observed", "is_imputed", "months_since_observation"]] = [False, True, 1]
    row = case_at(research.build_cases(frame, horizon_months=12), "2010-01-01")
    assert row.target_is_observed
    assert not row.origin_is_observed and not row.reference_eligible
    assert pd.isna(row.seasonal_naive)


def test_twelve_month_fold_has_full_embargo_and_observed_targets():
    cases = research.build_cases(monthly_frame(), horizon_months=12)
    training, evaluated, metadata = research.split_fold(cases, 2013, horizon_months=12)
    assert len(training) and len(evaluated) and metadata
    assert training.target_date.max() == pd.Timestamp("2010-12-01")
    assert training.target_date.max() <= pd.Timestamp("2010-12-31")
    assert evaluated.date.min() == pd.Timestamp("2012-01-01")
    assert evaluated.target_date.min() == pd.Timestamp("2013-01-01")
    assert evaluated.target_date.max() == pd.Timestamp("2013-12-01")
    assert (training.target_is_observed & np.isfinite(training.target_value)).all()
    assert evaluated.reference_eligible.all()
    assert set(training.case_id).isdisjoint(evaluated.case_id)
    assert not training.case_id.isin(evaluated.case_id).any()


def test_training_imputed_origins_are_bounded_and_targets_stay_observed():
    frame = monthly_frame(districts=("A",))
    for month, age in [("2009-01-01", 3), ("2009-02-01", 4)]:
        frame.loc[frame.date == pd.Timestamp(month),
                  ["is_observed", "is_imputed", "months_since_observation"]] = [False, True, age]
    training, _, _ = research.split_fold(research.build_cases(frame, horizon_months=12),
                                         2013, horizon_months=12)
    assert pd.Timestamp("2009-01-01") in set(training.date)
    assert pd.Timestamp("2009-02-01") not in set(training.date)
    assert training.target_is_observed.all()


def test_default_six_month_behavior_and_case_identity_are_unchanged():
    frame = monthly_frame()
    default = research.build_cases(frame)
    explicit = research.build_cases(frame, horizon_months=6)
    pd.testing.assert_frame_equal(default, explicit)
    assert (default.target_date == default.date + pd.DateOffset(months=6)).all()
    assert (default.seasonal_date == default.date - pd.DateOffset(months=6)).all()
    assert default.case_id.str.endswith("|6").all()
    default_split = research.split_fold(default, 2013)
    explicit_split = research.split_fold(explicit, 2013, horizon_months=6)
    for one, two in zip(default_split[:2], explicit_split[:2]):
        pd.testing.assert_frame_equal(one, two)
    assert default_split[2] == explicit_split[2]


def test_future_values_cannot_change_an_earlier_fold():
    first = monthly_frame()
    changed = first.copy()
    later = changed.date >= pd.Timestamp("2014-01-01")
    changed.loc[later, ["gwl_current", "rainfall_current"]] = [80000., 9e8]
    changed.loc[later, ["is_observed", "is_imputed"]] = [False, True]
    first_split = research.split_fold(research.build_cases(first, horizon_months=12),
                                      2013, horizon_months=12)
    changed_split = research.split_fold(research.build_cases(changed, horizon_months=12),
                                        2013, horizon_months=12)
    for one, two in zip(first_split[:2], changed_split[:2]):
        pd.testing.assert_frame_equal(one, two)
    assert first_split[2] == changed_split[2]


def test_shuffled_source_rows_cannot_change_case_identity_or_labels():
    frame = monthly_frame()
    one = research.build_cases(frame, horizon_months=12).sort_values("case_id").reset_index(drop=True)
    two = research.build_cases(frame.sample(frac=1., random_state=17), horizon_months=12)
    two = two.sort_values("case_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(one, two)


FEATURES = ["gwl_current", "rainfall_current"]
PROTOCOL_SHA256 = "a" * 64


def research_card(horizon=12):
    schema = json.dumps(FEATURES, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "research_schema_version": 1,
        "research_only": True,
        "allowed_use": "historical_research_only",
        "family": "linear_regression",
        "horizon_months": horizon,
        "embargo_months": horizon,
        "features": FEATURES.copy(),
        "feature_schema_sha256": hashlib.sha256(schema.encode()).hexdigest(),
        "units": "m_bgl",
        "protocol_sha256": PROTOCOL_SHA256,
        "train_target_cutoff": "2010-12-31",
        "max_train_target_date": "2010-12-01",
        "max_train_origin": "2009-12-01" if horizon == 12 else "2010-06-01",
    }


@pytest.fixture
def artifact(tmp_path, monkeypatch):
    """A byte-only fake serializer cannot train or load an estimator."""
    monkeypatch.setattr(research, "ROOT", tmp_path)
    monkeypatch.setattr(research, "RESEARCH_ROOT", tmp_path / "reports" / "candidates")
    calls = {"dump": [], "load": []}

    def dump(model, filename, *args, **kwargs):
        path = Path(getattr(filename, "name", filename))
        calls["dump"].append(path)
        if hasattr(filename, "write"):
            filename.write(b"SYNTHETIC TEST ARTIFACT: not a fitted model")
        else:
            with path.open("xb") as stream:
                stream.write(b"SYNTHETIC TEST ARTIFACT: not a fitted model")
        return [str(path)]

    def load(filename, *args, **kwargs):
        calls["load"].append(Path(filename))
        return {"synthetic_test_model": True}

    monkeypatch.setattr(joblib, "dump", dump)
    monkeypatch.setattr(joblib, "load", load)
    directory = tmp_path / "reports" / "candidates" / "twelve_month_horizon_fixture" / "models"
    directory.mkdir(parents=True)
    card_path = research.save_research_model(object(), research_card(), directory, "fixture")
    return Path(card_path), calls


def test_research_card_declares_explicit_horizon_and_provenance():
    card = research_card()
    research.validate_card(card, 12, PROTOCOL_SHA256, FEATURES)
    assert card == research_card()


@pytest.mark.parametrize("field,value", [
    ("research_schema_version", 2), ("research_schema_version", True),
    ("research_schema_version", 1.0), ("research_only", False),
    ("allowed_use", "production"), ("horizon_months", 6),
    ("horizon_months", 12.0), ("horizon_months", True),
    ("embargo_months", 6), ("embargo_months", 12.0),
    ("embargo_months", True), ("units", "m"),
    ("protocol_sha256", "b" * 64),
    ("features", list(reversed(FEATURES))),
    ("feature_schema_sha256", "0" * 64),
    ("train_target_cutoff", "not-a-date"),
    ("max_train_target_date", "2011-01-01"),
    ("max_train_target_date", None),
    ("max_train_origin", "2010-01-01"),
    ("max_train_origin", None),
])
def test_invalid_research_metadata_is_rejected(field, value):
    card = research_card()
    card[field] = value
    with pytest.raises(ValueError):
        research.validate_card(card, 12, PROTOCOL_SHA256, FEATURES)


def test_valid_research_artifact_round_trip_uses_only_fake_serializer(artifact):
    card_path, calls = artifact
    model, card = research.load_research_model(card_path, 12, PROTOCOL_SHA256, FEATURES)
    assert model == {"synthetic_test_model": True}
    assert card["horizon_months"] == card["embargo_months"] == 12
    assert card["research_only"] is True
    assert card["allowed_use"] == "historical_research_only"
    assert len(calls["dump"]) == len(calls["load"]) == 1
    assert calls["load"][0].parent == card_path.parent


def test_six_month_card_cannot_load_as_twelve_month_before_deserialization(artifact):
    card_path, calls = artifact
    stored = json.loads(card_path.read_text(encoding="utf-8"))
    stored.update(research_card(horizon=6))
    card_path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(ValueError):
        research.load_research_model(card_path, 12, PROTOCOL_SHA256, FEATURES)
    assert calls["load"] == []


@pytest.mark.parametrize("defect", ["units", "features", "protocol", "model_bytes", "model_hash"])
def test_incompatible_or_revised_artifacts_never_reach_deserializer(artifact, defect):
    card_path, calls = artifact
    card = json.loads(card_path.read_text(encoding="utf-8"))
    if defect == "units":
        card["units"] = "feet"
    elif defect == "features":
        card["features"] = list(reversed(FEATURES))
    elif defect == "protocol":
        card["protocol_sha256"] = "c" * 64
    elif defect == "model_bytes":
        model_path = card_path.parent / card["model_path"]
        model_path.write_bytes(model_path.read_bytes() + b" revised")
    else:
        card["model_sha256"] = "0" * 64
    card_path.write_text(json.dumps(card), encoding="utf-8")
    with pytest.raises(ValueError):
        research.load_research_model(card_path, 12, PROTOCOL_SHA256, FEATURES)
    assert calls["load"] == []


def test_artifact_model_path_cannot_escape_its_directory(artifact):
    card_path, calls = artifact
    card = json.loads(card_path.read_text(encoding="utf-8"))
    outside = card_path.parent.parent / "outside.joblib"
    outside.write_bytes(b"SYNTHETIC outside artifact")
    card["model_path"] = "../outside.joblib"
    card["model_sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
    card_path.write_text(json.dumps(card), encoding="utf-8")
    with pytest.raises(ValueError):
        research.load_research_model(card_path, 12, PROTOCOL_SHA256, FEATURES)
    assert calls["load"] == []


def test_artifact_cannot_load_from_active_model_namespace(artifact, tmp_path):
    card_path, calls = artifact
    outside = tmp_path / "models" / "checkpoints"
    outside.mkdir(parents=True)
    copied = outside / card_path.name
    copied.write_bytes(card_path.read_bytes())
    stored = json.loads(card_path.read_text(encoding="utf-8"))
    (outside / stored["model_path"]).write_bytes((card_path.parent / stored["model_path"]).read_bytes())
    with pytest.raises(ValueError):
        research.load_research_model(copied, 12, PROTOCOL_SHA256, FEATURES)
    assert calls["load"] == []


def test_saving_again_cannot_replace_an_existing_research_model_or_card(artifact):
    card_path, calls = artifact
    before = {path.name: path.read_bytes() for path in card_path.parent.iterdir() if path.is_file()}
    with pytest.raises((FileExistsError, ValueError)):
        research.save_research_model(object(), research_card(), card_path.parent, "fixture")
    after = {path.name: path.read_bytes() for path in card_path.parent.iterdir() if path.is_file()}
    assert before == after
    assert len(calls["dump"]) == 1


def test_model_stem_cannot_escape_candidate_directory(artifact):
    card_path, calls = artifact
    with pytest.raises(ValueError):
        research.save_research_model(object(), research_card(), card_path.parent, "../escaped")
    assert len(calls["dump"]) == 1
