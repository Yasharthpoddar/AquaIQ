"""Pure runner contracts using synthetic fixtures and forbidden fitting hooks."""
import json

import numpy as np
import pandas as pd
import pytest

from scripts import backtest_twelve_month as runner


@pytest.fixture(autouse=True)
def forbid_fitting_and_runtime_loading(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Pure runner tests must not fit models, load real data or access a database")
    for estimator in (runner.XGBRegressor, runner.LinearRegression,
                      runner.HistGradientBoostingRegressor):
        monkeypatch.setattr(estimator, "fit", forbidden)
    monkeypatch.setattr(runner, "load_frames", forbidden)
    monkeypatch.setattr(runner.six, "get_connection", forbidden)
    monkeypatch.setattr(runner.six, "load_feature_matrix", forbidden)


def prediction_fixture():
    dates = pd.date_range("2013-01-01", periods=18, freq="MS")
    frames = []
    for offset, district in enumerate(("A", "B", "C")):
        actual = np.arange(len(dates)) * .05 + 5. + offset
        frames.append(pd.DataFrame({
            "district_id": district, "target_date": dates,
            "date": dates - pd.DateOffset(months=12),
            "actual": actual, "persistence": actual + .25,
            "candidate": actual + np.linspace(-.5, .5, len(dates)),
        }))
    return pd.concat(frames, ignore_index=True)


def test_bootstrap_baseline_self_difference_is_exactly_zero():
    result = runner.bootstrap(prediction_fixture(), "persistence", repeats=60)
    assert result["districts"] == 3 and result["target_months"] == 18
    for intervals in result["interval_95_percentile"].values():
        for key in ("mae_difference_m", "rmse_difference_m", "bias_difference_m"):
            assert intervals[key] == [0., 0.]
    assert result["seed"] == 42
    assert result["negative_mae_rmse_difference_favors_model"] is True
    assert "no universally favorable direction" in result["bias_difference_interpretation"]


def test_bootstrap_is_deterministic_on_identical_inputs():
    first = runner.bootstrap(prediction_fixture(), "candidate", repeats=60)
    second = runner.bootstrap(prediction_fixture(), "candidate", repeats=60)
    assert first == second


def test_empty_bootstrap_has_no_fabricated_uncertainty():
    result = runner.bootstrap(prediction_fixture().iloc[:0], "candidate", repeats=20)
    assert result["status"] == "no_eligible_cases"
    assert result["districts"] == 0
    assert result["target_months"] == 0
    assert not result.get("interval_95_percentile")


def test_measure_constant_and_singleton_targets_have_no_r_squared():
    constant = runner.measure([7., 7., 7.], [6., 7., 8.])
    assert constant["n"] == 3 and constant["r2"] is None
    assert constant["mae_m"] == pytest.approx(2. / 3.)
    assert constant["rmse_m"] == pytest.approx(np.sqrt(2. / 3.))
    assert constant["bias_m"] == pytest.approx(0.)
    assert runner.measure([7.], [8.])["r2"] is None
    json.dumps(constant, allow_nan=False)


def test_measure_bias_and_large_errors_use_prediction_minus_observation():
    result = runner.measure([1., 2., 3.], [2., 8., 15.])
    assert result["bias_m"] == pytest.approx(19. / 3.)
    assert result["ae_over_5m"] == 2 and result["ae_over_10m"] == 1
    assert result["ae_max_m"] == 12.
    assert result["ae_p50_m"] == 6.


def test_summary_refuses_model_specific_nonfinite_case_dropping():
    table = prediction_fixture()
    table.loc[0, "candidate"] = np.nan
    with pytest.raises(ValueError, match="(?i)nonfinite|common"):
        runner.summarize(table, ["persistence", "candidate"])


def feature_fixture():
    frames = []
    for offset, district in enumerate(("A", "B")):
        dates = pd.date_range("2008-01-01", "2013-12-01", freq="MS")
        data = {name: np.full(len(dates), 1. + offset) for name in runner.HF}
        data.update({
            "district_id": district, "date": dates,
            "gwl_current": 5. + offset + np.arange(len(dates)) * .01,
            "is_observed": True, "is_imputed": False,
            "months_since_observation": 0,
            "panel_sha256": district + "-SYNTHETIC-panel",
            "well_count": 2,
            "first_reported_date": dates,
            "last_reported_date": dates,
        })
        frame = pd.DataFrame(data)
        if district == "B":
            # Twenty-four trainable observed labels, only eleven complete
            # origin feature rows: freeze this exclusion before any fitting.
            unavailable = frame.date.le("2009-12-01") & frame.date.ge("2008-12-01")
            frame.loc[unavailable, "rainfall_current"] = np.nan
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def fold_protocol():
    return {
        "primary_target_range": ["2013-01-01", "2013-06-01"],
        "secondary_target_range": ["2013-07-01", "2013-12-01"],
        "annual_folds": [{"target_year": 2013, "train_target_cutoff": "2010-12-31",
                          "first_permitted_origin": "2012-01-01"}],
    }


def test_common_cohort_excludes_insufficient_ols_support_before_any_fit():
    _, inventory = runner.decorate_cases(feature_fixture(), fold_protocol())
    complete = inventory.loc[inventory.district_id.eq("A")]
    sparse = inventory.loc[inventory.district_id.eq("B")]
    assert len(complete) == len(sparse) == 12
    assert inventory.reference_eligible.all() and inventory.complete_inputs.all()
    assert complete.complete_ols_training_n.eq(24).all()
    assert complete.common_eligible.all()
    assert sparse.complete_ols_training_n.eq(11).all()
    assert not sparse.common_eligible.any()
    assert sparse.exclusion_reasons.str.contains("fewer_than_12_complete_district_training_pairs").all()
    assert inventory.identical_origin_target_panel.all()
    assert inventory.seasonal_naive.eq(inventory.gwl_current).all()


def test_missing_common_input_excludes_the_same_case_for_every_model():
    frame = feature_fixture()
    affected = frame.district_id.eq("A") & frame.date.eq("2012-01-01")
    frame.loc[affected, "rainfall_current"] = np.nan
    _, inventory = runner.decorate_cases(frame, fold_protocol())
    case = inventory.loc[inventory.district_id.eq("A") & inventory.target_date.eq("2013-01-01")].iloc[0]
    assert case.reference_eligible
    assert not case.complete_inputs and not case.common_eligible
    assert "missing_common_model_inputs" in case.exclusion_reasons


def test_fold_must_match_the_frozen_protocol_before_fitting():
    protocol = fold_protocol()
    protocol["annual_folds"][0]["train_target_cutoff"] = "2011-12-31"
    with pytest.raises(ValueError, match="(?i)frozen protocol"):
        runner.decorate_cases(feature_fixture(), protocol)


@pytest.mark.parametrize("relative", [
    "reports/candidates", "reports/other", "data/processed",
    "models/checkpoints", "reports/candidates/other_experiment",
])
def test_output_namespace_rejects_unscoped_or_protected_paths(tmp_path, monkeypatch, relative):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    with pytest.raises(ValueError):
        runner.namespace(tmp_path / relative)


def test_output_namespace_accepts_only_dedicated_research_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    directory = tmp_path / "reports" / "candidates" / "twelve_month_horizon_fixture" / "run"
    assert runner.namespace(directory) == directory.resolve()


@pytest.mark.parametrize("format_name", ["json", "csv"])
def test_duplicate_output_cannot_overwrite_history(tmp_path, format_name):
    path = tmp_path / ("synthetic." + format_name)
    if format_name == "json":
        runner.write_json(path, {"fixture": "original"})
        write_again = lambda: runner.write_json(path, {"fixture": "replacement"})
    else:
        runner.write_csv(path, pd.DataFrame({"fixture": ["original"]}))
        write_again = lambda: runner.write_csv(path, pd.DataFrame({"fixture": ["replacement"]}))
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_again()
    assert path.read_bytes() == before


@pytest.mark.parametrize("defect", ["existing_output", "different_experiment"])
def test_run_output_guard_fails_before_reading_inputs_or_fitting(tmp_path, monkeypatch, defect):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    base = tmp_path / "reports" / "candidates" / "twelve_month_horizon_fixture"
    base.mkdir(parents=True)
    monkeypatch.setattr(runner, "protocol_at", lambda path: ({}, "synthetic-protocol-checksum"))
    if defect == "existing_output":
        output = base / "existing"
        output.mkdir()
        (output / "sentinel.txt").write_text("preserve", encoding="utf-8")
    else:
        output = tmp_path / "reports" / "candidates" / "twelve_month_horizon_other" / "run"
    with pytest.raises(ValueError, match="(?i)new child"):
        runner.run(base / "protocol.json", output)
    if defect == "existing_output":
        assert (output / "sentinel.txt").read_text(encoding="utf-8") == "preserve"
    else:
        assert not output.exists()
