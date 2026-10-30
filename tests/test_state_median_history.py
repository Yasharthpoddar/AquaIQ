"""Full history stays source-pinned, causal, genuinely observed and untruncated."""
from copy import deepcopy
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from models import state_median_history as history
from models import state_median_forecast as median
from models.xgboost_model import sha256_file


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    root = tmp_path/'project'
    directory = root/'data/processed/enrichment/pinned'
    directory.mkdir(parents=True)
    (directory/'feature_manifest.json').write_text('{"fixture": "history-only"}')
    (directory/'features_matrix.csv').write_text('fixture-only source bytes\n')
    registry = [dict(district_id=code+'-'+district, state_id=code)
                for code, districts in [('TN', ['A', 'B', 'C', 'D']), ('AS', ['A', 'B']), ('LA', ['A'])]
                for district in districts]
    rows = [dict(district_id=district, date=pd.Timestamp(date), gwl_current=value,
                 is_observed=observed, is_imputed=imputed)
            for district, date, value, observed, imputed in [
                ('TN-A', '2002-01-01', 2., True, False), ('TN-B', '2002-01-01', 6., True, False),
                ('TN-A', '2002-02-01', 10., True, False),
                ('TN-A', '2002-03-01', 99., True, True),  # Conflicting flags cannot make an observation.
                ('TN-A', '2002-04-01', 88., False, True),
                ('TN-A', '2026-10-01', 1000., True, False),  # Beyond the completed September cutoff.
                ('AS-A', '2013-01-01', 7., True, False), ('AS-B', '2013-01-01', 9., True, False),
                ('LA-A', '2026-09-01', None, False, False),
            ]]
    frame = pd.DataFrame(rows)
    frame.attrs.update(feature_generation_id='fixture-generation', data_sha256='b'*64,
        feature_manifest={'feature_csv_sha256': sha256_file(directory/'features_matrix.csv')})
    manifest = dict(source_manifest_sha256=sha256_file(directory/'feature_manifest.json'),
        source_csv_sha256=sha256_file(directory/'features_matrix.csv'),
        data_sha256='b'*64, registry_sha256='c'*64, model_algorithm_sha256=sha256_file(median.__file__),
        feature_generation_id='fixture-generation', min_coverage=.5,
        model_name='state_median_tiered', model_version='2.0-state-median-tiered', artifact_release='fixture-r2')
    forecast = dict(state_id='TN', product=median.PRODUCT_NAME, status='forecast',
        as_of='2026-10-29', input_cutoff='2026-09-01',
        generation_id='789ce3b5-3170-5866-9ce2-c0ec2f0b1b59', publication_status='published',
        feature_generation='fixture-generation', source_data_sha256='b'*64, registry_sha256='c'*64,
        min_coverage=.5, model_name=manifest['model_name'], model_version=manifest['model_version'],
        artifact_release=manifest['artifact_release'], release_manifest_sha256='d'*64,
        forecast=[dict(immutable_fixture=True)])
    calls = []
    def load(path):
        calls.append(Path(path))
        return frame
    monkeypatch.setattr(history, 'ROOT', root)
    monkeypatch.setattr(history, 'get_registry', lambda: registry)
    monkeypatch.setattr(history, 'registry_hash', lambda: 'c'*64)
    monkeypatch.setattr(median, 'registry_hash', lambda: 'c'*64)
    monkeypatch.setattr(history, 'load_feature_matrix', load)
    monkeypatch.setattr(median, 'forecast_state', lambda *a, **kw: pytest.fail('History must not run inference.'))
    monkeypatch.delenv(history.SOURCE_ENV, raising=False)
    history.clear_history_cache()
    yield directory, frame, manifest, forecast, calls
    history.clear_history_cache()


def test_all_genuine_history_is_returned_with_coverage_gaps_and_no_fills(snapshot):
    directory, _, manifest, forecast, _ = snapshot
    original = deepcopy(forecast)
    result = history.get_full_state_history('TN', forecast, manifest)
    assert len(result['history']) == 297
    assert result['history_start'] == result['earliest_observation_date'] == '2002-01-01'
    assert result['earliest_eligible_date'] == '2002-01-01'
    assert result['history_end'] == '2026-09-01'
    assert result['generation_id'] == forecast['generation_id']
    assert result['feature_generation'] == forecast['feature_generation']
    assert result['source_data_sha256'] == forecast['source_data_sha256']
    first, low, missing = result['history'][:3]
    assert first['gwl_m_bgl'] == 4. and first['training_eligible'] is True
    assert first['district_coverage_pct'] == 50. and first['contributing_districts_count'] == 2
    assert low['gwl_m_bgl'] == 10. and low['training_eligible'] is False
    assert low['is_observed'] is True and low['observation_quality'] == 'low_coverage'
    assert missing['gwl_m_bgl'] is None and missing['is_observed'] is False
    assert all(not row['is_imputed'] and not row['is_forecast'] and not row['is_forward_filled_display'] for row in result['history'])
    assert result['observed_state_months'] == 2 and result['qualified_state_months'] == 1
    assert forecast == original


def test_late_starting_state_has_no_fake_2002_padding_and_no_data_is_empty(snapshot):
    _, _, manifest, forecast, _ = snapshot
    later = history.get_full_state_history('AS', dict(forecast, state_id='AS'), manifest)
    empty = history.get_full_state_history('LA', dict(forecast, state_id='LA', status='insufficient_data'), manifest)
    assert later['history'][0]['date'] == '2013-01-01'
    assert len(later['history']) == 165
    assert later['history'][0]['gwl_m_bgl'] == 8.
    assert empty['history'] == [] and empty['status'] == 'no_observations'
    assert empty['earliest_observation_date'] is None and empty['earliest_eligible_date'] is None


