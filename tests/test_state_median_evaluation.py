"""Paired comparison math, chronology, availability and baseline isolation."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from models import state_median_evaluation as evaluation


def metric_rows():
    return pd.DataFrame(dict(state_id=['TN', 'AP'], target_date=['2021-02-01', '2021-03-01'],
        target_eligible=[True, True], actual=[2., 4.], baseline=[3., 6.],
        candidate=[2., 3.], persistence=[1., 2.], target_coverage_ratio=[.5, 1.],
        candidate_reason=[None, None]))


def test_metrics_and_absolute_relative_changes_are_reproducible():
    rows = metric_rows()
    first = evaluation.summarize_cases(rows)
    assert first == evaluation.summarize_cases(rows.copy())
    assert first['baseline']['mae_m'] == 1.5
    assert first['baseline']['rmse_m'] == pytest.approx(np.sqrt(2.5))
    assert first['candidate']['mae_m'] == .5
    assert first['candidate']['rmse_m'] == pytest.approx(np.sqrt(.5))
    assert first['candidate']['bias_m'] == -.5
    assert first['candidate']['directional_accuracy'] == 1.
    assert first['candidate']['directional_n'] == 2
    assert first['candidate']['mean_target_coverage_ratio'] == .75
    assert first['changes']['mae_m']['absolute_change_m'] == -1.
    assert first['changes']['mae_m']['relative_change_pct'] == pytest.approx(-100/1.5)


def test_missing_prediction_is_reported_and_comparison_uses_same_targets():
    rows = metric_rows()
    rows.loc[1, 'candidate'] = np.nan
    rows.loc[1, 'candidate_reason'] = 'insufficient_data'
    report = evaluation.summarize_cases(rows)
    assert report['baseline']['n'] == 2
    assert report['candidate']['n'] == 1
    assert {entry['n'] for entry in report['paired'].values()} == {1}
    assert report['availability']['candidate']['unavailable_cases'] == 1
    assert report['failure_reasons'] == {'insufficient_data': 1}
    assert report['changes']['mae_m']['absolute_change_m'] == -1.


def test_low_coverage_and_missing_targets_never_enter_metrics():
    rows = metric_rows()
    rows.loc[1, 'target_eligible'] = False
    report = evaluation.summarize_cases(rows)
    assert report['eligible_target_cases'] == 1
    assert report['candidate']['n'] == 1
    assert report['candidate']['mae_m'] == 0.


def test_direction_excludes_unchanged_actual_and_empty_metrics_are_null():
    rows = metric_rows()
    rows['actual'] = rows.persistence
    assert evaluation.error_metrics(rows, 'candidate')['directional_n'] == 0
    assert evaluation.error_metrics(rows, 'candidate')['directional_accuracy'] is None
    empty = evaluation.error_metrics(rows.iloc[:0], 'candidate')
    assert empty['n'] == 0 and empty['mae_m'] is None and empty['rmse_m'] is None
    assert evaluation.metric_changes({'mae_m': 0., 'rmse_m': None}, {'mae_m': 0., 'rmse_m': None})['mae_m']['relative_change_pct'] is None


def test_origins_require_twelve_month_embargo_after_both_models():
    candidate = {'train_target_cutoff': '2020-12-31'}
    baseline = {'train_target_cutoff': '2019-12-31'}
    with pytest.raises(ValueError, match='embargo'):
        evaluation.validate_origins(['2021-01-01'], candidate, baseline)
    assert evaluation.validate_origins(['2022-01-31'], candidate, baseline) == [pd.Timestamp('2022-01-01')]
    assert evaluation.validate_origins(['2021-12-01'], candidate, baseline) == [pd.Timestamp('2021-12-01')]
    with pytest.raises(ValueError, match='embargo'):
        evaluation.validate_origins(['2021-11-01'], candidate, baseline)
    with pytest.raises(ValueError, match='training targets'):
        evaluation.validate_origins(['2023-01-01'], dict(candidate, max_train_target_date='2021-01-01'), baseline)


@pytest.fixture
def replay(monkeypatch):
    monkeypatch.setattr(evaluation, 'STATES_REGISTRY', {'TN': {}})
    frame = pd.DataFrame([dict(district_id=district, date=pd.Timestamp(date), gwl_current=depth)
        for district, depth in [('TN-A', 2.), ('TN-B', 8.)]
        for date in ['2019-01-01', '2021-01-01', '2021-02-01']])
    frame.attrs['feature_generation_id'] = 'fixture-only'
    history = pd.DataFrame([dict(state_id='TN', date=pd.Timestamp(date), gwl_m_bgl=depth,
        training_eligible=qualified, contributing_districts_count=2,
        total_districts_in_state=2, coverage_ratio=1., district_coverage_pct=100.)
        for date, depth, qualified in [('2019-01-01', 4., True), ('2021-01-01', 5., True),
                                       ('2021-02-01', 7., True), ('2021-03-01', 9., False)]])
    registry = [dict(district_id='TN-A', state_id='TN'), dict(district_id='TN-B', state_id='TN')]
    seen = []
    def reference(available, cutoff):
        assert available.date.max() <= pd.Timestamp(cutoff)
        seen.append(('reference', len(available)))
        return object()
    def district(district_id, available, cutoff, generation, bundle, donor, calibration=None):
        assert available.date.max() <= pd.Timestamp(cutoff)
        assert calibration is None
        seen.append((district_id, len(available)))
        depth = available.sort_values('date').iloc[-1].gwl_current
        origin = pd.Timestamp(cutoff).to_period('M').to_timestamp()
        return dict(status='forecast', district_id=district_id, units='m_bgl',
            forecast=[dict(horizon=h, date=(origin+pd.DateOffset(months=h)).date().isoformat(),
                           predicted_gwl=float(depth+h)) for h in range(1, 13)])
    def candidate(code, known, models, card, cutoff):
        assert known.date.max() <= pd.Timestamp(cutoff)
        last = known.loc[known.training_eligible].sort_values('date').iloc[-1].gwl_m_bgl
        origin = pd.Timestamp(cutoff).to_period('M').to_timestamp()
        return dict(status='forecast', forecast=[dict(horizon=h, predicted_gwl=float(last+h/2),
            target_date=(origin+pd.DateOffset(months=h)).date().isoformat()) for h in range(1, 13)])
    monkeypatch.setattr(evaluation, 'RegionalReference', reference)
    monkeypatch.setattr(evaluation, 'forecast_district', district)
    monkeypatch.setattr(evaluation.median, 'forecast_state', candidate)
    card = dict(train_target_cutoff='2019-12-31', feature_generation_id='fixture-only')
    bundle = (None, dict(train_target_cutoff='2019-12-31', model_sha256='fixture-only'))
    return frame, history, registry, card, bundle, seen


def test_replay_uses_unchanged_district_path_mean_and_separate_median_targets(replay):
    frame, history, registry, card, bundle, seen = replay
    report, cases = evaluation.run_evaluation(frame, history, {}, card, ['2021-01-01'], registry, bundle)
    first = cases.loc[cases.target_eligible].iloc[0]
    assert first.baseline == 6.  # Equal mean of the two original district predictions, 3 and 9.
    assert first.actual == 7.  # Held-out state median, never the baseline mean/history.
    assert first.candidate == 5.5
    assert first.persistence == 5.
    assert [name for name, _ in seen] == ['reference', 'TN-A', 'TN-B']
    assert report['comparison']['paired']['candidate']['n'] == 1
    assert report['status'] == 'experimental' and report['promotion_recommended'] is False
    assert len(cases) == 12


def test_future_values_do_not_change_predictions_or_origin_references(replay):
    frame, history, registry, card, bundle, _ = replay
    _, first = evaluation.run_evaluation(frame, history, {}, card, ['2021-01-01'], registry, bundle)
    altered = frame.copy()
    altered.loc[altered.date > pd.Timestamp('2021-01-31'), 'gwl_current'] = 10000.
    altered_history = history.copy()
    altered_history.loc[altered_history.date > pd.Timestamp('2021-01-31'), 'gwl_m_bgl'] = 20000.
    _, second = evaluation.run_evaluation(altered, altered_history, {}, card, ['2021-01-01'], registry, bundle)
    pd.testing.assert_frame_equal(first[['baseline', 'candidate', 'persistence']], second[['baseline', 'candidate', 'persistence']])
    assert first.loc[0, 'actual'] != second.loc[0, 'actual']


def test_duplicate_state_target_keys_fail_before_evaluation(replay):
    frame, history, registry, card, bundle, _ = replay
    with pytest.raises(ValueError, match='Ambiguous'):
        evaluation.run_evaluation(frame, pd.concat([history, history.iloc[:1]]), {}, card, ['2021-01-01'], registry, bundle)


def test_insufficient_state_produces_unavailable_metrics_and_keeps_baseline(replay, monkeypatch):
    frame, history, registry, card, bundle, _ = replay
    monkeypatch.setattr(evaluation.median, 'forecast_state', lambda *a, **kw:
                        dict(status='insufficient_data', message='Insufficient qualified state history.'))
    report, cases = evaluation.run_evaluation(frame, history, {}, card, ['2021-01-01'], registry, bundle)
    assert report['comparison']['baseline']['n'] == 1
    assert report['comparison']['candidate']['n'] == 0
    assert report['comparison']['paired']['baseline']['n'] == 0
    assert report['comparison']['changes']['mae_m']['absolute_change_m'] is None
    assert cases.candidate.isna().all()
    assert report['comparison']['failure_reasons'] == {'Insufficient qualified state history.': 1}


def test_report_is_strict_json_and_never_overwrites_prior_evidence(tmp_path, replay):
    frame, history, registry, card, bundle, _ = replay
    report, cases = evaluation.run_evaluation(frame, history, {}, card, ['2021-01-01'], registry, bundle)
    output = tmp_path / 'comparison'
    saved = evaluation.write_report(output, report, cases)
    assert json.loads((output/'evaluation.json').read_text()) == saved
    assert len(saved['cases_sha256']) == 64
    assert (output/'comparison.md').exists()
    with pytest.raises(FileExistsError):
        evaluation.write_report(output, report, cases)


def test_coverage_bin_boundaries_preserve_unqualified_and_missing_targets():
    ratios = [.49, .5, .75, .9, 1., np.nan]
    rows = pd.DataFrame(dict(state_id=['TN']*6,
        target_date=pd.date_range('2021-01-01', periods=6, freq='MS').strftime('%Y-%m-%d'),
        target_eligible=[False, True, True, True, True, False],
        target_observed=[True]*5+[False], target_coverage_ratio=ratios,
        actual=[2.]*5+[np.nan], baseline=[3.]*6, candidate=[2.]*6,
        persistence=[1.]*6, candidate_reason=[None]*6))
    bins = evaluation.coverage_summaries(rows)
    assert bins['under_50_percent']['attempted_horizon_cases'] == 1
    assert bins['under_50_percent']['candidate']['n'] == 0
    assert bins['50_to_75_percent']['candidate']['n'] == 1
    assert bins['75_to_90_percent']['candidate']['n'] == 1
    assert bins['90_to_100_percent']['candidate']['n'] == 2
    assert bins['missing_observed_target']['attempted_horizon_cases'] == 1
    assert sum(value['eligible_target_cases'] for value in bins.values()) == 4


def test_repeated_targets_report_unique_observations_without_inflating_count():
    rows = pd.concat([metric_rows(), metric_rows()], ignore_index=True)
    rows['origin_date'] = ['2020-12-01']*2+['2021-01-01']*2
    rows['horizon'] = [2, 3, 1, 2]
    counts = evaluation.target_reuse_summary(rows)
    assert counts['eligible']['forecast_cases'] == 4
    assert counts['eligible']['unique_state_month_targets'] == 2
    assert counts['eligible']['repeated_forecast_cases'] == 2
    assert counts['eligible']['maximum_forecasts_per_target'] == 2
    assert counts['eligible']['target_calendar_months'] == 2
    assert counts['eligible']['target_months_of_year'] == [2, 3]
    assert counts['paired'] == counts['eligible']
    metrics = evaluation.error_metrics(rows, 'candidate')
    assert metrics['n'] == 4 and metrics['valid_state_month_observations'] == 2
    assert metrics['evaluated_origins'] == 2
    assert metrics['horizons'] == [1, 2, 3]


def test_all_twelve_horizons_are_explicit_when_only_one_has_evidence():
    rows = metric_rows().assign(horizon=1)
    groups, support = evaluation.horizon_support(rows)
    assert set(groups) == {str(h) for h in range(1, 13)}
    assert support['horizons_with_paired_evidence'] == [1]
    assert support['all_horizons_have_paired_evidence'] is False
    assert support['all_horizons_validated'] is False
    assert support['by_horizon']['2']['n'] == 0
    assert support['by_horizon']['2']['mae_m'] is None
    assert support['by_horizon']['2']['status'] == 'no_paired_evidence'


def test_report_metrics_identify_frozen_scope_and_evidence_horizons(replay):
    frame, history, registry, card, bundle, _ = replay
    report, _ = evaluation.run_evaluation(frame, history, {}, card, ['2021-01-01'], registry, bundle)
    assert report['evidence_role'] == 'frozen_artifact_retrospective_diagnostic'
    assert report['validates_later_refit_weights'] is False
    assert report['candidate_training_cutoff'] == '2019-12-31'
    metrics = report['by_state']['TN']['candidate']
    assert metrics['horizons'] == [1]
    assert metrics['target_calendar_months'] == 1
    assert metrics['valid_state_month_observations'] == 1


def test_cli_loads_explicit_matching_frozen_district_checkpoint(tmp_path, monkeypatch, replay):
    from scripts import backtest_state_median as cli
    frame, history, registry, card, bundle, _ = replay
    artifacts = tmp_path/'models'
    artifacts.mkdir()
    (artifacts/'model_card.json').write_text('{}')
    pointer = tmp_path/'checkpoint.json'
    pointer.write_text('{"fixture": true}')
    seen = {}
    monkeypatch.setattr(cli, 'load_models', lambda path: ({}, card))
    monkeypatch.setattr(cli, 'load_feature_matrix', lambda path: frame)
    monkeypatch.setattr(cli, 'get_registry', lambda: registry)
    monkeypatch.setattr(cli, 'build_state_history', lambda *a, **kw: history)
    def load_bundle(**kwargs):
        seen.update(kwargs)
        return bundle
    monkeypatch.setattr(cli.climate, 'load_bundle', load_bundle)
    def run(*args, **kwargs):
        assert kwargs['bundle'] is bundle
        return {'comparison': {}}, pd.DataFrame()
    monkeypatch.setattr(cli, 'run_evaluation', run)
    monkeypatch.setattr(cli, 'write_report', lambda *a: None)
    report = cli.main(['--artifacts', str(artifacts), '--output', str(tmp_path/'output'),
                      '--processed-dir', str(tmp_path/'features'), '--checkpoint', str(pointer),
                      '--origins', '2020-12-01'])
    assert seen == {'checkpoint': pointer, 'expected_generation': 'fixture-only'}
    assert len(report['candidate_model_card_sha256']) == 64
    assert len(report['baseline_checkpoint_sha256']) == 64


def test_parallel_origin_merge_exactly_reproduces_serial_synthetic_replay(replay):
    frame, history, registry, card, bundle, _ = replay
    origins = ['2021-01-01', '2021-02-01']
    serial, serial_cases = evaluation.run_evaluation(frame, history, {}, card, origins, registry, bundle)
    parts = [evaluation.run_evaluation(frame, history, {}, card, [origin], registry, bundle) for origin in reversed(origins)]
    merged, merged_cases = evaluation.merge_origin_evaluations(parts, origins)
    pd.testing.assert_frame_equal(serial_cases, merged_cases, check_exact=True)
    assert serial == merged


def test_parallel_merge_rejects_wrong_provenance_overlaps_and_omissions(replay):
    frame, history, registry, card, bundle, _ = replay
    first = evaluation.run_evaluation(frame, history, {}, card, ['2021-01-01'], registry, bundle)
    with pytest.raises(ValueError, match='overlap'):
        evaluation.merge_origin_evaluations([first, first], ['2021-01-01'])
    with pytest.raises(ValueError, match='omit'):
        evaluation.merge_origin_evaluations([first], ['2021-01-01', '2021-02-01'])
    altered = (dict(first[0], data_sha256='other-source'), first[1])
    with pytest.raises(ValueError, match='mismatched'):
        evaluation.merge_origin_evaluations([first, altered], ['2021-01-01'])
