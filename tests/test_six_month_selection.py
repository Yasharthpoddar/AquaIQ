"""Observed labels, temporal isolation and paired model selection contracts."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from models import six_month_selection as experiment
from models import xgboost_model as forecast


def physical_frame(start="2006-01-01", end="2012-12-01", districts=("A", "B")):
    panels = []
    for number, district in enumerate(districts):
        dates = pd.date_range(start, end, freq="MS")
        depth = 8. + number * 5 + np.arange(len(dates)) * .1
        frame = pd.DataFrame({
            "district_id": district, "date": dates, "gwl_current": depth,
            "gwl_lag_3mo": pd.Series(depth).shift(3),
            "gwl_lag_6mo": pd.Series(depth).shift(6),
            "rainfall_current": 30. + dates.month * 2,
            "rainfall_3mo_avg": 40., "monsoon_deficit_pct": 1.,
            "temperature": 24., "evapotranspiration": 45.,
            "water_balance_proxy": 5., "crop_season_flag": "Rabi",
            "is_observed": True, "is_imputed": False,
            "months_since_observation": 0,
            "feature_generation": "physical-selection-fixture",
        })
        panels.append(frame)
    result = pd.concat(panels, ignore_index=True)
    result.attrs.update(feature_generation_id="physical-selection-fixture",
                        data_source="observed-schema-fixture")
    return result


def specification(**changes):
    return {"train_target_cutoff": "2008-12-31",
            "evaluation_origin_start": "2009-07-01",
            "evaluation_target_start": "2010-01-01",
            "evaluation_target_end": "2010-12-31", **changes}


def candidate(**changes):
    return {"family": "ridge", "parameters": {"alpha": 10.},
            "target_form": "delta", **changes}


def row_at(frame, origin, district="A"):
    return frame.loc[(frame.district_id == district) &
                     (frame.date == pd.Timestamp(origin))]


def test_target_is_exactly_six_calendar_months_on_an_irregular_panel():
    frame = physical_frame(districts=("A",))
    # With August absent, a row shift would substitute a later observed month.
    frame = frame.loc[frame.date != pd.Timestamp("2010-08-01")].copy()
    cases = experiment.build_cases(frame)
    assert row_at(cases, "2010-02-01").empty
    origin = row_at(cases, "2010-01-01").iloc[0]
    assert origin.target_date == pd.Timestamp("2010-07-01")
    expected = row_at(frame, "2010-07-01").gwl_current.iloc[0]
    assert origin.target_gwl_6mo == expected
    assert (cases.target_date == cases.date + pd.DateOffset(months=6)).all()


@pytest.mark.parametrize("flag", [False, "False", "unknown", None])
def test_only_explicitly_observed_target_flags_create_labels(flag):
    frame = physical_frame(districts=("A",))
    frame["is_observed"] = frame.is_observed.astype(object)
    affected = frame.date == pd.Timestamp("2010-07-01")
    frame.loc[affected, "is_observed"] = flag
    frame.loc[affected, "is_imputed"] = True
    # The depth remains finite; finite carried-forward values are not labels.
    cases = experiment.build_cases(frame)
    assert row_at(cases, "2010-01-01").empty
    assert cases.target_is_observed.all()


def test_filled_origin_is_separate_from_observed_primary_cohort():
    frame = physical_frame(districts=("A",))
    filled = frame.date == pd.Timestamp("2009-07-01")
    frame.loc[filled, ["is_observed", "is_imputed"]] = [False, True]
    frame.loc[filled, "months_since_observation"] = 1
    primary = experiment.build_cases(frame)
    secondary = experiment.build_cases(frame, origin_policy="causal")
    assert row_at(primary, "2009-07-01").empty
    assert len(row_at(secondary, "2009-07-01")) == 1
    assert not row_at(secondary, "2009-07-01").is_observed.iloc[0]
    assert set(primary.case_id).issubset(set(secondary.case_id))


def test_seasonal_baseline_requires_exact_observed_target_month_one_year_before():
    frame = physical_frame(districts=("A",))
    # For a January 2010 origin the July 2010 target uses July 2009 only.
    affected = frame.date == pd.Timestamp("2009-07-01")
    frame.loc[affected, ["is_observed", "is_imputed"]] = [False, True]
    cases = experiment.build_cases(frame)
    assert pd.isna(row_at(cases, "2010-01-01").seasonal_naive_6mo.iloc[0])
    exact = row_at(cases, "2010-02-01").iloc[0]
    assert exact.seasonal_naive_6mo == row_at(frame, "2009-08-01").gwl_current.iloc[0]
    # A missing seasonal baseline removes only evaluation coverage, not training.
    training, evaluation = experiment.window_split(cases, specification())
    assert training.seasonal_naive_6mo.isna().any()
    assert evaluation.seasonal_naive_6mo.notna().all()
    assert row_at(evaluation, "2010-01-01").empty


def test_window_has_six_full_embargo_months_and_disjoint_target_dates():
    cases = experiment.build_cases(physical_frame())
    training, evaluation = experiment.window_split(cases, specification())
    assert len(training) and len(evaluation)
    assert training.target_date.max() <= pd.Timestamp("2008-12-31")
    assert evaluation.date.min() >= pd.Timestamp("2009-07-01")
    assert evaluation.target_date.min() >= pd.Timestamp("2010-01-01")
    assert evaluation.target_date.max() <= pd.Timestamp("2010-12-31")
    assert set(training.case_id).isdisjoint(evaluation.case_id)
    assert training.target_is_observed.all() and evaluation.target_is_observed.all()
    assert evaluation.seasonal_naive_6mo.notna().all()


def test_window_rejects_one_month_short_embargo():
    cases = experiment.build_cases(physical_frame())
    with pytest.raises(ValueError, match="(?i)embargo"):
        experiment.window_split(cases, specification(evaluation_origin_start="2009-06-01"))


def test_case_identity_is_unique_and_independent_of_input_row_order():
    frame = physical_frame()
    ordered = experiment.build_cases(frame)
    shuffled = experiment.build_cases(frame.sample(frac=1, random_state=17))
    assert ordered.case_id.is_unique
    columns = ["case_id", "district_id", "date", "target_date", "target_gwl_6mo",
               "seasonal_naive_6mo"]
    pd.testing.assert_frame_equal(ordered[columns].sort_values("case_id").reset_index(drop=True),
                                  shuffled[columns].sort_values("case_id").reset_index(drop=True))


def test_later_labels_cannot_enter_a_validation_window_or_change_training():
    first = physical_frame()
    changed = first.copy()
    later = changed.date >= "2011-01-01"
    changed.loc[later, ["gwl_current", "rainfall_current", "temperature"]] = [8000., 90000., -80.]
    train1, evaluation1 = experiment.window_split(experiment.build_cases(first), specification())
    train2, evaluation2 = experiment.window_split(experiment.build_cases(changed), specification())
    pd.testing.assert_frame_equal(train1, train2)
    pd.testing.assert_frame_equal(evaluation1, evaluation2)


def test_full_validation_selection_cannot_use_post_2018_features_or_labels(tmp_path, monkeypatch):
    original = physical_frame(end="2022-12-01")
    revised = original.copy()
    held_out = revised.date >= "2019-01-01"
    revised.loc[held_out, ["gwl_current", "rainfall_current", "temperature"]] = [90000., 8e8, -80.]
    revised.loc[held_out, ["is_observed", "is_imputed"]] = [False, False]
    monkeypatch.setattr(experiment, "FOLDS", (specification(fold="fixture-validation"),))
    monkeypatch.setattr(experiment, "FAMILIES", ("ridge",))
    plan = {"candidates": [candidate(candidate_id="ridge-fixture-one", parameters={"alpha": .1}),
                            candidate(candidate_id="ridge-fixture-two", parameters={"alpha": 1.})]}
    training_calls = []

    class CheapCandidate:
        def __init__(self, parameters):
            self.parameters = parameters

        def fit(self, inputs, labels):
            training_calls.append((inputs.copy(), np.asarray(labels).copy()))
            self.mean = np.mean(labels)
            return self

        def predict(self, inputs):
            return np.full(len(inputs), self.mean + self.parameters["alpha"])

    monkeypatch.setattr(experiment, "make_estimator", lambda family, parameters: CheapCandidate(parameters))
    real_build_cases = experiment.build_cases
    checked_frames = []

    def development_only(frame, *args, **kwargs):
        checked_frames.append(frame.copy())
        assert frame.date.max() <= pd.Timestamp("2018-12-31")
        return real_build_cases(frame, *args, **kwargs)

    monkeypatch.setattr(experiment, "build_cases", development_only)
    locks = []
    for label, frame in (("original", original), ("mutated", revised)):
        output = tmp_path / label
        output.mkdir()
        experiment.write_once(output / "protocol.json", {"fixture_protocol": 1})
        locks.append(experiment.validate(frame, output, plan))
    assert len(checked_frames) == 2
    pd.testing.assert_frame_equal(checked_frames[0], checked_frames[1])
    for key in ("selected_ml", "selected_by_family", "ranking", "validation_best_including_baselines"):
        assert locks[0][key] == locks[1][key]
    assert len(training_calls) == 4
    for first, second in zip(training_calls[:2], training_calls[2:]):
        pd.testing.assert_frame_equal(first[0], second[0])
        np.testing.assert_array_equal(first[1], second[1])


def test_origin_features_and_baselines_do_not_use_later_rows():
    first = physical_frame()
    changed = first.copy()
    later = changed.date > "2010-01-01"
    changed.loc[later, ["gwl_current", "rainfall_current", "temperature"]] = [8000., 90000., -80.]
    one = row_at(experiment.build_cases(first), "2010-01-01").iloc[0]
    two = row_at(experiment.build_cases(changed), "2010-01-01").iloc[0]
    inputs = forecast.CANONICAL_FEATURE_COLS + ["origin_month_sin", "origin_month_cos",
                                               "seasonal_naive_6mo", "case_id"]
    pd.testing.assert_series_equal(one[inputs], two[inputs])
    assert one.target_gwl_6mo != two.target_gwl_6mo


@pytest.mark.parametrize("family", ["ridge", "random_forest"])
def test_imputation_and_scaling_statistics_fit_only_training_rows(family):
    cases = experiment.build_cases(physical_frame())
    training, evaluation = experiment.window_split(cases, specification())
    training = training.copy()
    training.loc[training.index[::3], "rainfall_current"] = np.nan
    parameters = {"alpha": 10.} if family == "ridge" else {
        "n_estimators": 3, "max_depth": 2, "random_state": 42, "n_jobs": 1}
    model = experiment.fit_candidate(training, candidate(family=family, parameters=parameters))
    assert isinstance(model, Pipeline)
    imputer = next(step for _, step in model.steps if isinstance(step, SimpleImputer))
    feature_index = list(model.feature_names_in_).index("rainfall_current")
    expected = training.rainfall_current.median()
    assert imputer.statistics_[feature_index] == pytest.approx(expected)
    before = imputer.statistics_.copy()
    extreme = evaluation.copy()
    extreme["rainfall_current"] = 1e12
    experiment.predict_candidate(model, extreme, candidate(family=family, parameters=parameters))
    np.testing.assert_array_equal(imputer.statistics_, before)
    if family == "ridge":
        scaler = next(step for _, step in model.steps if isinstance(step, StandardScaler))
        assert scaler.n_samples_seen_ == len(training)


@pytest.mark.parametrize("target_form", ["absolute", "delta"])
def test_target_form_fit_and_prediction_round_trip(monkeypatch, target_form):
    cases = experiment.build_cases(physical_frame())
    training, evaluation = experiment.window_split(cases, specification())
    captured = {}

    class Recorder:
        def fit(self, inputs, labels):
            captured["inputs"] = inputs.copy()
            captured["labels"] = np.asarray(labels).copy()
            return self

        def predict(self, inputs):
            return np.full(len(inputs), .75)

    monkeypatch.setattr(experiment, "make_estimator", lambda family, parameters: Recorder())
    spec = candidate(target_form=target_form)
    model = experiment.fit_candidate(training, spec)
    offset = training.gwl_current.to_numpy() if target_form == "delta" else 0.
    np.testing.assert_allclose(captured["labels"], training.target_gwl_6mo.to_numpy() - offset)
    prediction = experiment.predict_candidate(model, evaluation, spec)
    expected = evaluation.gwl_current.to_numpy() + .75 if target_form == "delta" else np.full(len(evaluation), .75)
    np.testing.assert_allclose(prediction, expected)
    assert list(captured["inputs"].columns) == forecast.CANONICAL_FEATURE_COLS + [
        "origin_month_sin", "origin_month_cos"]


def test_histogram_boosting_has_no_random_internal_validation_split():
    model = experiment.make_estimator("hist_gradient_boosting", {"max_iter": 3})
    steps = [step for _, step in model.steps] if isinstance(model, Pipeline) else [model]
    booster = next(step for step in steps if isinstance(step, HistGradientBoostingRegressor))
    assert booster.early_stopping is False


def prediction_table():
    return pd.DataFrame({"case_id": ["a", "b", "c", "d"],
        "district_id": ["A", "A", "B", "B"],
        "date": pd.to_datetime(["2009-07-01", "2009-08-01", "2009-07-01", "2009-08-01"]),
        "origin_date": pd.to_datetime(["2009-07-01", "2009-08-01", "2009-07-01", "2009-08-01"]),
        "target_date": pd.to_datetime(["2010-01-01", "2010-02-01", "2010-01-01", "2010-02-01"]),
        "horizon_months": 6, "actual": [10., 11., 20., 22.],
        "persistence": [10., 10., 20., 20.], "seasonal_naive": [10., 12., 21., 22.],
        "ridge": [10.5, 10.5, 20.5, 21.5]})


def test_summary_compares_every_model_on_identical_cases_and_reports_breakdowns():
    table = prediction_table()
    names = ["persistence", "seasonal_naive", "ridge"]
    summary = experiment.summarize_cases(table, names)
    assert set(summary["models"]) == set(names)
    assert all(summary["models"][name]["n"] == len(table) for name in names)
    assert set(summary["by_district"]) == {"A", "B"}
    assert set(summary["by_target_year"]) == {"2010"}
    assert set(summary["by_horizon_months"]) == {"6"}
    expected = forecast.metrics(table.actual, table.ridge)
    assert summary["models"]["ridge"] == expected


def test_summary_rejects_nonfinite_predictions_instead_of_changing_comparison_cases():
    table = prediction_table()
    table.loc[0, "ridge"] = np.nan
    with pytest.raises(ValueError, match="(?i)finite|identical|paired"):
        experiment.summarize_cases(table, ["persistence", "seasonal_naive", "ridge"])


def test_summary_undefined_r_squared_is_null():
    table = prediction_table().iloc[:1]
    summary = experiment.summarize_cases(table, ["persistence", "seasonal_naive", "ridge"])
    assert all(value["r2"] is None for value in summary["models"].values())


def test_candidate_output_protects_source_and_other_report_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(experiment, "ROOT", tmp_path)
    accepted = tmp_path / "reports" / "candidates" / "six_month_selection_fixture"
    assert experiment.candidate_output(accepted) == accepted.resolve()
    invalid = [tmp_path / "data" / "candidate", tmp_path / "models" / "candidate",
               tmp_path / "reports" / "audit", tmp_path / "reports" / "candidates" / "other",
               tmp_path / "reports" / "candidates" / "six_month_selection_fixture" / ".." / "other"]
    for path in invalid:
        with pytest.raises(ValueError):
            experiment.candidate_output(path)


def test_candidate_output_rejects_a_symlink_that_escapes_the_candidate_root(tmp_path, monkeypatch):
    monkeypatch.setattr(experiment, "ROOT", tmp_path)
    parent = tmp_path / "reports" / "candidates"
    parent.mkdir(parents=True)
    outside = tmp_path / "source_data"
    outside.mkdir()
    link = parent / "six_month_selection_link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory symlinks needs Windows developer mode or privileges")
    with pytest.raises(ValueError):
        experiment.candidate_output(link / "run")


def test_write_once_refuses_to_overwrite_an_existing_artifact(tmp_path):
    output = tmp_path / "existing_report.json"
    experiment.write_once(output, {"existing": "preserve this report"})
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        experiment.write_once(output, {"replacement": "must not be written"})
    assert output.read_bytes() == original


def test_main_refuses_protected_input_changes_between_validation_and_test(tmp_path, monkeypatch, capsys):
    """A matching protocol alone cannot authorize resuming after input drift."""
    monkeypatch.setattr(experiment, "ROOT", tmp_path)
    output = tmp_path / "reports" / "candidates" / "six_month_selection_fixture" / "experiment"
    output.mkdir(parents=True)
    feature_marker = tmp_path / "data" / "processed" / "features_matrix.csv"
    feature_marker.parent.mkdir(parents=True)
    feature_marker.write_text("synthetic fixture marker only", encoding="utf-8")
    plan = {"version": "fixture-protocol", "selection": "already locked"}
    experiment.write_once(output / "protocol.json", plan)
    experiment.write_once(output / "protected_inputs.json", {"existing_report": "original-sha"})
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    monkeypatch.setattr(experiment, "candidate_output", lambda path: Path(path).resolve())
    monkeypatch.setattr(experiment.source, "load_feature_matrix", lambda: physical_frame())
    monkeypatch.setattr(experiment, "protocol", lambda frame, external_features: plan)
    monkeypatch.setattr(experiment, "protected_snapshot", lambda owned: {"existing_report": "changed-sha"})

    def forbidden(*args, **kwargs):
        pytest.fail("Input drift must be rejected before fitting or final evaluation")

    monkeypatch.setattr(experiment, "validate", forbidden)
    monkeypatch.setattr(experiment, "evaluate_final", forbidden)
    with pytest.raises(SystemExit) as error:
        experiment.main(["--stage", "test", "--output-dir", str(output)])
    assert error.value.code == 2
    assert "changed between stages" in capsys.readouterr().err
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before
