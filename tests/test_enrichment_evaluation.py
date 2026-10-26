"""Scientific safeguards in the paired official-data replay."""
import numpy as np
import pandas as pd
import pytest

from scripts import evaluate_official_enrichment as evaluation
from tests.test_official_enrichment import baseline


def small_panel():
    groups = []
    for did, offset in [('AA-One', 0), ('AA-Two', 10), ('BB-Three', 20)]:
        frame = baseline()
        frame['district_id'] = did
        for col in ('gwl_current', 'GWL_current'):
            frame[col] += offset
            frame.loc[frame.date.eq('2021-08-01'), col] = 6 + offset
        frame.loc[frame.date.eq('2021-08-01'), 'is_observed'] = True
        frame.loc[frame.date.eq('2021-08-01'), 'is_imputed'] = False
        groups.append(frame)
    panel = pd.concat(groups, ignore_index=True)
    panel.attrs['feature_generation_id'] = 'baseline'
    return panel


def replay(monkeypatch, candidate):
    base = small_panel()
    monkeypatch.setattr(evaluation, 'get_registry', lambda: [{'district_id': d} for d in base.district_id.unique()])
    bundle = (None, {'train_target_cutoff': '2019-12-31'})
    return evaluation.predictions(base, candidate, [bundle, bundle], ['2021-07-31'])


def test_future_labels_change_errors_without_changing_any_prediction(monkeypatch):
    candidate = small_panel()
    first, first_cold = replay(monkeypatch, candidate)
    candidate.loc[candidate.date.eq('2021-08-01'), 'gwl_current'] = 100
    second, second_cold = replay(monkeypatch, candidate)
    assert not first.actual.equals(second.actual)
    pd.testing.assert_frame_equal(first.drop(columns='actual'), second.drop(columns='actual'))
    pd.testing.assert_frame_equal(first_cold.drop(columns='actual'), second_cold.drop(columns='actual'))


def test_pseudo_cold_reference_never_sees_hidden_local_history(monkeypatch):
    candidate = small_panel()
    _, first = replay(monkeypatch, candidate)
    candidate.loc[candidate.district_id.eq('AA-One'), 'gwl_current'] = 100
    _, second = replay(monkeypatch, candidate)
    a = first.loc[first.district_id.eq('AA-One')].drop(columns='actual')
    b = second.loc[second.district_id.eq('AA-One')].drop(columns='actual')
    pd.testing.assert_frame_equal(a, b)
    assert a.target_history_excluded.all()


def test_calibration_quantiles_use_only_supplied_calibration_cases():
    cal = pd.DataFrame({'tier_candidate': ['B','B'], 'horizon': [1,1],
        'district_id': ['AA-One','AA-Two'], 'actual': [1.,3.], 'candidate': [1.,1.], 'target_date': ['2021-02-01','2021-02-01']})
    frame = small_panel()
    frame.attrs['feature_manifest'] = {'feature_csv_sha256':'featurehash'}
    result = evaluation.build_calibration(cal, frame, (None, {'model_sha256':'modelhash'}))
    assert result['radii_m'] == {'B': {'1': 2.}}
    assert result['max_calibration_target'] == '2021-02-01'
    assert result['sample_counts']['B']['1'] == {'n':2,'districts':2}
    assert '2' not in result['radii_m']['B']


def test_metrics_require_finite_identical_case_arrays():
    assert evaluation.metric([1,3],[1,1]) == {'n':2,'mae_m':1.,'rmse_m':np.sqrt(2)}
    with pytest.raises(ValueError):
        evaluation.metric([],[])
    with pytest.raises(ValueError):
        evaluation.metric([np.nan],[1])


def test_evaluation_seal_changes_with_code_or_card(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, 'ROOT', tmp_path)
    monkeypatch.setattr(evaluation, 'SEALED_CODE', ('predictor.py',))
    (tmp_path/'predictor.py').write_text('first implementation')
    original = evaluation.code_identity()
    (tmp_path/'predictor.py').write_text('different implementation')
    assert evaluation.code_identity() != original
    assert evaluation.card_identity({'train_cutoff':'2019'}) != evaluation.card_identity({'train_cutoff':'2020'})
