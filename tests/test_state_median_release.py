"""Release safety tests; temporary fixtures are not forecast evidence."""
import json
from unittest.mock import Mock

import pandas as pd
import pytest

from models import state_median_release as release
from scripts.release_state_median import main


def test_missing_artifact_fails_clearly(tmp_path):
    with pytest.raises(FileNotFoundError):
        release.verify_release(tmp_path/'missing', 'requested-v1')


def test_corrupt_manifest_rejected_before_loading_any_model(tmp_path, monkeypatch):
    path = tmp_path/'release_manifest.json'
    path.write_text('{}')
    monkeypatch.setattr(release.median, 'load_models', lambda *_: pytest.fail('must verify manifest first'))
    with pytest.raises(ValueError, match='checksum'):
        release.verify_release(tmp_path, expected_manifest_sha256='a'*64)


@pytest.mark.parametrize('extra', [dict(format_version=2), dict(model_version='wrong'),
    dict(package_versions={'xgboost':'wrong'}), dict(model_algorithm_sha256='0'*64),
    dict(registry_sha256='0'*64), dict(artifact_release='unexpected')])
def test_incompatible_release_identity_fails_closed(tmp_path, extra, monkeypatch):
    value = dict(format_version=1, model_version=release.median.MODEL_VERSION,
        artifact_release='requested', package_versions=release.package_versions(),
        model_algorithm_sha256=release.sha256_file(release.median.__file__),
        registry_sha256=release.registry_hash(), features=release.median.FEATURES,
        parameters=release.median.PARAMETERS)
    value.update(extra)
    (tmp_path/'release_manifest.json').write_text(json.dumps(value))
    monkeypatch.setattr(release.median, 'load_models', lambda *_: pytest.fail('must fail before model load'))
    with pytest.raises(ValueError, match='Incompatible'):
        release.verify_release(tmp_path, 'requested')


@pytest.mark.parametrize('action', ['migrate', 'stage', 'publish', 'rollback'])
def test_production_writes_require_explicit_backup_and_authorization(action, tmp_path):
    args = [action]
    if action == 'stage':
        args += ['--release-dir', str(tmp_path), '--input', str(tmp_path/'generation.json')]
    elif action != 'migrate':
        args += ['--release-id','d8de5ac0-e3ad-4906-a16c-836640f1f60e','--expected-active','none','--reason','test']
    with pytest.raises(ValueError, match='Production writes require'):
        main(args)


def test_invalid_backup_is_not_accepted_for_migration(tmp_path):
    backup = tmp_path/'bad.dump'
    backup.write_text('not a PostgreSQL backup')
    with pytest.raises(ValueError, match='custom-format'):
        main(['migrate','--allow-production-write','--backup',str(backup)])


def test_status_is_read_only_and_reports_exact_active_identity(monkeypatch, capsys):
    from models import state_median_release_storage as storage
    read = Mock(return_value={'generation_id':'test-only-id','artifact_release':'test-version'})
    monkeypatch.setattr(storage,'get_active_release',read)
    main(['status','--test-schema','aquaiq_test_status'])
    assert json.loads(capsys.readouterr().out)['artifact_release'] == 'test-version'
    read.assert_called_once_with(test_schema='aquaiq_test_status')


def test_readiness_rejects_missing_exact_artifact_settings(monkeypatch):
    from deploy.serve import validate_state_median_release
    for name in ('AQUAIQ_STATE_MEDIAN_ARTIFACT_DIR','AQUAIQ_STATE_MEDIAN_EXPECTED_RELEASE','AQUAIQ_STATE_MEDIAN_MANIFEST_SHA256'):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match='Configure'):
        validate_state_median_release(Mock())


def test_readiness_rejects_database_artifact_mismatch(monkeypatch):
    from deploy.serve import validate_state_median_release
    from models import state_median_release_storage as storage
    monkeypatch.setenv('AQUAIQ_STATE_MEDIAN_ARTIFACT_DIR','fixture')
    monkeypatch.setenv('AQUAIQ_STATE_MEDIAN_EXPECTED_RELEASE','fixture-v1')
    monkeypatch.setenv('AQUAIQ_STATE_MEDIAN_MANIFEST_SHA256','a'*64)
    monkeypatch.setattr(release,'verify_release',lambda *args:(None,None,{'artifact_release':'fixture-v1'},'a'*64))
    monkeypatch.setattr(storage,'get_published_manifest',lambda:{'artifact_release':'other'})
    with pytest.raises(RuntimeError, match='Published state median manifest'):
        validate_state_median_release(Mock())


def test_frozen_artifact_cannot_be_packaged_as_latest_refit(tmp_path, monkeypatch):
    history = pd.DataFrame({'date':[pd.Timestamp('2026-09-01')]})
    history.attrs.update(feature_generation_id='test-source',data_sha256='a'*64)
    monkeypatch.setattr(release,'load_feature_matrix',lambda *_:history)
    monkeypatch.setattr(release.median,'build_state_history',lambda *_:history)
    monkeypatch.setattr(release.median,'load_models',lambda *_:({}, {'training_cutoff':'2019-12-01'}))
    with pytest.raises(ValueError, match='Pretrained refit'):
        release.prepare_release(tmp_path/'new', 'test-release', tmp_path/'source',
                                '2026-10-29', trained_artifacts=tmp_path/'old')
    assert not (tmp_path/'new').exists()
