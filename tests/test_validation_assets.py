"""Synthetic temporary files test preflight mechanics, never forecasting data."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import check_validation_assets as check


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


@pytest.fixture
def asset_tree(tmp_path):
    """Only a validator fixture: these bytes cannot supply a forecast or Kaithal history."""
    matrix = tmp_path / check.FEATURE_CSV
    matrix.parent.mkdir(parents=True)
    matrix.write_bytes(b'validator-fixture-only\n')
    manifest = write_json(tmp_path, check.FEATURE_MANIFEST, {
        'generation_id': 'validator-fixture', 'sample_only': False,
        'feature_csv_sha256': sha(matrix)})
    crosswalk = tmp_path / 'data_ingestion/district_crosswalk.csv'
    crosswalk.parent.mkdir(parents=True)
    crosswalk.write_bytes(b'validator-fixture-crosswalk-only\n')
    contract = {'feature_generation_id': 'validator-fixture'}
    for name, path in [('feature_csv', matrix), ('feature_manifest', manifest),
                       ('district_crosswalk', crosswalk)]:
        contract[name + '_path'] = path.relative_to(tmp_path).as_posix()
        contract[name + '_sha256'] = sha(path)
    write_json(tmp_path, check.SCENARIO_CONTRACT, contract)
    for name in (check.MONTHLY_POINTER, check.PRODUCTION_POINTER):
        pointer = tmp_path / name
        model = pointer.parent / 'fixture_bundle/model.json'
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b'validator-fixture-model-only\n')
        card = write_json(tmp_path, (model.parent / 'card.json').relative_to(tmp_path), {
            'model_sha256': sha(model), 'feature_generation_id': 'validator-fixture',
            'data_sha256': 'a' * 64})
        write_json(tmp_path, name, {'bundle_schema_version': 1,
            'model_path': 'fixture_bundle/model.json', 'card_path': 'fixture_bundle/card.json',
            'model_sha256': sha(model), 'card_sha256': sha(card)})
    write_json(tmp_path, check.MONTHLY_EVALUATION, {
        'model_sha256': sha(tmp_path / 'models/checkpoints/fixture_bundle/model.json'),
        'feature_generation_id': 'validator-fixture', 'data_sha256': 'a' * 64})
    return tmp_path


def test_complete_hash_bound_fixture_is_read_only_and_does_not_claim_test_success(asset_tree, capsys):
    before = {p: p.read_bytes() for p in asset_tree.rglob('*') if p.is_file()}
    assert check.validate_assets(asset_tree)['ok']
    assert check.main(asset_tree) == 0
    assert before == {p: p.read_bytes() for p in asset_tree.rglob('*') if p.is_file()}
    output = capsys.readouterr().out
    assert 'Run the unchanged regression suite' in output
    assert 'forecasting accuracy' in output
    assert 'tests passed' not in output


def test_absent_private_assets_fail_with_actionable_paths_and_guide(tmp_path, capsys):
    assert check.main(tmp_path) == 1
    output = capsys.readouterr().out
    assert check.FEATURE_CSV in output and check.FEATURE_MANIFEST in output
    assert check.MONTHLY_POINTER in output and check.GUIDE in output
    assert 'no private-asset provisioning configured' in output
    assert 'does not mean the regression suite passed' in output


def test_model_bundle_member_is_required_even_when_card_is_present(asset_tree):
    (asset_tree / 'models/checkpoints/fixture_bundle/model.json').unlink()
    result = check.validate_assets(asset_tree)
    assert not result['ok']
    assert 'Missing required asset: models/checkpoints/fixture_bundle/model.json.' in result['issues']


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'data/../outside',
    'C:\\outside', 'data\\outside', '.env', 'data/.env.private', '.git/config',
    'data/key.pem', 'data/data.dump', 'data/unsafe\npath'])
def test_metadata_cannot_escape_or_read_private_paths(asset_tree, name):
    with pytest.raises(ValueError):
        check.repository_path(asset_tree, name)


def test_metadata_cannot_traverse_a_link_even_inside_the_checkout(asset_tree, monkeypatch):
    redirected = asset_tree / 'redirected'
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == redirected or original(path))
    with pytest.raises(ValueError, match='links or junctions'):
        check.repository_path(asset_tree, 'redirected/model.json')


def test_untrusted_metadata_value_is_not_echoed_or_opened(asset_tree, monkeypatch, capsys):
    pointer_path = asset_tree / check.MONTHLY_POINTER
    pointer = json.loads(pointer_path.read_text())
    pointer['model_path'] = '../do_not_echo_untrusted_value'
    write_json(asset_tree, check.MONTHLY_POINTER, pointer)
    original = Path.open

    def guarded_open(path, *args, **kwargs):
        assert 'do_not_echo_untrusted_value' not in path.name
        assert not path.name.startswith('.env')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', guarded_open)
    assert check.main(asset_tree) == 1
    output = capsys.readouterr().out
    assert 'Unsafe or missing file-path field' in output
    assert 'do_not_echo_untrusted_value' not in output


def test_changed_feature_bytes_cannot_pass_presence_checks(asset_tree):
    (asset_tree / check.FEATURE_CSV).write_bytes(b'changed fixture bytes\n')
    result = check.validate_assets(asset_tree)
    assert not result['ok']
    assert f'Asset checksum differs from its metadata: {check.FEATURE_CSV}.' in result['issues']


def test_malformed_metadata_fails_without_exposing_its_contents(asset_tree, capsys):
    (asset_tree / check.FEATURE_MANIFEST).write_text('{"do_not_echo_contents":', encoding='utf-8')
    assert check.main(asset_tree) == 1
    output = capsys.readouterr().out
    assert 'Invalid JSON metadata object' in output
    assert 'do_not_echo_contents' not in output


def test_sample_export_is_rejected_even_with_matching_hashes(asset_tree):
    path = asset_tree / check.FEATURE_MANIFEST
    manifest = json.loads(path.read_text())
    manifest['sample_only'] = True
    write_json(asset_tree, check.FEATURE_MANIFEST, manifest)
    contract = json.loads((asset_tree / check.SCENARIO_CONTRACT).read_text())
    contract['feature_manifest_sha256'] = sha(path)
    write_json(asset_tree, check.SCENARIO_CONTRACT, contract)
    result = check.validate_assets(asset_tree)
    assert not result['ok']
    assert f'A full, non-sample feature manifest is required: {check.FEATURE_MANIFEST}.' in result['issues']


def test_monthly_bundle_must_match_retained_evaluation_identity(asset_tree):
    evaluation = json.loads((asset_tree / check.MONTHLY_EVALUATION).read_text())
    evaluation['model_sha256'] = 'b' * 64
    write_json(asset_tree, check.MONTHLY_EVALUATION, evaluation)
    result = check.validate_assets(asset_tree)
    assert not result['ok']
    assert 'Monthly bundle differs from its retained evaluation identity: model_sha256.' in result['issues']


def test_hash_bound_card_still_must_match_feature_generation(asset_tree):
    card = asset_tree / 'models/checkpoints/fixture_bundle/card.json'
    value = json.loads(card.read_text())
    value['feature_generation_id'] = 'different-validator-fixture'
    write_json(asset_tree, card.relative_to(asset_tree), value)
    pointer = json.loads((asset_tree / check.MONTHLY_POINTER).read_text())
    pointer['card_sha256'] = sha(card)
    write_json(asset_tree, check.MONTHLY_POINTER, pointer)
    result = check.validate_assets(asset_tree)
    assert not result['ok']
    assert ('Model card and feature manifest generation identities differ: '
            + check.MONTHLY_POINTER + '.') in result['issues']
