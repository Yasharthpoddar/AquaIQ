"""Paired serving-path evaluation safeguards without fitting or a database."""
import json

import numpy as np
import pandas as pd
import pytest

from scripts import evaluate_retrained_model as evaluation


@pytest.fixture
def panel(monkeypatch):
    dates = pd.date_range('2023-01-01', '2026-01-01', freq='MS')
    frames = []
    for did, depth in [('HR-One', 10.), ('HR-Two', 20.), ('TN-Three', 30.)]:
        observed_dates = (['2026-01-01'] if did == 'TN-Three' else
                          ['2023-01-01', '2024-01-01', '2025-01-01', '2025-03-01', '2026-01-01'])
        frame = pd.DataFrame({'district_id': did, 'date': dates,
            'gwl_current': depth + np.arange(len(dates)) / 100,
            'is_observed': dates.isin(pd.to_datetime(observed_dates)), 'is_imputed': False,
            'rainfall_current': 60., 'temperature': 25., 'evapotranspiration': 30.})
        frames.append(frame)
    result = pd.concat(frames, ignore_index=True)
    result.attrs.update(feature_generation_id='verified-fixture', data_source='audited_fixture')
    registry = [{'district_id': did, 'state_id': did.split('-')[0]} for did in result.district_id.unique()]
    monkeypatch.setattr(evaluation, 'get_registry', lambda: registry)
    return result


@pytest.fixture
def bundles():
    class NeverFit:
        def fit(self, *args, **kwargs):
            pytest.fail('Paired evaluation must never fit a candidate.')

    card = {'feature_generation_id': 'verified-fixture', 'train_target_cutoff': '2025-01-31'}
    return ((NeverFit(), {**card, 'model_sha256': 'frozen'}),
            (NeverFit(), {**card, 'model_sha256': 'retrained'}))


def run(panel, bundles, **kwargs):
    return evaluation.evaluate(panel, *bundles, ['2025-01-31', '2025-03-31'], **kwargs)


def test_same_production_frames_reference_and_eligibility_are_used_once(panel, bundles, monkeypatch):
    original = panel.copy(deep=True)
    predictor = evaluation.tiered.forecast_district
    calls = []

    def record(did, frame, cutoff, generation, bundle, reference, *, calibration):
        assert calibration is None
        calls.append((did, str(cutoff), id(frame), id(reference), bundle))
        return predictor(did, frame, cutoff, generation, bundle, reference, calibration=calibration)

    monkeypatch.setattr(evaluation.tiered, 'forecast_district', record)
    table = run(panel, bundles, added_districts={'HR-One'})
    assert len(table) == 8 and len(calls) == 12
    for left, right in zip(calls[::2], calls[1::2]):
        assert left[:4] == right[:4]
        assert left[4] is bundles[0] and right[4] is bundles[1]
    assert len({call[3] for call in calls}) == 2
    assert table.frozen_method.equals(table.retrained_method)
    assert table.frozen_eligible.equals(table.retrained_eligible)
    assert set(table.tier) == {'B', 'C'}
    assert table.loc[table.district_id.eq('HR-One'), 'newly_enriched'].all()
    assert not table.loc[table.district_id.ne('HR-One'), 'newly_enriched'].any()
    assert table.attrs['evaluation_coverage']['potential_target_slots'] == 72
    assert table.attrs['evaluation_coverage']['unavailable_target_slots'] == 64
    pd.testing.assert_frame_equal(panel, original)


def test_baselines_use_only_exact_past_observed_months(panel, bundles):
    table = run(panel, bundles)
    january_target = table.loc[table.district_id.eq('HR-One') & table.target_date.eq('2026-01-01')]
    known_january = float(panel.loc[panel.district_id.eq('HR-One') & panel.date.eq('2025-01-01'), 'gwl_current'].iloc[0])
    assert (january_target.seasonal == known_january).all()
    assert table.loc[table.target_date.eq('2025-03-01'), 'seasonal'].isna().all()
    assert table.loc[table.tier.eq('C'), ['persistence', 'seasonal']].isna().all().all()
    # March values cannot supply persistence for a January origin.
    january_origins = table.loc[table.district_id.eq('HR-One') & table.origin.eq('2025-01-31')]
    assert (january_origins.persistence == known_january).all()


def test_future_targets_change_errors_without_changing_predictions(panel, bundles):
    first = evaluation.evaluate(panel, *bundles, ['2025-01-31'])
    changed = panel.copy()
    changed.loc[changed.date.gt('2025-01-31'), 'gwl_current'] += 1000
    second = evaluation.evaluate(changed, *bundles, ['2025-01-31'])
    assert not first.actual.equals(second.actual)
    pd.testing.assert_frame_equal(first.drop(columns='actual'), second.drop(columns='actual'))


@pytest.mark.parametrize('column,value', [('is_observed', False), ('is_observed', 'False'),
    ('is_imputed', True), ('gwl_current', np.nan), ('gwl_current', np.inf), ('gwl_current', -1.)])
