"""Fixed-array historical-evaluation guards; no estimator fitting or issuance."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location('actual_forecast_eval', Path(__file__).with_name('evaluate_research.py'))
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def fixture_frame():
    dates = pd.date_range('2022-07-01', '2024-01-01', freq='MS')
    frame = pd.DataFrame({'district_id': 'TS-SYNTHETIC_UNIT', 'date': dates,
        'gwl_current': np.arange(len(dates), dtype=float)+1, 'is_observed':True,
        'panel_sha256':'synthetic-panel', 'well_count':1,
        'first_reported_date':dates, 'last_reported_date':dates})
    for name in evaluation.F:
        if name not in frame:
            frame[name] = 1.
    return frame


def test_exact_six_month_target_and_seasonal_not_nearest():
    frame = fixture_frame()
    # A finite imputed seasonal must abstain, even with adjacent observed months.
    frame.loc[frame.date.eq('2023-01-01'), 'is_observed'] = False
    rows = evaluation.make_inventory(frame, {'primary_target_range':['2024-01-01','2024-01-01'],
        'secondary_target_range':['2024-02-01','2024-03-01']})
    january = rows.loc[rows.target_date.eq('2024-01-01')].iloc[0]
    assert january.date == pd.Timestamp('2023-07-01')
    assert january.seasonal_date == pd.Timestamp('2023-01-01')
    assert not january.reference_eligible
    assert 'missing_exact_observed_seasonal' in january.reference_exclusion_reasons


def test_observed_targets_required_without_suppressing_missing_inventory():
    frame = fixture_frame()
    frame.loc[frame.date.eq('2024-01-01'), 'is_observed'] = False
    rows = evaluation.make_inventory(frame, {'primary_target_range':['2024-01-01','2024-01-01'],
        'secondary_target_range':['2024-02-01','2024-03-01']})
    assert len(rows) == 3
    assert not rows.reference_eligible.any()
    assert rows.reference_exclusion_reasons.str.contains('missing_observed_target').all()


def test_metrics_bias_and_nonconstant_r2_semantics():
    measured = evaluation.measure([2.,2.], [1.,3.])
    assert measured['bias_m'] == 0
    assert measured['rmse_m'] == 1
    assert measured['mae_m'] == 1
    assert measured['r2'] is None
    with pytest.raises(ValueError):
        evaluation.measure([1.,np.nan],[1.,2.])


def test_paired_resampling_identical_predictions_zero_in_both_dependence_schemes():
    table = pd.DataFrame({'district_id':['A']*12+['B']*12,
        'target_date':list(pd.date_range('2024-01-01',periods=12,freq='MS'))*2,
        'actual':np.arange(24,dtype=float), 'model':np.arange(24,dtype=float)+1,
        'baseline':np.arange(24,dtype=float)+1})
    result = evaluation.uncertainty(table,'model','baseline',repeats=50)
    for interval in result['interval_95_percentile'].values():
        assert interval['mae_difference_m'] == [0,0]
        assert interval['rmse_difference_m'] == [0,0]


def test_existing_output_rejected_before_any_model_or_input_loading():
    with pytest.raises(ValueError,match='absent output'):
        evaluation.run(evaluation.RUN/'missing-normalized', evaluation.RUN)
