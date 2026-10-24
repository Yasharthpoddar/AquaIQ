"""Run relevant tests with DB, training, publishing and statistical fitting blocked."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

def forbidden(*args, **kwargs):
    raise RuntimeError('Independent audit forbids database connections, fitting and publishing')

if __name__ == '__main__':
    import pytest
    with ExitStack() as guards:
        for target in ['psycopg2.connect', 'xgboost.XGBRegressor.fit', 'models.climate_forecast_12m.train',
                       'models.climate_forecast_12m.publish_bundle', 'models.climate_forecast.train',
                       'models.climate_forecast.publish_bundle', 'models.monthly_projection.fit_projection',
                       'models.climate_forecast.fit_projection', 'models.climate_forecast_12m.fit_projection']:
            guards.enter_context(patch(target, forbidden))
        args = ['-q', '-p', 'no:cacheprovider', '--basetemp', str(Path(__file__).parent / 'pytest_tmp'),
                'tests/test_climate_forecast_12m.py', 'tests/test_climate_inputs.py', 'tests/test_api.py',
                'tests/test_climate_forecast.py::test_pairs_use_exact_calendar_months_and_complete_intermediate_weather',
                'tests/test_climate_forecast.py::test_unobserved_or_unknown_values_cannot_be_origins_or_labels',
                'tests/test_climate_forecast.py::test_invalid_intermediate_weather_excludes_longer_pairs',
                'tests/test_climate_forecast.py::test_duplicate_district_months_are_rejected_before_training',
                'tests/test_climate_forecast.py::test_training_and_holdout_are_separated_by_target_date_and_six_month_embargo',
                'tests/test_climate_forecast.py::test_holdout_uses_origin_available_weather_instead_of_realized_future_weather',
                '-k', 'not forecast_next_twelve_months_returns_exact_12_points and not api_12m_prediction_success and not api_12m_prediction_not_found and not legacy_6m_prediction_remains_compatible']
        print('pytest', ' '.join(args), flush=True)
        sys.exit(pytest.main(args))
