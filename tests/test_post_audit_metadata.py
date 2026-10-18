"""F10 schema/documentation checks using metadata only, never model execution."""
import json
from pathlib import Path

import pandas as pd
import pytest

from models import ann_classifier as ann
from models import linear_regression as linear
from models import xgboost_model as forecast

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return json.loads((ROOT/relative).read_text(encoding='utf-8'))


@pytest.fixture(autouse=True)
def forbid_training_and_production_io(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Metadata checks must not fit, forecast, load datasets or access a database.')
    for owner, name in [(ann.MLPClassifier,'fit'), (ann.MLPClassifier,'predict'),
                        (ann,'load_features'),
                        (linear,'train_per_district'), (forecast,'new_model'),
                        (forecast,'load_feature_matrix'), (forecast,'get_connection')]:
        monkeypatch.setattr(owner, name, forbidden)


def test_ann_documentation_matches_encoded_canonical_feature_schema():
    encoded = forecast.encode_crop_season(pd.DataFrame({'crop_season_flag':['Kharif','Rabi','Zaid']}))
    for column in forecast.CANONICAL_FEATURE_COLS:
        if column not in encoded:
            encoded[column] = 1.
    columns = forecast.get_feature_columns(encoded)
    assert len(columns) == 12
    assert sum(name.startswith('season_') for name in columns) == 3
    assert columns == forecast.CANONICAL_FEATURE_COLS
    assert '12-feature vector' in ann.__doc__
    assert '[12, 64, 4]' in ann.train_ann.__doc__
    # A fixture never needs to invoke the guarded training entry point.


def test_ols_docs_describe_actual_split_contract_not_old_fixed_test_years():
    assert 'configured training-label cutoff' in linear.__doc__
    assert 'heldout_origin_start(cutoff)' in linear.__doc__
    assert 'date_range.end' in linear.__doc__
    assert '2023-2024 test set' not in linear.__doc__
    assert 'separate from the serving ensemble' in linear.__doc__


def test_historical_climate_review_is_distinct_from_active_generation():
    old = read('reports/climate_forecast_review.json')
    manifest = read('data/processed/feature_manifest.json')
    pointer_path = ROOT/'models/checkpoints/aquaiq_monthly_climate.json'
    pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
    card = json.loads((pointer_path.parent/pointer['card_path']).read_text(encoding='utf-8'))
    evaluation = read('reports/climate_forecast_evaluation.json')
    assert old['feature_generation_id'] == 'physical-v3-causal-monthly-90a24f1f2574'
    assert old['source_feature_csv_sha256'] != manifest['feature_csv_sha256']
    assert old['feature_generation_id'] != manifest['generation_id']
    assert card['feature_generation_id'] == evaluation['feature_generation_id'] == manifest['generation_id']
    assert card['data_sha256'] == evaluation['data_sha256']
    assert card['model_sha256'] == evaluation['model_sha256'] == pointer['model_sha256']
    readme = (ROOT/'README.md').read_text(encoding='utf-8')
    assert old['feature_generation_id'] in readme
    assert 'historical evidence and does not verify a later generation' in readme
