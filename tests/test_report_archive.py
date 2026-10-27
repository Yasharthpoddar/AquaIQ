import hashlib
import json

import pytest

from scripts import restore_report_archive as archive


def entry(data=b'example\n',transform='raw'):
    actual=data.replace(b'\n',b'\r\n') if transform=='crlf' else data
    return {'path':'reports/old/fixture.json','commit':'a'*40,'git_sha256':hashlib.sha256(data).hexdigest(),
            'sha256':hashlib.sha256(actual).hexdigest(),'transform':transform}


@pytest.mark.parametrize('transform',['raw','crlf'])
def test_materialization_reconstructs_and_checks_original_bytes(transform):
    data=b'example\n'
    expected=data.replace(b'\n',b'\r\n') if transform=='crlf' else data
    assert archive.materialize(entry(data,transform),lambda ref:data)==expected


@pytest.mark.parametrize('path',['../source.py','reports/../../.env','models/model.json','/reports/file','reports/.git/config','reports/a:file','reports/NUL'])
def test_unsafe_targets_are_rejected(path):
    with pytest.raises(ValueError):archive.safe_path(path)


def test_corrupt_git_payload_is_rejected():
    with pytest.raises(ValueError,match='checksum'):archive.materialize(entry(),lambda ref:b'changed')


def test_restore_never_overwrites_and_preflights_all_files(tmp_path,monkeypatch):
    monkeypatch.setattr(archive,'ROOT',tmp_path)
    manifest=tmp_path/'inventory.json';manifest.write_text(json.dumps({'files':[entry()]}))
    destination=tmp_path/'recovered'
    assert archive.restore(manifest,destination,fetch=lambda ref:b'example\n')==1
    assert (destination/'reports/old/fixture.json').read_bytes()==b'example\n'
    with pytest.raises(FileExistsError):archive.restore(manifest,destination,fetch=lambda ref:b'example\n')
    manifest.write_text(json.dumps({'files':[entry(),{**entry(),'path':'reports/new/other.json','git_sha256':'0'*64}]}))
    other=tmp_path/'other'
    with pytest.raises(ValueError,match='checksum'):archive.restore(manifest,other,fetch=lambda ref:b'example\n')
    assert not other.exists()
