"""Reproducible candidate-only Telangana/Mumbai spatial audit; never ingests.

Reuses the existing strict coordinate resolver and duplicate/conflict auditor.
Station-level evidence stays local; only aggregate diagnostics are published.
"""
import argparse
import hashlib
import json
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
from data_ingestion.cgwb_updates import audit_records
from models.district_registry import get_registry
from models.xgboost_model import sha256_file

ROOT=Path(__file__).resolve().parents[1]


def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    source=ROOT/'data/raw/cgwb_combined.csv';boundary=ROOT/'data/raw/india_districts.geojson'
    raw=pd.read_csv(source,dtype=str)
    geo=gpd.read_file(boundary)
    ts=raw.loc[raw.state_name.str.casefold().eq('telangana')].copy()
    dates=pd.to_datetime(ts.date,format='mixed',errors='coerce')
    records=ts.rename(columns={'currentlevel':'gwl_m_bgl'}).copy()
    records['reported_date']=dates.dt.strftime('%d-%m-%Y')
    records['source_month']=dates.dt.strftime('%Y-%m')
    records['block']='';records['village']=records.station_name
    crosswalk=pd.read_csv(ROOT/'data_ingestion/district_crosswalk.csv',dtype=str)
    boundaries=geo.loc[geo.st_nm.str.casefold().eq('telangana') & geo.district.notna()]
    audit,monthly=audit_records(records,crosswalk,as_of='2026-10-25',boundaries=boundaries)
    # Candidate mean values never replace current model training/inference inputs.
    monthly.to_csv(output/'candidate_telagana_monthly.csv',index=False)
    station_cols=['station_name','latitude','longitude']
    assigned=audit[audit.audit_reason.eq('')]
    mapping=dict(zip(crosswalk.legacy_district_id,crosswalk.canonical_district_id))
    mismatch=assigned.district_code.map(mapping).ne(assigned.district_id)
    rejection={k:v for k,v in audit.audit_reason.str.get_dummies(sep=';').sum().to_dict().items() if k}
    mumbai=geo.loc[geo.district.fillna('').str.casefold().eq('mumbai') & geo.st_nm.eq('Maharashtra')]
    polygon=mumbai.geometry.union_all()
    suburban=raw[raw.district_name.fillna('').str.casefold().str.replace('_',' ').eq('mumbai suburban')]
    xy=suburban[['latitude','longitude']].apply(pd.to_numeric,errors='coerce').dropna().drop_duplicates()
    points=gpd.GeoSeries(gpd.points_from_xy(xy.longitude,xy.latitude),crs='EPSG:4326')
    weather={}
    for name in ['imd_rainfall_district_monthly.csv','era5_district_monthly.csv']:
        p=ROOT/'data/processed'/name;f=pd.read_csv(p)
        rows=f[f.district.fillna('').str.contains('Mumbai',case=False)]
        weather[name]={'source_sha256':sha256_file(p),'district_labels':sorted(rows.district.unique()),
            'spatial_methods':sorted(rows.spatial_method.unique()) if 'spatial_method' in rows else ['not_recorded_in_csv'],
            'max_source_cell_distance_m':float(rows.distance_m.max()) if 'distance_m' in rows else None}
    # Reproduce a source-grid attribution probe, not just a CSV name comparison.
    from data_ingestion.imd_district_climatology import read_grd_file, grid_to_long_monthly
    from data_ingestion.spatial import assign_grid_cells
    grd=ROOT/'data/raw/imd/Rainfall_ind2024_rfp25.grd'
    rain=grid_to_long_monthly(read_grd_file(grd,2024),2024)
    rain=rain[rain.month.eq(1)]
    pts=gpd.GeoDataFrame(rain,geometry=gpd.points_from_xy(rain.longitude,rain.latitude),crs='EPSG:4326')
    cells=assign_grid_cells(pts,mumbai)
    weather['raw_imd_january_2024_probe']={'source_sha256':sha256_file(grd),
        'cells':cells[['latitude','longitude','rainfall_mm','spatial_method','distance_m']].to_dict('records')}
    import xarray as xr
    nc=ROOT/'data/raw/era5/era5_temp_pet_india_2002_2024.nc'
    # The downloaded .nc is a ZIP container; the existing converter also
    # handles this format. Inspect its cleaned runtime artifact without
    # re-extracting over the source archive or changing preprocessing.
    archive_sha=sha256_file(nc)
    import zipfile
    archive_members=zipfile.ZipFile(nc).namelist() if zipfile.is_zipfile(nc) else None
    if archive_members:
        nc=ROOT/'data/processed/era5_india_2002_2024_clean.nc'
    with xr.open_dataset(nc,engine='netcdf4') as ds:
        lon,lat=np.meshgrid(ds.longitude.values,ds.latitude.values)
        tname='t2m_celsius' if 't2m_celsius' in ds else 't2m'
        ename='pev' if 'pev' in ds else 'pet'
        arr=ds[tname].values
        usable=np.isfinite(arr).any(axis=0)&np.isfinite(ds[ename].values).any(axis=0)
        grid=pd.DataFrame({'latitude':lat[usable], 'longitude':lon[usable]})
        pts=gpd.GeoDataFrame(grid,geometry=gpd.points_from_xy(grid.longitude,grid.latitude),crs='EPSG:4326')
        land=gpd.sjoin(pts,geo[['geometry']],how='inner',predicate='within')
        cells=assign_grid_cells(pts.loc[land.index.unique()],mumbai)
        weather['raw_era5_grid_probe']={'source_sha256':sha256_file(nc),
            'download_archive_sha256':archive_sha,'archive_members':archive_members,
            'temperature_units':ds[tname].attrs.get('units'),'evaporation_metadata':{k:str(v) for k,v in ds[ename].attrs.items()},
            'cells':cells[['latitude','longitude','spatial_method','distance_m']].to_dict('records')}
    report={'source_sha256':sha256_file(source),'boundary_sha256':sha256_file(boundary),
        'boundary_crs':str(geo.crs),'boundary_invalid_geometries':int((~geo.is_valid).sum()),
        'boundary_year_labels':sorted(geo.year.dropna().astype(str).unique()),
        'telangana':{'raw_readings':len(ts),'unique_named_coordinates':len(ts[station_cols].drop_duplicates()),
            'accepted_candidate_readings':len(assigned),'candidate_district_months':len(monthly),
            'candidate_districts':monthly.district_id.nunique(),'rejection_reasons':rejection,
            'coordinates_disagree_with_parent_crosswalk_readings':int(mismatch.sum()),
            'candidate_observed_months_by_district':monthly.groupby('district_id').size().to_dict(),
            'publication_status':'not_ingested',
            'limitation':'The boundary carries mixed/undated administrative metadata and station identity/coordinate provenance is not independently certified. Candidate coordinate assignment cannot certify location-specific truth. Existing immutable source/features/model are preserved.'},
        'mumbai_suburban':{'separate_boundary_present':bool(geo.district.fillna('').str.casefold().eq('mumbai suburban').any()),
            'mumbai_polygon_area_km2':float(mumbai.to_crs('+proj=aea +lat_1=12 +lat_2=35 +lat_0=22.5 +lon_0=80 +datum=WGS84 +units=m').area.sum()/1e6),
            'suburban_unique_source_coordinates':len(points),'coordinates_inside_mumbai_polygon':int(points.within(polygon).sum()),
            'weather':weather,'assignment_status':'missing_environment_fallback',
            'limitation':'A single combined-looking polygon and coarse grid resolution do not verify a distinct district boundary or identical spatial weights. No Mumbai-to-Suburban alias or unvalidated nearest-cell transfer is applied.'}}
    (output/'spatial_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,default=ROOT/'reports/nationwide_20261025')
    run(parser.parse_args().output_dir)
