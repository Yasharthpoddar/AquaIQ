"""Fixture-only checks of reserved splits, hidden observations and intervals."""
from dataclasses import asdict
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tested_uncertainty_replay", BASE/"models/uncertainty.py")
u = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = u
spec.loader.exec_module(u)


@pytest.fixture
def protocol():
    return u.TemporalProtocol(fit_start="2002-01-01", fit_end="2010-12-31", development_start="2011-07-01",
        development_end="2011-12-31", calibration_start="2012-01-01", calibration_end="2012-12-31",
        evaluation_start="2013-01-01", evaluation_end="2013-12-31")


@pytest.fixture
def model():
    return {"model_sha256": "verified_fixture_model", "feature_generation_id": "verified_fixture_generation",
            "train_target_cutoff": "2010-12-31"}


@pytest.fixture
def panel(model):
    records = []
    for district in ("A", "B", "C"):
        for index, date in enumerate(pd.date_range("2002-01-01", "2014-01-01", freq="MS")):
            records.append({"district_id": district, "date": date,
                "gwl_current": 5.+index*.01+(district == "B"), "gwl_lag_3mo": 99., "gwl_lag_6mo": 98.,
                "is_observed": True, "is_imputed": False, "rainfall_current": 20.+date.month,
                "rainfall_3mo_avg": 25., "monsoon_deficit_pct": 0., "temperature": 22.,
                "evapotranspiration": 3., "water_balance_proxy": 20., "crop_season_flag": "Rabi"})
    frame = pd.DataFrame(records)
    frame.attrs.update(feature_generation_id=model["feature_generation_id"], data_source="fixture_only")
    return frame


def case(protocol, model, *, split="calibration", district="A", month=1, horizon=1, gap=0,
         source="district_level", predicted=5., actual=6.):
    origin = pd.Timestamp(f"{2012 if split == 'calibration' else 2013}-{month:02d}-01")
    visible = origin-pd.DateOffset(months=gap)
    return {"split": split, "district_id": district, "origin_date": origin.date().isoformat(),
        "target_date": (origin+pd.DateOffset(months=horizon)).date().isoformat(), "horizon_months": horizon,
        "requested_gap_months": gap, "groundwater_visible_through": visible.date().isoformat(),
        "last_observed_date": visible.date().isoformat(), "data_age_months": gap,
        "estimate_type": source, "source_zone": "Z" if source == "zone_fallback" else None,
        "target_basis": "observed_district_depth", "target_is_observed": True,
        "actual_gwl_m_bgl": actual, "predicted_gwl_m_bgl": predicted,
        "model_sha256": model["model_sha256"], "feature_generation_id": model["feature_generation_id"],
        "protocol_sha256": protocol.sha256}


def calibration_cases(protocol, model):
    return [case(protocol, model, district=district, month=month, actual=5.+index)
            for index, (district, month) in enumerate((district, month) for district in ("A", "B", "C") for month in (1, 2, 3))]


@pytest.mark.parametrize("field,value", [("development_start", "2011-06-01"),
    ("fit_start", "2011-01-01"), ("fit_start", "2002-01-02"),
    ("calibration_start", "2011-12-01"), ("evaluation_start", "2012-12-01"),
    ("development_start", "2011-07-02"), ("evaluation_end", "2013-01-01"),
    ("fit_end", "invalid"), ("fit_end", "2010-12-31T12:00:00"),
    ("fit_end", "2010-12-31T00:00:00Z")])
def test_protocol_rejects_overlap_dates_and_short_embargo(protocol, field, value):
    settings = asdict(protocol)
    settings[field] = value
    with pytest.raises(ValueError):
        u.TemporalProtocol(**settings)


def test_protocol_model_cutoff_and_identity(protocol, model):
    protocol.validate_model(model)
    for values in ({**model, "train_target_cutoff": "2011-01-01"}, {**model, "model_sha256": ""}, {}):
        with pytest.raises(ValueError):
            protocol.validate_model(values)