def test_unobserved_imputed_and_invalid_targets_never_become_cases(panel, bundles, column, value):
    panel[column] = panel[column].astype(object)
    panel.loc[panel.district_id.eq('HR-One') & panel.date.eq('2026-01-01'), column] = value
    table = run(panel, bundles)
    assert not (table.district_id.eq('HR-One') & table.target_date.eq('2026-01-01')).any()


@pytest.mark.parametrize('problem', ['duplicate', 'month_day', 'unknown_district', 'generation', 'future_cutoff', 'fingerprint'])
def test_invalid_keys_provenance_and_temporal_model_identity_fail(panel, bundles, problem):
    if problem == 'duplicate':
        panel = pd.concat([panel, panel.iloc[:1]], ignore_index=True)
    elif problem == 'month_day':
        panel.loc[0, 'date'] = pd.Timestamp('2023-01-02')
    elif problem == 'unknown_district':
        panel.loc[0, 'district_id'] = 'ZZ-Unknown'
    elif problem == 'generation':
        bundles[1][1]['feature_generation_id'] = 'different-generation'
    elif problem == 'future_cutoff':
        bundles[1][1]['train_target_cutoff'] = '2025-02-01'
    else:
        panel.attrs['data_sha256'] = 'verified-source-fingerprint'
        bundles[0][1]['data_sha256'] = 'different-fingerprint'
    with pytest.raises(ValueError):
        run(panel, bundles)


@pytest.mark.parametrize('origins', [[], ['2025-01-31', '2025-01-31'], ['NaT']])
def test_origins_cannot_silently_repeat_or_be_unknown(panel, bundles, origins):
    with pytest.raises(ValueError):
        evaluation.evaluate(panel, *bundles, origins)


@pytest.mark.parametrize('problem', ['unavailable', 'short_path', 'infinite_unused_horizon',
    'boolean_depth', 'boolean_horizon', 'bad_calendar', 'bad_units', 'bad_age', 'eligibility_change', 'method_change'])
def test_failed_or_unpaired_models_cannot_improve_metrics_by_dropping_cases(panel, bundles, monkeypatch, problem):
    predictor = evaluation.tiered.forecast_district

    def corrupt(did, frame, cutoff, generation, bundle, reference, *, calibration):
        result = predictor(did, frame, cutoff, generation, bundle, reference, calibration=calibration)
        if bundle is bundles[1]:
            if problem == 'unavailable': result['status'] = 'model_unavailable'
            elif problem == 'short_path': result['forecast'].pop()
            elif problem == 'infinite_unused_horizon': result['forecast'][0]['predicted_gwl'] = np.inf
            elif problem == 'boolean_depth': result['forecast'][0]['predicted_gwl'] = True
            elif problem == 'boolean_horizon': result['forecast'][0]['horizon'] = True
            elif problem == 'bad_calendar': result['forecast'][0]['date'] = '2025-03-01'
            elif problem == 'bad_units': result['units'] = 'feet'
            elif problem == 'bad_age': result['data_age_months'] = None
            elif problem == 'eligibility_change': result['data_readiness']['eligible'] = True
            else: result['forecast_method'] = 'invented_method'
        return result

    monkeypatch.setattr(evaluation.tiered, 'forecast_district', corrupt)
    with pytest.raises(ValueError):
        run(panel, bundles)


def summary_cases():
    rows = []
    for h in range(1, 7):
        rows.append(dict(district_id='HR-One' if h < 6 else 'HR-Two', state_id='HR',
            origin='2025-01-31', target_date=(pd.Timestamp('2025-01-01') + pd.DateOffset(months=h)).date().isoformat(),
            horizon=h, actual=10., frozen=11., retrained=10.123456789,
            tier='A', observation_count=30, age=[1, 4, 13, 37, None, 0][h - 1],
            persistence=10. if h != 2 else np.nan, seasonal=9. if h % 2 else np.nan,
            newly_enriched=h < 6, frozen_method='climate_conditioned_xgboost_12m',
            retrained_method='climate_conditioned_xgboost_12m', frozen_eligible=True, retrained_eligible=True))
    return pd.DataFrame(rows, columns=evaluation.COLUMNS)


