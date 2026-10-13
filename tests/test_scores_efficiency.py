"""Published score responses read their shared configuration once per batch."""
import json
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from api.routes import scores


@pytest.mark.parametrize('validated', [False, True])
def test_large_score_batch_preserves_contract_and_reads_configuration_once(monkeypatch, validated):
    config_file = Mock()
    config_file.read_text.return_value = (
        'model_hyperparameters:\n'
        '  ensemble:\n'
        f'    validated_weights: {str(validated).lower()}\n'
    )
    root = Mock()
    root.__truediv__ = Mock(return_value=config_file)
    monkeypatch.setattr(scores, 'ROOT', root)
    parser = Mock(wraps=scores.yaml.safe_load)
    monkeypatch.setattr(scores.yaml, 'safe_load', parser)

    frame = pd.DataFrame([
        {'district_id': f'D-{index}', 'name': f'District {index}', 'state': 'Test',
         'score': float(index % 100), 'tier': 'Watch', 'estimate_type': 'district_level',
         'zone_fallback_reason': None, 'top_factor_1': 'Depth', 'top_factor_2': None,
         'top_factor_3': 'Trend', 'forecast_date': pd.Timestamp('2026-10-13'),
         'last_observed_date': pd.Timestamp('2021-01-01'), 'model_version': 'verified',
         'feature_generation': 'generation', 'run_id': 'complete-run'}
        for index in range(725)
    ])
    frame.loc[1, ['score', 'tier']] = [np.nan, None]
    frame.loc[1, 'last_observed_date'] = pd.NaT
    frame.loc[2, 'last_observed_date'] = pd.Timestamp('2026-05-01')

    records = scores.score_records(frame)

    assert len(records) == 725
    config_file.read_text.assert_called_once_with(encoding='utf-8')
    parser.assert_called_once()
    expected_weights_status = 'validated' if validated else 'initial_uncalibrated'
    assert all(record['weights_status'] == expected_weights_status for record in records)
    assert records[0]['score'] == 0
    assert records[0]['status'] == 'historical_forecast'
    assert records[0]['forecast_origin'] == '2021-01-01'
    assert records[0]['forecast_target'] == '2021-07-01'
    assert records[0]['as_of'] == records[0]['forecast_date'] == '2026-10-13T00:00:00'
    assert records[0]['top_factors'] == ['Depth', 'Trend']
    assert records[0]['model_version'] == 'verified'
    assert records[0]['feature_generation'] == 'generation'
    assert records[0]['run_id'] == 'complete-run'
    assert records[1]['score'] is records[1]['tier'] is None
    assert records[1]['status'] == 'unavailable'
    assert records[1]['forecast_origin'] is records[1]['forecast_target'] is None
    assert records[2]['status'] == 'success'
    assert records[2]['forecast_target'] == '2026-11-01'
    json.dumps(records, allow_nan=False)


def test_empty_score_batch_needs_no_configuration(monkeypatch):
    root = Mock()
    root.__truediv__ = Mock(side_effect=AssertionError('Empty batches must not read configuration'))
    monkeypatch.setattr(scores, 'ROOT', root)

    assert scores.score_records(pd.DataFrame()) == []
    root.__truediv__.assert_not_called()