@pytest.mark.parametrize("age,expected", [(0, "0"), (1, "1_3"), (3, "1_3"), (4, "4_12"),
    (12, "4_12"), (13, "13_36"), (36, "13_36"), (37, "37_plus")])
def test_age_bins(age, expected):
    assert u.age_bin(age) == expected


@pytest.mark.parametrize("age", [-1, True, np.nan, 2.5, "bad"])
def test_age_requires_nonnegative_integer(age):
    with pytest.raises(ValueError):
        u.age_bin(age)


def test_snapshot_hides_all_peers_rebuilds_lags_and_never_mutates(panel):
    before = panel.copy(deep=True)
    snapshot, visible = u.groundwater_snapshot(panel, "2013-01-01", 6)
    assert visible == pd.Timestamp("2012-07-01")
    assert snapshot.date.max() == pd.Timestamp("2013-01-01")
    assert not snapshot.loc[snapshot.date > visible, "is_observed"].any()
    assert snapshot.loc[snapshot.date > pd.Timestamp("2012-10-01"), "gwl_current"].isna().all()
    assert (snapshot.loc[snapshot.date == pd.Timestamp("2012-08-01"), "gwl_current"] < 10).all()
    assert not (snapshot.gwl_lag_3mo == 99).any()
    assert not (snapshot.gwl_lag_6mo == 98).any()
    pd.testing.assert_frame_equal(panel, before)


def test_snapshot_lag_is_calendar_based_not_row_offset(panel):
    frame = panel.loc[~((panel.district_id == "A") & (panel.date == pd.Timestamp("2012-12-01")))].copy()
    snapshot, _ = u.groundwater_snapshot(frame, "2013-01-01", 0)
    row = snapshot.loc[(snapshot.district_id == "A") & (snapshot.date == pd.Timestamp("2013-01-01"))].iloc[0]
    expected = frame.loc[(frame.district_id == "A") & (frame.date == pd.Timestamp("2012-10-01")), "gwl_current"].iloc[0]
    assert row.gwl_lag_3mo == expected


def test_prepare_frame_explicit_flags_duplicates_and_observed_depth(panel):
    assert len(u.prepare_replay_frame(panel)) == len(panel)
    bads = [pd.concat([panel, panel.iloc[:1]], ignore_index=True), panel.assign(is_observed="unknown"),
            panel.assign(gwl_current=-1), panel.assign(date=pd.NaT)]
    for bad in bads:
        with pytest.raises(ValueError):
            u.prepare_replay_frame(bad)


def test_zone_provider_uses_observed_peer_mean_and_skips_no_zone(panel, model):
    sparse = panel.copy()
    sparse.loc[(sparse.district_id == "A") & (sparse.date < "2012-01-01"), "is_observed"] = False
    snapshot, _ = u.groundwater_snapshot(sparse, "2012-03-01", 0)
    provider = u.in_memory_evidence_provider(generation=model["feature_generation_id"],
                                            zones={"A": "Z", "B": "Z", "C": "Z"})
    evidence = provider("A", "2012-03-31", snapshot)
    assert evidence["estimate_type"] == "zone_fallback"
    assert evidence["zone"] == "Z"
    latest = evidence["history"].iloc[-1]
    peers = snapshot.loc[(snapshot.date == latest.date) & snapshot.is_observed, "gwl_current"]
    assert latest.gwl_current == pytest.approx(peers.mean())
    empty = u.in_memory_evidence_provider(generation=model["feature_generation_id"])("A", "2012-03-31", snapshot)
    assert empty["estimate_type"] == "insufficient_data"