def test_future_observation_changes_never_enter_published_history(snapshot):
    _, frame, manifest, forecast, _ = snapshot
    first = history.get_full_state_history('TN', forecast, manifest)
    frame.loc[frame.date.gt(pd.Timestamp('2026-09-01')), 'gwl_current'] = 99999.
    history.clear_history_cache()
    second = history.get_full_state_history('TN', forecast, manifest)
    assert first['history'] == second['history']
    assert all(row['date'] <= '2026-09-01' for row in second['history'])


@pytest.mark.parametrize('field,value', [('source_data_sha256', 'a'*64), ('feature_generation', 'other'),
    ('registry_sha256', 'a'*64), ('artifact_release', 'other'), ('model_version', 'other'), ('min_coverage', .7)])
def test_forecast_and_manifest_mismatch_fails_before_loading(snapshot, field, value):
    _, _, manifest, forecast, calls = snapshot
    with pytest.raises(RuntimeError, match='identities differ'):
        history.get_full_state_history('TN', dict(forecast, **{field: value}), manifest)
    assert not calls


def test_wrong_explicit_or_environment_override_never_uses_discovered_source(snapshot, tmp_path, monkeypatch):
    directory, _, manifest, forecast, calls = snapshot
    wrong = tmp_path/'wrong'
    wrong.mkdir()
    (wrong/'feature_manifest.json').write_text('wrong-generation')
    with pytest.raises(RuntimeError, match='configured history source'):
        history.get_full_state_history('TN', forecast, manifest, wrong)
    monkeypatch.setenv(history.SOURCE_ENV, str(wrong))
    with pytest.raises(RuntimeError, match='configured history source'):
        history.get_full_state_history('TN', forecast, manifest)
    assert not calls
    assert history.get_full_state_history('TN', forecast, manifest, directory)['history'][0]['date'] == '2002-01-01'


def test_discovery_rejects_ambiguous_and_missing_exact_manifests(snapshot):
    directory, _, manifest, forecast, _ = snapshot
    duplicate = directory.parent/'duplicate'
    duplicate.mkdir()
    (duplicate/'feature_manifest.json').write_bytes((directory/'feature_manifest.json').read_bytes())
    with pytest.raises(RuntimeError, match='More than one matching'):
        history.get_full_state_history('TN', forecast, manifest)
    # An explicit matching directory disambiguates safely.
    assert history.get_full_state_history('TN', forecast, manifest, directory)['status'] == 'available'
    with pytest.raises(RuntimeError, match='not installed'):
        history.get_full_state_history('TN', forecast, dict(manifest, source_manifest_sha256='e'*64))


def test_cache_reuse_rechecks_content_hash_even_if_stat_metadata_is_preserved(snapshot):
    directory, _, manifest, forecast, calls = snapshot
    history.get_full_state_history('TN', forecast, manifest)
    source = directory/'features_matrix.csv'
    before = source.stat()
    raw = source.read_bytes()
    source.write_bytes(b'x'+raw[1:])
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(RuntimeError, match='source content differs'):
        history.get_full_state_history('TN', forecast, manifest)
    assert len(calls) == 1


def test_verified_aggregation_cache_is_shared_but_returned_rows_are_independent(snapshot):
    _, _, manifest, forecast, calls = snapshot
    first = history.get_full_state_history('TN', forecast, manifest)
    first['history'][0]['gwl_m_bgl'] = 99999.
    second = history.get_full_state_history('TN', forecast, manifest)
    history.get_full_state_history('AS', dict(forecast, state_id='AS'), manifest)
    assert len(calls) == 1
    assert second['history'][0]['gwl_m_bgl'] == 4.


def test_dataframe_identity_registry_and_source_availability_are_not_bypassed(snapshot, monkeypatch):
    directory, frame, manifest, forecast, _ = snapshot
    frame.attrs['data_sha256'] = 'a'*64
    with pytest.raises(RuntimeError, match='dataframe identity'):
        history.get_full_state_history('TN', forecast, manifest)
    frame.attrs['data_sha256'] = manifest['data_sha256']
    monkeypatch.setattr(history, 'registry_hash', lambda: 'f'*64)
    with pytest.raises(RuntimeError, match='district registry differs'):
        history.get_full_state_history('TN', forecast, manifest)
    monkeypatch.setattr(history, 'registry_hash', lambda: manifest['registry_sha256'])
    (directory/'features_matrix.csv').unlink()
    with pytest.raises(RuntimeError, match='source files are unavailable'):
        history.get_full_state_history('TN', forecast, manifest)


def test_pinned_forecast_context_and_completed_cutoff_are_required(snapshot):
    _, _, manifest, forecast, _ = snapshot
    with pytest.raises(RuntimeError, match='pinned'):
        history.get_full_state_history('TN', dict(forecast, generation_id=None), manifest)
    with pytest.raises(RuntimeError, match='completed-input'):
        history.get_full_state_history('TN', dict(forecast, input_cutoff='2026-10-01'), manifest)
    with pytest.raises(RuntimeError, match='pinned'):
        history.get_full_state_history('AS', forecast, manifest)
