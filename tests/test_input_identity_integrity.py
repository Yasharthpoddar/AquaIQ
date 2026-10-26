import json
import pytest

from models import forecast_storage
from models.xgboost_model import sha256_file


def test_identity_never_trusts_a_stale_feature_manifest(tmp_path,monkeypatch):
    processed=tmp_path/'data/processed';processed.mkdir(parents=True)
    (processed/'feature_manifest.json').write_text(json.dumps({'generation_id':'old','feature_csv_sha256':'0'*64}))
    (processed/'features_matrix.csv').write_text('changed input')
    monkeypatch.setattr(forecast_storage,'ROOT',tmp_path)
    monkeypatch.setattr(forecast_storage.climate,'load_bundle',lambda *a,**kw:pytest.fail('must reject source corruption before checking model/idempotency'))
    with pytest.raises(ValueError,match='current input identity is unverified'):
        forecast_storage.compute_input_identity('2026-10-26')


def test_generation_identity_is_portable_but_evidence_changes_invalidate_it(tmp_path,monkeypatch):
    processed=tmp_path/'data/processed';processed.mkdir(parents=True)
    matrix=processed/'features_matrix.csv';matrix.write_bytes(b'fixture\n')
    (processed/'feature_manifest.json').write_text(json.dumps({'generation_id':'fixture','feature_csv_sha256':sha256_file(matrix)}))
    crosswalk=tmp_path/'data_ingestion/district_crosswalk.csv';crosswalk.parent.mkdir();crosswalk.write_text('canonical_district_id\nAA-Test\n')
    code_names=forecast_storage.GENERATION_IMPLEMENTATION_FILES
    for name in code_names:
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'x = 1\ny = 2\n')
    evidence=tmp_path/'models/artifacts/interval_reliability.json';evidence.parent.mkdir();evidence.write_text('{"policy":2,"cases":10}')
    calibration=tmp_path/'calibration.json';calibration.write_text('{"radius":2,"count":10}')
    monkeypatch.setattr(forecast_storage,'ROOT',tmp_path)
    monkeypatch.setattr(forecast_storage,'get_registry',lambda:[{'district_id':'AA-Test'}])
    monkeypatch.setattr(forecast_storage.climate,'load_bundle',lambda *a,**kw:(None,{'model_sha256':'frozen'}))
    first=forecast_storage.compute_input_identity('2026-10-26',calibration_path=calibration)
    for name in code_names:(tmp_path/name).write_bytes(b'x = 1\r\ny = 2\r\n')
    calibration.write_bytes(b'{\r\n "count": 10, "radius": 2\r\n}\r\n')
    evidence.write_bytes(b'{\r\n "cases": 10, "policy": 2\r\n}\r\n')
    same=forecast_storage.compute_input_identity('2026-10-26',calibration_path=calibration)
    assert same['generation_id']==first['generation_id']
    evidence.write_text('{"cases":11,"policy":2}')
    changed=forecast_storage.compute_input_identity('2026-10-26',calibration_path=calibration)
    assert changed['generation_id']!=first['generation_id']
    before_dependency_change=changed['generation_id']
    (tmp_path/'models/climate_forecast.py').write_text('changed origin/weather encoding')
    assert forecast_storage.compute_input_identity('2026-10-26',calibration_path=calibration)['generation_id']!=before_dependency_change