def fake_predictor(evidence):
    origin = pd.Timestamp(evidence["as_of"]).to_period("M").to_timestamp()
    if evidence["estimate_type"] == "insufficient_data":
        return {"status": "insufficient_data", "forecast": []}
    depth = float(evidence["history"].gwl_current.iloc[-1])
    return {"status": "projection", "forecast": [
        {"date": (origin+pd.DateOffset(months=h)).date().isoformat(), "predicted_gwl": depth+h*.01}
        for h in range(1, 7)]}


def test_replay_joins_only_observed_labels_after_prediction_and_records_gaps(panel, protocol, model):
    provider = u.in_memory_evidence_provider(generation=model["feature_generation_id"])
    seen = []
    def inspect(evidence):
        assert evidence["frame"].date.max() <= evidence["as_of"]
        seen.append(evidence["history"].date.max())
        return fake_predictor(evidence)
    report = u.replay_forecasts(panel, protocol, model, evidence_provider=provider, predictor=inspect,
                                gaps=(0, 12), district_ids=["A"])
    assert report["cases"] and seen
    for record in report["cases"]:
        assert record["data_age_months"] == record["requested_gap_months"]
        assert record["target_is_observed"] is True
        assert pd.Timestamp(record["target_date"]) > pd.Timestamp(record["origin_date"])
    assert report["production_changes_made"] is False
    assert report["current_period_accuracy_established"] is False


def test_replay_zone_predictions_are_evaluated_against_district_truth(panel, protocol, model):
    panel.loc[(panel.district_id == "A") & (panel.date < "2012-01-01"), "is_observed"] = False
    provider = u.in_memory_evidence_provider(generation=model["feature_generation_id"],
                                            zones={"A": "Z", "B": "Z", "C": "Z"})
    report = u.replay_forecasts(panel, protocol, model, evidence_provider=provider, predictor=fake_predictor,
                                gaps=(3,), splits=("calibration",), district_ids=["A"])
    assert report["cases"]
    assert {row["estimate_type"] for row in report["cases"]} == {"zone_fallback"}
    for row in report["cases"]:
        actual = panel.loc[(panel.district_id == "A") & (panel.date == row["target_date"]), "gwl_current"].iloc[0]
        assert row["actual_gwl_m_bgl"] == actual


def test_replay_rejects_evidence_leak_and_bad_predictions(panel, protocol, model):
    base = u.in_memory_evidence_provider(generation=model["feature_generation_id"])
    def leaking(district, as_of, snapshot):
        evidence = base(district, as_of, snapshot)
        evidence["history"] = panel.loc[panel.district_id == district].copy()
        return evidence
    with pytest.raises(ValueError, match="leaked"):
        u.replay_forecasts(panel, protocol, model, evidence_provider=leaking, predictor=fake_predictor, gaps=(12,), district_ids=["A"])
    def frame_leak(district, as_of, snapshot):
        evidence = base(district, as_of, snapshot)
        evidence["frame"].loc[evidence["frame"].date == pd.Timestamp(as_of).to_period("M").to_timestamp(), "is_observed"] = True
        return evidence
    with pytest.raises(ValueError, match="leaked"):
        u.replay_forecasts(panel, protocol, model, evidence_provider=frame_leak, predictor=fake_predictor, gaps=(12,), district_ids=["A"])
    def bad(evidence):
        result = fake_predictor(evidence)
        result["forecast"][0]["predicted_gwl"] = np.nan
        return result
    with pytest.raises(ValueError, match="six finite"):
        u.replay_forecasts(panel, protocol, model, evidence_provider=base, predictor=bad, gaps=(0,), district_ids=["A"])


def test_replay_skips_unobserved_targets(panel, protocol, model):
    panel.loc[(panel.district_id == "A") & (panel.date >= "2012-01-01"), "is_observed"] = False
    report = u.replay_forecasts(panel, protocol, model,
        evidence_provider=u.in_memory_evidence_provider(generation=model["feature_generation_id"]),
        predictor=fake_predictor, gaps=(0,), district_ids=["A"])
    assert report["cases"] == []
    assert report["summary"]["n"] == 0