def test_precise_metrics_share_target_keys_and_expose_all_coverage_panels():
    table = summary_cases()
    report = evaluation.summarize(table)
    overall = report['overall']
    assert overall['retrained']['mae_m'] == pytest.approx(.123456789, abs=1e-12)
    assert overall['retrained']['rmse_m'] == pytest.approx(.123456789, abs=1e-12)
    assert overall['frozen']['n'] == overall['retrained']['n'] == 6
    assert overall['seasonal_paired']['cases'] == 3
    assert {overall['seasonal_paired'][name]['n'] for name in ['frozen', 'retrained', 'persistence', 'seasonal']} == {3}
    assert overall['persistence_paired']['cases'] == 5
    assert overall['baseline_availability']['seasonal']['missing_cases'] == 3
    assert overall['seasonal_paired']['case_keys_sha256'] != overall['case_keys_sha256']
    assert list(report['by_horizon']) == [str(h) for h in range(1, 13)]
    assert report['by_horizon']['12']['status'] == 'unavailable'
    assert report['by_horizon']['12']['retrained']['mae_m'] is None
    assert report['by_district']['HR-One']['retrained']['n'] == 5
    assert report['by_district']['HR-Two']['status'] == 'insufficient_cases'
    assert 'retrained' not in report['by_district']['HR-Two']
    assert report['by_newly_enriched']['newly_enriched']['cases'] == 5
    assert set(report['by_age']) == set(evaluation.AGE_GROUPS)
    assert report['by_state']['HR']['target_months'] == 6
    assert report['new_blind_evaluation'] is False
    assert report['model_or_interval_selection_performed'] is False
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize('problem', ['duplicate', 'nonfinite', 'baseline_infinity', 'unknown_tier', 'bad_horizon',
    'bad_calendar', 'method_mismatch', 'eligibility_mismatch'])
def test_summary_rejects_invalid_or_duplicate_comparison_arrays(problem):
    table = summary_cases()
    if problem == 'duplicate': table = pd.concat([table, table.iloc[:1]], ignore_index=True)
    elif problem == 'nonfinite': table.loc[0, 'retrained'] = np.nan
    elif problem == 'baseline_infinity': table.loc[0, 'seasonal'] = np.inf
    elif problem == 'unknown_tier': table.loc[0, 'tier'] = 'unknown'
    elif problem == 'bad_horizon': table.loc[0, 'horizon'] = 13
    elif problem == 'bad_calendar': table.loc[0, 'target_date'] = '2025-01-02'
    elif problem == 'method_mismatch': table.loc[0, 'retrained_method'] = 'different_method'
    else: table.loc[0, 'retrained_eligible'] = False
    with pytest.raises(ValueError):
        evaluation.summarize(table)


def test_seasonal_panel_pairs_all_four_methods_on_the_same_available_cases():
    table = summary_cases()
    table.loc[0, 'persistence'] = np.nan
    report = evaluation.summarize(table)['overall']
    assert report['baseline_availability']['seasonal']['available_cases'] == 3
    paired = report['seasonal_paired']
    assert paired['cases'] == 2 and paired['excluded_cases'] == 4
    assert all(paired[name]['n'] == 2 for name in ('frozen', 'retrained', 'persistence', 'seasonal'))


def test_no_observed_targets_retains_explicit_empty_horizon_panels(panel, bundles):
    panel['is_observed'] = False
    table = run(panel, bundles)
    assert table.empty
    report = evaluation.summarize(table)
    assert report['status'] == 'unavailable'
    assert report['overall']['cases'] == 0
    assert len(report['by_horizon']) == 12
    assert all(part['status'] == 'unavailable' for part in report['by_horizon'].values())
    json.dumps(report, allow_nan=False)


def test_cli_writes_only_new_evidence_and_never_replaces_it(tmp_path, monkeypatch, panel, bundles):
    feature_directory = tmp_path / 'features'
    panel.attrs['feature_manifest'] = {'feature_csv_sha256': 'fixture-feature-csv-hash'}
    monkeypatch.setattr(evaluation, 'load_feature_matrix', lambda path: panel)
    frozen, candidate = tmp_path / 'frozen.json', tmp_path / 'candidate.json'
    frozen.write_text('immutable frozen pointer')
    candidate.write_text('immutable candidate pointer')
    before = [path.read_bytes() for path in (frozen, candidate)]
    monkeypatch.setattr(evaluation.climate, 'load_bundle', lambda path, expected_generation:
        bundles[0] if path == frozen else bundles[1])
    added = tmp_path / 'added.json'
    added.write_text(json.dumps(['HR-One']))
    output = tmp_path / 'evaluation'
    arguments = ['--features', str(feature_directory), '--frozen-checkpoint', str(frozen),
        '--candidate-checkpoint', str(candidate), '--output', str(output), '--origins',
        '2025-01-31,2025-03-31', '--added-districts', str(added)]
    report = evaluation.main(arguments)
    assert report['overall']['cases'] == 8
    assert report['cases_sha256'] == evaluation.sha256_file(output / 'cases.csv')
    assert json.loads((output / 'summary.json').read_text()) == report
    assert [path.read_bytes() for path in (frozen, candidate)] == before
    original_report = (output / 'summary.json').read_bytes()
    monkeypatch.setattr(evaluation, 'load_feature_matrix', lambda path: pytest.fail('Existing output must fail before loading inputs.'))
    with pytest.raises(FileExistsError):
        evaluation.main(arguments)
    assert (output / 'summary.json').read_bytes() == original_report
