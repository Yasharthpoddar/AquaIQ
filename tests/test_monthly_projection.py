"""Calendar alignment, provenance and stale-origin projection regressions."""
import json

import numpy as np
import pandas as pd
import pytest

from models import monthly_projection as monthly


def history(periods=120, start='2011-02-01', depth=20.0, trend=0.12, seasonal=2.0):
    dates = pd.date_range(start, periods=periods, freq='MS')
    frame = pd.DataFrame({'date': dates,
                          'gwl_current': depth + np.arange(periods) * trend / 12
                          + seasonal * np.sin(dates.month * 2 * np.pi / 12),
                          'is_observed': True, 'is_imputed': False})
    return frame


def evidence(frame, as_of='2026-10-13'):
    return {'district_id': 'GJ-Gandhinagar', 'as_of': pd.Timestamp(as_of),
            'origin': pd.Timestamp(frame.date.max()) if len(frame) else None,
            'generation': 'fixture-generation', 'estimate_type': 'district_level',
            'zone': None, 'reason': None, 'history': frame}


@pytest.mark.parametrize('cutoff,expected', [
    ('2026-10-13', ['2026-11','2026-12','2027-01','2027-02','2027-03','2027-04']),
    ('2025-12-31', ['2026-01','2026-02','2026-03','2026-04','2026-05','2026-06']),
    ('2024-02-29', ['2024-03','2024-04','2024-05','2024-06','2024-07','2024-08']),
])
def test_six_future_months_are_anchored_to_requested_date(cutoff, expected):
    result = monthly.projection_from_evidence(evidence(history(), cutoff))
    assert [row['month'] for row in result['forecast']] == expected
    assert result['forecast_origin'] == cutoff
    assert result['last_observed_date'] == '2021-01-01'
    assert result['status'] == 'projection'
    assert all(pd.Timestamp(row['date']) > pd.Timestamp(cutoff) for row in result['forecast'])
    assert result['validation']['sufficient_for_operational_use'] is False
    json.dumps(result, allow_nan=False)


def test_imputed_unknown_future_and_partial_month_data_cannot_change_projection():
    frame = history()
    baseline = monthly.projection_from_evidence(evidence(frame))
    artificial = pd.DataFrame({'date': pd.to_datetime(['2021-02-01','2021-03-01','2026-10-01','2027-01-01']),
                              'gwl_current': [999.,888.,777.,666.],
                              'is_observed': [False,None,True,True], 'is_imputed': [True,False,False,False]})
    mutated = evidence(pd.concat([frame, artificial]))
    result = monthly.projection_from_evidence(mutated)
    assert result['forecast'] == baseline['forecast']
    assert result['last_observed_date'] == '2021-01-01'
    assert result['fit_details']['history_sha256'] == baseline['fit_details']['history_sha256']


def test_damping_includes_old_data_gap_and_has_finite_long_run_limit():
    fit = monthly.fit_projection(history(seasonal=0., trend=1.2), pd.Timestamp('2026-10-13'))
    origin = fit['origin']
    depths = monthly.predict_depth(fit, [origin,origin+pd.DateOffset(months=6),
                                       origin+pd.DateOffset(months=69),origin+pd.DateOffset(months=75)])
    assert depths[3] > depths[2] > depths[1] > depths[0]
    assert depths[3]-depths[2] < depths[1]-depths[0]
    long_run = monthly.predict_depth(fit, [origin+pd.DateOffset(months=600)])[0]
    assert long_run-depths[0] == pytest.approx(fit['coefficients'][1]*3, rel=0.001)


def test_quarterly_observations_fit_calendar_seasonality_without_fake_months():
    frame = history(periods=180)
    frame = frame[frame.date.dt.month.isin([1,5,8,11])]
    result = monthly.projection_from_evidence(evidence(frame))
    assert len(result['forecast']) == 6
    assert result['fit_details']['annual_seasonality'] is True
    assert len({point['predicted_gwl'] for point in result['forecast']}) > 1
    assert result['fit_details']['observed_months'] < 60


@pytest.mark.parametrize('depth', [0.0, 105.0])
def test_zero_and_deep_water_tables_are_preserved(depth):
    result = monthly.projection_from_evidence(evidence(history(depth=depth, trend=0., seasonal=0.)))
    assert all(point['predicted_gwl'] == pytest.approx(depth) for point in result['forecast'])
    assert result['estimated_current_gwl'] == pytest.approx(depth)


def test_insufficient_real_history_is_null_not_a_manufactured_curve():
    result = monthly.projection_from_evidence(evidence(history(periods=12)))
    assert result['status'] == 'insufficient_data' and result['forecast'] == []
    assert result['estimated_current_gwl'] is None
    missing = evidence(history())
    missing['estimate_type'] = 'insufficient_data'
    assert monthly.projection_from_evidence(missing)['forecast'] == []


def test_duplicate_observation_months_are_rejected():
    frame = history()
    with pytest.raises(ValueError, match='duplicate'):
        monthly.fit_projection(pd.concat([frame,frame.iloc[:1]]), pd.Timestamp('2026-10-13'))


def test_predictions_never_produce_negative_depth():
    fit = monthly.fit_projection(history(depth=30, trend=-1.2, seasonal=0), pd.Timestamp('2026-10-13'))
    fit['coefficients'][1] = -1000.0
    assert monthly.predict_depth(fit, [pd.Timestamp('2026-11-01')])[0] == 0.


def test_zone_provenance_is_retained_for_monthly_projection():
    selected = evidence(history())
    selected.update(estimate_type='zone_fallback', zone='Gujarat Plains', reason='Limited district observations.')
    result = monthly.projection_from_evidence(selected)
    assert result['source_zone'] == 'Gujarat Plains'
    assert result['estimate_type'] == 'zone_fallback'
    assert result['zone_fallback_reason'] == 'Limited district observations.'