@pytest.mark.parametrize("field,value", [("horizon_months", 7), ("horizon_months", 1.5),
    ("actual_gwl_m_bgl", np.inf), ("predicted_gwl_m_bgl", -1), ("target_is_observed", False),
    ("target_basis", "zone_mean"), ("data_age_months", 2), ("estimate_type", "invented"),
    ("split", "development"), ("model_sha256", "another"), ("feature_generation_id", "other"),
    ("protocol_sha256", "other"), ("origin_date", "2011-12-01"), ("target_date", "2012-03-01"),
    ("last_observed_date", "2012-02-01"), ("district_id", "")])
def test_calibration_rejects_invalid_or_leaking_cases(protocol, model, field, value):
    row = case(protocol, model)
    row[field] = value
    with pytest.raises(ValueError):
        u.fit_intervals([row], protocol, model)


def test_duplicate_cases_cannot_inflate_support(protocol, model):
    row = case(protocol, model)
    with pytest.raises(ValueError, match="Duplicate"):
        u.fit_intervals([row, row], protocol, model)


def test_rank_uses_calibration_only_not_later_extreme_values(protocol, model):
    rows = calibration_cases(protocol, model)
    artifact = u.fit_intervals(rows, protocol, model, alpha=.1, min_cases=9, min_origins=3, min_districts=3)
    group = artifact["groups"]["h1|district_level|age_0"]
    assert group["rank"] == 9
    assert group["radius_m"] == 8.
    before = u._hash(artifact)
    heldout = [case(protocol, model, split="evaluation", actual=10000.)]
    evaluated = u.evaluate_intervals(heldout, artifact, protocol, model)
    assert evaluated["empirical_coverage"] == 0.
    assert artifact["groups"]["h1|district_level|age_0"]["radius_m"] == 8.
    assert u._hash(artifact) == before


def test_sparse_groups_and_unavailable_finite_rank_never_borrow_radii(protocol, model):
    rows = calibration_cases(protocol, model)
    rows += [case(protocol, model, source="zone_fallback", gap=12)]
    artifact = u.fit_intervals(rows, protocol, model, min_cases=9, min_origins=3, min_districts=3)
    assert artifact["groups"]['h1|zone_fallback|zone="Z"|age_4_12']["status"] == "uncertainty_not_established"
    one = u.fit_intervals([case(protocol, model)], protocol, model, min_cases=1, min_origins=1, min_districts=1)
    assert one["groups"]["h1|district_level|age_0"]["radius_m"] is None
    assert "finite_sample_rank_unavailable" in one["groups"]["h1|district_level|age_0"]["reasons"]
    unsupported = [case(protocol, model, split="evaluation", gap=37, source="zone_fallback")]
    result = u.evaluate_intervals(unsupported, artifact, protocol, model)
    assert result["supported_n"] == 0
    assert result["empirical_coverage"] is None


def test_lower_bound_clips_to_physical_zero_and_reports_width(protocol, model):
    artifact = u.fit_intervals(calibration_cases(protocol, model), protocol, model,
                              min_cases=9, min_origins=3, min_districts=3)
    result = u.evaluate_intervals([case(protocol, model, split="evaluation", predicted=1., actual=0.)], artifact, protocol, model)
    assert result["cases"][0]["lower_m_bgl"] == 0.
    assert result["mean_width_m"] == 9.
    assert result["empirical_coverage"] == 1.
    assert result["sufficient_for_operational_use"] is False


def test_interval_identity_and_invalid_radius_rejected(protocol, model):
    artifact = u.fit_intervals(calibration_cases(protocol, model), protocol, model,
                              min_cases=9, min_origins=3, min_districts=3)
    evaluation = [case(protocol, model, split="evaluation")]
    with pytest.raises(ValueError, match="identity"):
        u.evaluate_intervals(evaluation, {**artifact, "protocol_sha256": "different"}, protocol, model)
    artifact["groups"]["h1|district_level|age_0"]["radius_m"] = float("inf")
    with pytest.raises(ValueError, match="invalid radius"):
        u.evaluate_intervals(evaluation, artifact, protocol, model)


