"""Authorized probes keep credentials hidden, bound jobs and preserve old assets."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
import requests
import xarray as xr

from data_ingestion import release_weather as release


def source_fields(months=('2025-01-01',)):
    dims=('valid_time','latitude','longitude')
    coords={'valid_time':pd.DatetimeIndex(months),'latitude':np.arange(38,5.99,-.25),
            'longitude':np.arange(68,98.01,.25)}
    shape=(len(months),129,121)
    dataset=xr.Dataset({'t2m':(dims,np.full(shape,300,dtype=np.float32)),
        'pev':(dims,np.full(shape,-.002,dtype=np.float32))},coords=coords)
    dataset.t2m.attrs['units']='K'
    dataset.pev.attrs.update(units='m',GRIB_stepType='avgad',GRIB_stream='moda')
    return dataset


def request():
    return release.era5_requests('2025-01','2025-01',as_of=pd.Timestamp('2026-10-26').date())[0]


def paths(tmp_path,monkeypatch):
    monkeypatch.setattr(release,'ROOT',tmp_path)
    return tmp_path/'data/raw/official_release/probe',tmp_path/'data/processed/final_release/probe'


def test_terms_rejection_records_status_without_exception_or_credentials(tmp_path,monkeypatch):
    output,prepared=paths(tmp_path,monkeypatch)
    response=SimpleNamespace(status_code=403)
    error=requests.HTTPError('Required licences not accepted; secret=sensitive-placeholder',response=response)
    client=Mock(); client.retrieve.side_effect=error
    report=release.retrieve_one(request(),output,prepared,client=client)
    serialized=json.dumps(report)
    assert 'sensitive-placeholder' not in serialized and 'Required licences' not in serialized
    assert report['failure']['reason']=='manual_dataset_terms_or_licence_acceptance_required'
    assert report['failure']['http_status']==403
    assert report['status']['accessible'] is False
    assert not report['status']['downloaded']
    assert not list(output.glob('*.partial'))
    assert not list(prepared.glob('*.nc'))


def test_generic_403_licence_reference_does_not_claim_unaccepted_terms():
    error=requests.HTTPError('Forbidden, see licence documentation',response=SimpleNamespace(status_code=403))
    assert release.safe_failure(error)['reason']=='existing_authorization_rejected'


def test_probe_timeout_cancels_only_its_own_job_and_never_downloads(tmp_path,monkeypatch):
    output,prepared=paths(tmp_path,monkeypatch)
    remote=Mock(request_id='job-1',status='running')
    client=Mock(); client.retrieve.return_value=remote
    times=iter([0,2])
    report=release.retrieve_one(request(),output,prepared,client=client,
        max_wait_seconds=1,clock=lambda:next(times),sleeper=lambda _:None)
    remote.delete.assert_called_once_with(); remote.get_results.assert_not_called()
    assert report['timed_out_job_cancelled']
    assert report['failure']['reason']=='bounded_request_timeout'


def test_provider_job_state_cannot_leak_arbitrary_text(tmp_path,monkeypatch,capsys):
    output,prepared=paths(tmp_path,monkeypatch)
    client=Mock(); client.retrieve.return_value=Mock(request_id='job-1',status='sensitive-placeholder')
    report=release.retrieve_one(request(),output,prepared,client=client)
    assert 'sensitive-placeholder' not in capsys.readouterr().out
    assert 'sensitive-placeholder' not in json.dumps(report)
    assert not report['status']['downloaded']


def test_existing_source_or_manifest_cannot_be_overwritten(tmp_path,monkeypatch):
    output,prepared=paths(tmp_path,monkeypatch)
    output.mkdir(parents=True)
    existing=output/'era5_2025_01_01.manifest.json';existing.write_text('protected')
    client=Mock()
    with pytest.raises(FileExistsError):release.retrieve_one(request(),output,prepared,client=client)
    assert existing.read_text()=='protected'
    client.retrieve.assert_not_called()


def test_wrong_output_scope_fails_before_credential_read(tmp_path,monkeypatch):
    monkeypatch.setattr(release,'ROOT',tmp_path)
    client=Mock()
    with pytest.raises(ValueError,match='isolated'):
        release.retrieve_one(request(),tmp_path/'outside',tmp_path/'also_outside',client=client)
    client.retrieve.assert_not_called()


def test_valid_prepared_source_has_exact_calendar_grid_and_physical_units(tmp_path):
    source=tmp_path/'source.nc'; source_fields().to_netcdf(source,engine='netcdf4')
    metadata=release.validate_prepared(source,request())
    assert metadata['grid']==[129,121]
    assert metadata['months']==1
    assert metadata['finite_values']['temperature_degC']==129*121
    assert metadata['source_step_types']['pev']=='avgad'


@pytest.mark.parametrize('problem',['month','grid'])
def test_changed_month_or_grid_fails_validation(tmp_path,problem):
    dataset=source_fields(('2025-02-01',) if problem=='month' else ('2025-01-01',))
    if problem=='grid':dataset=dataset.assign_coords(longitude=dataset.longitude+.01)
    source=tmp_path/'bad.nc';dataset.to_netcdf(source,engine='netcdf4')
    with pytest.raises(ValueError):release.validate_prepared(source,request())


def test_overlap_distinguishes_new_months_and_actual_array_changes(tmp_path):
    baseline=source_fields(('2024-12-01',)); old=tmp_path/'old.nc';baseline.to_netcdf(old,engine='netcdf4')
    candidate=source_fields(('2024-12-01','2025-01-01')); new=tmp_path/'new.nc';candidate.to_netcdf(new,engine='netcdf4')
    result=release.compare_overlap(new,old)
    assert result['common_months']==['2024-12-01']
    assert result['genuinely_new_source_months']==['2025-01-01']
    assert all(v['exact_values_equal'] for v in result['variables'].values())
    candidate.t2m.values[0,0,0]+=1
    changed=tmp_path/'changed.nc';candidate.to_netcdf(changed,engine='netcdf4')
    result=release.compare_overlap(changed,old)
    assert not result['variables']['t2m']['exact_values_equal']
    assert result['variables']['t2m']['max_absolute_difference_source_units']==1
    assert result['variables']['pev']['exact_values_equal']
