"""Bounded authorized ERA5 retrieval and explicit release-weather validation.

No client, credential read, network access or writes occur on import. This CLI
only creates isolated source/derived files; deployed weather and models stay put.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import time
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from data_ingestion.update_weather_sources import ERA5_DATASET, era5_requests, sha256
from data_ingestion.era5_to_district import prepare_era5_nc, evaporation_monthly
from data_ingestion.weather_enrichment import publish_new_file

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'authorized-era5-release-v1'
DATASET_URL = 'https://cds.climate.copernicus.eu/datasets/' + ERA5_DATASET


def safe_failure(error):
    """Classify provider failures without serializing exception text or secrets."""
    response = getattr(error, 'response', None)
    status = getattr(response, 'status_code', None)
    message = str(error).lower()  # inspected in memory only; never returned
    licence_required = ('required licences' in message or 'required licenses' in message) and 'not accepted' in message
    if licence_required or ('terms' in message and 'must accept' in message):
        reason = 'manual_dataset_terms_or_licence_acceptance_required'
    elif status in (401,403) or any(word in message for word in ('unauthorized','authentication','invalid credentials')):
        reason = 'existing_authorization_rejected'
    elif 'timed out' in message or isinstance(error, TimeoutError):
        reason = 'bounded_request_timeout'
    else:
        reason = 'retrieval_or_validation_failed'
    return {'exception_type':type(error).__name__, 'http_status':status, 'reason':reason,
            'credential_values_logged':False}


def _quiet(*args, **kwargs):
    return None


def authorized_client():
    import cdsapi
    logging.getLogger('cdsapi').setLevel(logging.CRITICAL)
    logging.getLogger('ecmwf.datastores').setLevel(logging.CRITICAL)
    client = cdsapi.Client(quiet=True,debug=False,verify=True,timeout=20,
        progress=False,retry_max=1,sleep_max=5,wait_until_complete=False,
        info_callback=_quiet,warning_callback=_quiet,error_callback=_quiet,debug_callback=_quiet)
    url = urlparse(client.url)
    if (url.scheme != 'https' or url.hostname != 'cds.climate.copernicus.eu'
            or url.username or url.password or url.query):
        raise ValueError('CDS configuration must use the official public HTTPS API endpoint')
    return client


def validate_prepared(path, request):
    import xarray as xr
    expected = pd.DatetimeIndex([f"{request['year'][0]}-{month}-01" for month in request['month']])
    with xr.open_dataset(path,engine='netcdf4') as ds:
        time_name = 'valid_time' if 'valid_time' in ds.coords else 'time'
        times = pd.DatetimeIndex(ds[time_name].values)
        if not times.equals(expected):
            raise ValueError('Prepared ERA5 calendar differs from requested complete months')
        if (not np.array_equal(ds.latitude.values,np.arange(38,5.99,-.25))
                or not np.array_equal(ds.longitude.values,np.arange(68,98.01,.25))):
            raise ValueError('ERA5 source differs from the existing full India quarter-degree grid')
        values = {'temperature_degC':ds.t2m.values - np.float32(273.15),
            'evapotranspiration_mm_month':evaporation_monthly(ds.pev.values,dict(ds.pev.attrs),times)}
        return {'months':len(times),'date_start':str(times[0].date()),'date_end':str(times[-1].date()),
            'grid':[len(ds.latitude),len(ds.longitude)],'coordinate_system':'source latitude/longitude degrees',
            'units':{'t2m':'K','pev':'m monthly-mean daily accumulation','temperature':'degC','evapotranspiration':'mm/month'},
            'finite_values':{name:int(np.isfinite(value).sum()) for name,value in values.items()},
            'source_step_types':{name:ds[name].attrs.get('GRIB_stepType') for name in ('t2m','pev')}}


def compare_overlap(prepared, baseline):
    """Compare common actual source months/arrays; never overwrite the baseline."""
    import xarray as xr
    with xr.open_dataset(prepared,engine='netcdf4') as new, xr.open_dataset(baseline,engine='netcdf4') as old:
        nt='valid_time' if 'valid_time' in new.coords else 'time'
        ot='valid_time' if 'valid_time' in old.coords else 'time'
        if not np.array_equal(new.latitude,old.latitude) or not np.array_equal(new.longitude,old.longitude):
            raise ValueError('Overlap comparison requires the same source grid')
        common=pd.DatetimeIndex(new[nt].values).intersection(pd.DatetimeIndex(old[ot].values))
        fields={}
        for variable in ('t2m','pev'):
            a=new[variable].sel({nt:common}).values; b=old[variable].sel({ot:common}).values
            paired=np.isfinite(a)&np.isfinite(b)
            fields[variable]={'paired_values':int(paired.sum()),
                'missing_mask_equal':bool(np.array_equal(np.isfinite(a),np.isfinite(b))),
                'exact_values_equal':bool(np.array_equal(a,b,equal_nan=True)),
                'max_absolute_difference_source_units':float(np.abs(a[paired]-b[paired]).max()) if paired.any() else None}
        old_dates=pd.DatetimeIndex(old[ot].values)
        new_dates=pd.DatetimeIndex(new[nt].values)
        return {'baseline_sha256':sha256(Path(baseline)), 'common_months':[str(x.date()) for x in common],
            'genuinely_new_source_months':[str(x.date()) for x in new_dates.difference(old_dates)],'variables':fields}


def retrieve_one(request, source_dir, prepared_dir, *, max_wait_seconds=180,
                 max_bytes=32*1024*1024, client=None, sleeper=time.sleep, clock=time.monotonic):
    """Use existing user authorization; never accept terms or print job URLs."""
    source_dir, prepared_dir = Path(source_dir).resolve(),Path(prepared_dir).resolve()
    if not source_dir.is_relative_to(ROOT/'data/raw/official_release') or not prepared_dir.is_relative_to(ROOT/'data/processed/final_release'):
        raise ValueError('Release weather outputs require explicit isolated source and prepared directories')
    if not 0 < max_wait_seconds <= 900 or not 0 < max_bytes <= 32*1024*1024:
        raise ValueError('Invalid bounded wait/size limits')
    stem=f"era5_{request['year'][0]}_{request['month'][0]}_{request['month'][-1]}"
    source=source_dir/(stem+'.nc'); prepared=prepared_dir/(stem+'_prepared.nc')
    manifest_path=source_dir/(stem+'.manifest.json')
    if any(p.exists() for p in (source,prepared,manifest_path)):
        raise FileExistsError('Choose fresh release output paths; no source or candidate is overwritten')
    source_dir.mkdir(parents=True,exist_ok=True); prepared_dir.mkdir(parents=True,exist_ok=True)
    report={'version':VERSION,'dataset':ERA5_DATASET,'dataset_url':DATASET_URL,'request':request,
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'license':'CC-BY-4.0 per official catalogue',
        'credential_configuration':'existing user-managed CDS configuration; values never serialized',
        'manual_terms_accepted_by_agent':False,'status':{'discovered':True,'accessible':None,'downloaded':False,'parsed':False,'integrated':False,'validated':False}}
    remote=None; partial=source.with_suffix('.partial')
    try:
        client=client or authorized_client()
        remote=client.retrieve(ERA5_DATASET,request)
        report['status']['accessible']=True
        report['request_id_sha256']=hashlib.sha256(str(remote.request_id).encode()).hexdigest()
        started=clock(); last=None
        while True:
            state=remote.status
            if state not in {'accepted','running','successful','failed','dismissed','rejected'}:
                raise ValueError('Unrecognized CDS job state')
            if state!=last:
                print(f'CDS request state: {state}',flush=True);last=state
            if state=='successful':break
            if state in ('failed','dismissed','rejected'):
                raise RuntimeError('Provider job did not produce a successful result')
            if clock()-started>=max_wait_seconds:
                try: remote.delete(); report['timed_out_job_cancelled']=True
                except Exception: report['timed_out_job_cancelled']=False
                raise TimeoutError('Bounded CDS processing wait exceeded')
            sleeper(min(5,max_wait_seconds))
        result=remote.get_results()
        if int(result.content_length)>max_bytes:
            raise ValueError('Result exceeds bounded download size')
        import requests
        size=0
        # Download URL can contain temporary signatures. Never log or store it,
        # and never forward the user's CDS Authorization header to cloud assets.
        with requests.get(result.location,stream=True,timeout=(10,45)) as response:
            response.raise_for_status()
            with partial.open('xb') as stream:
                for block in response.iter_content(1024*1024):
                    size+=len(block)
                    if size>max_bytes:raise ValueError('Result exceeds bounded download size')
                    stream.write(block)
        if size!=int(result.content_length):raise ValueError('CDS result content length mismatch')
        publish_new_file(partial,source)
        report['status']['downloaded']=True
        report.update(source_file=str(source.relative_to(ROOT)).replace('\\','/'),sha256=sha256(source),size_bytes=size)
        prepare_era5_nc(source,prepared)
        report['validation']=validate_prepared(prepared,request)
        report['status'].update(parsed=True,validated=True)
        report['prepared_file']=str(prepared.relative_to(ROOT)).replace('\\','/')
        report['prepared_sha256']=sha256(prepared)
    except Exception as error:
        report['failure']=safe_failure(error)
        if report['failure']['http_status'] in (401,403):
            report['status']['accessible']=False
            report['authenticated_api_reachable']=True
    finally:
        partial.unlink(missing_ok=True)
    manifest_path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--start',required=True);p.add_argument('--end',required=True)
    p.add_argument('--source-dir',type=Path,required=True);p.add_argument('--prepared-dir',type=Path,required=True)
    p.add_argument('--max-wait-seconds',type=int,default=180)
    a=p.parse_args(argv)
    for request in era5_requests(a.start,a.end):
        report=retrieve_one(request,a.source_dir,a.prepared_dir,max_wait_seconds=a.max_wait_seconds)
        print(json.dumps(report,indent=2,allow_nan=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