def test_fallback_zones_never_borrow_calibration_counts_or_radii(protocol, model):
    dense = [{**row, "estimate_type": "zone_fallback", "source_zone": "Dense|zone"}
             for row in calibration_cases(protocol, model)]
    sparse = [{**case(protocol, model, district="D", source="zone_fallback", actual=100.), "source_zone": "Sparse zone"}]
    artifact = u.fit_intervals(dense+sparse, protocol, model, min_cases=9, min_origins=3, min_districts=3)
    assert artifact["version"] == "1.1-gap-source-zone-forecast-replay"
    assert artifact["groups"]['h1|zone_fallback|zone="Dense|zone"|age_0']["radius_m"] == 8.
    assert artifact["groups"]['h1|zone_fallback|zone="Sparse zone"|age_0']["radius_m"] is None
    cases = [{**case(protocol, model, split="evaluation", source="zone_fallback"), "source_zone": "Unseen zone"}]
    assert u.evaluate_intervals(cases, artifact, protocol, model)["unsupported_n"] == 1
    with pytest.raises(ValueError, match="source zone"):
        u.fit_intervals([{**dense[0], "source_zone": " "}], protocol, model)


def test_replay_summary_compares_only_present_valid_stale_depth_baselines(protocol, model):
    row = {**case(protocol, model, actual=8., predicted=5.), "last_observed_gwl_m_bgl": 7.}
    summary = u.summarize_errors([row, case(protocol, model, month=2)])
    assert summary["persistence_paired_n"] == 1
    assert summary["forecast_paired_rmse_m"] == 3.
    assert summary["persistence_paired_rmse_m"] == 1.
    for bad in (-1, float("nan"), True):
        with pytest.raises(ValueError):
            u.validated_cases([{**row, "last_observed_gwl_m_bgl": bad}], protocol, "calibration", model)


def test_full_serving_function_replays_estimated_current_depth_and_weather(panel, protocol, model, monkeypatch):
    from models import climate_forecast as climate
    class DeltaModel:
        def predict(self, rows):
            assert list(rows.columns) == climate.FEATURES
            assert np.isfinite(rows.target_rainfall).all()
            return np.arange(1, 7, dtype=float)*.1
    card = {**model, "validation_assessment": {"status": "fixture_only"}}
    monkeypatch.setattr(climate, "load_bundle", lambda **kwargs: (DeltaModel(), card))
    provider = u.in_memory_evidence_provider(generation=model["feature_generation_id"])
    short = u.TemporalProtocol(**{**asdict(protocol), "calibration_end": "2012-03-31"})
    report = u.replay_forecasts(panel, short, model, evidence_provider=provider,
        predictor=climate.forecast_from_evidence, gaps=(12,), splits=("calibration",), district_ids=["A"])
    assert report["cases"]
    assert {row["data_age_months"] for row in report["cases"]} == {12}
    assert all(row["predicted_gwl_m_bgl"] > 0 for row in report["cases"])
    # The same complete serving path is exercised on a sparse district's zone
    # evidence, while scoring its actual district measurement as the target.
    panel.loc[(panel.district_id == "A") & (panel.date < "2012-01-01"), "is_observed"] = False
    zone_provider = u.in_memory_evidence_provider(generation=model["feature_generation_id"],
                                                zones={"A": "Z", "B": "Z", "C": "Z"})
    zoned = u.replay_forecasts(panel, short, model, evidence_provider=zone_provider,
        predictor=climate.forecast_from_evidence, gaps=(12,), splits=("calibration",), district_ids=["A"])
    assert zoned["cases"] and {row["estimate_type"] for row in zoned["cases"]} == {"zone_fallback"}
