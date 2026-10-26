"""Extract an exact-coordinate Mumbai subset from a pinned official SoI archive.

Stream the 130 MiB national shape member without writing it to disk. Only the
two source records and small sidecars are written to a new ignored directory.
This does not replace the project's historical boundary artifact or mappings.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import time
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from urllib.parse import urlparse
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS,Transformer
from shapely.geometry import Point,Polygon

from data_ingestion.update_weather_sources import sha256

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE_SHA256='b8325e5d9dd0f04a6663d775363fe38cd2f23bd9dbae3fb7118b4e6e0ce0bcb7'
MEMBER='State_District_Subdistrict_PAN INDIA/District_Subdistrict_PAN INDIA/District Boundary'
EXPECTED_IDENTITIES={('MAHARASHTRA','519'):'MUMBAI',('MAHARASHTRA','518'):'MUMBAI SUBURBAN'}
MAX_STREAM_BYTES=160*1024*1024
MAX_SUBSET_BYTES=8*1024*1024
BOUNDARY_URL='https://surveyofindia.gov.in/documents/State_District_Subdistrict_PAN%20INDIA.rar'
METADATA_URL='https://surveyofindia.gov.in/documents/Metadata_ABDB.zip'
METADATA_SHA256='1a14716b73f00fc8391f2708a7975c2f2c1ad4a4e91aafb6dce6546a039e9514'


def acquire_resource(url,target,*,expected_size,expected_sha256,last_modified=None,
                     timeout_seconds=900,opener=urlopen):
    """Create immutable pinned source; resume only verified same-resource ranges."""
    parsed=urlparse(url)
    if (parsed.scheme!='https' or parsed.hostname not in {'surveyofindia.gov.in','www.surveyofindia.gov.in'}
            or parsed.username or parsed.password or parsed.query):
        raise ValueError('Expected a public official SoI HTTPS source without credentials/query')
    if not 0<expected_size<=220*1024*1024 or not 0<timeout_seconds<=900 or not re.fullmatch('[0-9a-f]{64}',expected_sha256):
        raise ValueError('Invalid bounded acquisition metadata')
    target=Path(target).resolve()
    if not target.is_relative_to(ROOT/'data/raw/official_release'):
        raise ValueError('Acquisition requires the isolated official release source tree')
    if target.exists():
        if target.stat().st_size!=expected_size or sha256(target)!=expected_sha256:
            raise ValueError('Cached official source differs from pinned provenance')
        return {'source_url':url,'source_file':str(target.relative_to(ROOT)).replace('\\','/'),
            'sha256':expected_sha256,'size_bytes':expected_size,'cached_source_verified':True,
            'verified_at_utc':datetime.now(timezone.utc).isoformat()}
    target.parent.mkdir(parents=True,exist_ok=True)
    partial=target.with_suffix(target.suffix+'.partial')
    deadline=time.monotonic()+timeout_seconds; attempts=[]
    for attempt in range(4):
        offset=partial.stat().st_size if partial.exists() else 0
        if offset==expected_size:break
        if offset>expected_size:raise ValueError('Existing partial source exceeds declared size')
        if time.monotonic()>=deadline:raise TimeoutError('Bounded source acquisition exceeded')
        headers={'User-Agent':'AquaIQ academic source audit'}
        if offset:
            if last_modified is None:raise ValueError('Cannot resume without a pinned source version')
            headers.update(Range=f'bytes={offset}-',**{'If-Range':last_modified})
        with opener(Request(url,headers=headers),timeout=30) as response:
            observed_modified=response.headers.get('Last-Modified')
            if last_modified and observed_modified!=last_modified:
                raise ValueError('Official source version changed')
            if offset:
                match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
                if response.status!=206 or not match or int(match[1])!=offset or int(match[3])!=expected_size:
                    raise ValueError('Resume requires exact206 Content-Range; no bytes appended')
            elif response.status!=200 or int(response.headers.get('Content-Length','0'))!=expected_size:
                raise ValueError('Source size/status differs from inspected metadata')
            attempts.append({'attempt':attempt+1,'start_offset':offset,'status':response.status,
                'content_range':response.headers.get('Content-Range'),'last_modified':observed_modified})
            with partial.open('ab' if offset else 'xb') as stream:
                while True:
                    if time.monotonic()>=deadline:raise TimeoutError('Bounded source acquisition exceeded')
                    block=response.read(1024*1024)
                    if not block:break
                    offset+=len(block)
                    if offset>expected_size:raise ValueError('Source exceeds inspected size')
                    stream.write(block)
    if not partial.exists() or partial.stat().st_size!=expected_size or sha256(partial)!=expected_sha256:
        raise ValueError('Incomplete or checksum-mismatched source remains quarantined')
    # On Windows rename fails if another process has already created target.
    from data_ingestion.weather_enrichment import publish_new_file
    publish_new_file(partial,target)
    result={'source_url':url,'source_file':str(target.relative_to(ROOT)).replace('\\','/'),
        'sha256':expected_sha256,'size_bytes':expected_size,'acquired_at_utc':datetime.now(timezone.utc).isoformat(),
        'http_attempts':attempts}
    target.with_suffix(target.suffix+'.source.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


def dbf_records(data):
    if len(data)<33:raise ValueError('Truncated DBF header')
    count=struct.unpack('<I',data[4:8])[0]
    header,record_size=struct.unpack('<HH',data[8:12])
    if header<33 or record_size<1 or header+count*record_size>len(data):
        raise ValueError('Invalid DBF record bounds')
    fields=[]
    for position in range(32,header-1,32):
        if data[position]==13:break
        if position+32>header:raise ValueError('Truncated DBF field descriptor')
        fields.append((data[position:position+11].split(b'\0')[0].decode('ascii'),data[position+16]))
    if sum(length for _,length in fields)+1!=record_size:raise ValueError('DBF field lengths mismatch')
    rows=[]
    for index in range(count):
        raw=data[header+index*record_size:header+(index+1)*record_size]
        if raw[:1]!=b' ':raise ValueError('Deleted/unknown DBF rows need explicit review')
        offset=1; row={}
        for name,length in fields:
            row[name]=raw[offset:offset+length].decode('utf-8').strip();offset+=length
        rows.append(row)
    return rows,header,record_size


def _read_exact(stream,size):
    parts=[]; remaining=size
    while remaining:
        part=stream.read(min(1024*1024,remaining))
        if not part:raise ValueError('Truncated shape member')
        parts.append(part);remaining-=len(part)
    return b''.join(parts)


def _discard(stream,size):
    remaining=size
    while remaining:
        block=stream.read(min(1024*1024,remaining))
        if not block:raise ValueError('Truncated shape member')
        remaining-=len(block)


def subset_shape_stream(stream,shx,dbf,indices):
    """Reindex selected raw records; no point coordinate or DBF value changes."""
    rows,dbf_header,dbf_record_size=dbf_records(dbf)
    if not indices or len(set(indices))!=len(indices) or any(i<0 or i>=len(rows) for i in indices):
        raise ValueError('Invalid unique source record indices')
    if len(shx)!=100+8*len(rows) or struct.unpack('>I',shx[:4])[0]!=9994:
        raise ValueError('Shape index record count/header differs from DBF')
    header=bytearray(_read_exact(stream,100))
    total=struct.unpack('>I',header[24:28])[0]*2
    if struct.unpack('>I',header[:4])[0]!=9994 or not 100<total<=MAX_STREAM_BYTES:
        raise ValueError('Unexpected or oversized shape header')
    if header[:24]!=shx[:24] or header[28:100]!=shx[28:100]:
        raise ValueError('Shape and index headers differ')
    blobs=[];source_evidence=[]; position=100
    for index in sorted(indices):
        offset,length=struct.unpack('>II',shx[100+8*index:108+8*index]);offset*=2;length*=2
        if offset<position or offset+8+length>total or length<36:
            raise ValueError('Invalid source record offset/size')
        _discard(stream,offset-position)
        record_header=_read_exact(stream,8); blob=_read_exact(stream,length)
        if struct.unpack('>II',record_header)!=(index+1,length//2):
            raise ValueError('Source record number/length disagrees with shape index')
        if struct.unpack('<I',blob[:4])[0] not in (5,15,25):
            raise ValueError('Expected a district polygon record')
        blobs.append((index,blob));position=offset+8+length
        if sum(len(value)+8 for _,value in blobs)>MAX_SUBSET_BYTES:
            raise ValueError('Selected polygon subset exceeds the explicit bound')
        source_evidence.append({'source_record_index':index,'source_record_bytes':length,
            'raw_record_content_sha256':hashlib.sha256(blob).hexdigest(),'attributes':rows[index]})
    _discard(stream,total-position)
    if stream.read(1):raise ValueError('Shape member contains unexpected trailing bytes')
    # Header metadata is recalculated for the subset; record content is exact.
    boxes=[struct.unpack('<4d',blob[4:36]) for _,blob in blobs]
    header[36:68]=struct.pack('<4d',min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
    shp_header=bytearray(header);shp_header[24:28]=struct.pack('>I',(100+sum(8+len(blob) for _,blob in blobs))//2)
    index_header=bytearray(header);index_header[24:28]=struct.pack('>I',(100+8*len(blobs))//2)
    new_shape=bytes(shp_header);new_index=bytes(index_header);offset=50
    for number,(_,blob) in enumerate(blobs,1):
        new_shape+=struct.pack('>II',number,len(blob)//2)+blob
        new_index+=struct.pack('>II',offset,len(blob)//2);offset+=4+len(blob)//2
    new_dbf=bytearray(dbf[:dbf_header]);new_dbf[4:8]=struct.pack('<I',len(blobs))
    for index,_ in blobs:new_dbf+=dbf[dbf_header+index*dbf_record_size:dbf_header+(index+1)*dbf_record_size]
    return new_shape,new_index,bytes(new_dbf)+b'\x1a',source_evidence


def subset_soi(archive,output,*,tar='C:/Windows/System32/tar.exe'):
    archive,output=Path(archive).resolve(),Path(output).resolve()
    if sha256(archive)!=ARCHIVE_SHA256:raise ValueError('Official boundary archive hash changed; review before use')
    if output.exists() or not output.is_relative_to(ROOT/'data/processed/final_release'):
        raise ValueError('Choose a new isolated derived boundary directory')
    sidecars={}
    for extension in ('dbf','shx','prj','cpg'):
        value=subprocess.run([tar,'-xOf',str(archive),MEMBER+'.'+extension],capture_output=True,check=True).stdout
        if len(value)>1024*1024:raise ValueError('Unexpected source sidecar size')
        sidecars[extension]=value
    rows,_,_=dbf_records(sidecars['dbf'])
    indices=[i for i,row in enumerate(rows) if (row.get('STATE_UT'),row.get('DIST_LGD')) in EXPECTED_IDENTITIES]
    if len(indices)!=2 or any(rows[i]['DISTRICT']!=EXPECTED_IDENTITIES[(rows[i]['STATE_UT'],rows[i]['DIST_LGD'])] for i in indices):
        raise ValueError('Expected exact Maharashtra district identities519/518 were not found')
    process=subprocess.Popen([tar,'-xOf',str(archive),MEMBER+'.shp'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        shp,shx,dbf,evidence=subset_shape_stream(process.stdout,sidecars['shx'],sidecars['dbf'],indices)
        process.stdout.close()
        if process.wait(timeout=60)!=0:raise ValueError('Official archive failed member integrity/decompression')
    finally:
        if process.poll() is None:process.kill();process.wait()
        if process.stderr:process.stderr.close()
    output.mkdir(parents=True)
    values={'shp':shp,'shx':shx,'dbf':dbf,'prj':sidecars['prj'],'cpg':sidecars['cpg']}
    for extension,value in values.items():(output/('mumbai_districts.'+extension)).write_bytes(value)
    report={'source_archive_sha256':ARCHIVE_SHA256,'source_member':MEMBER,
        'national_geometry_bytes_written':0,'subset_bytes_written':sum(len(value) for value in values.values()),
        'source_records':len(rows),'selected_records':evidence,'coordinate_values_changed':False,
        'source_crs_wkt':sidecars['prj'].decode(),'output_sha256':{name:sha256(output/name) for name in sorted(path.name for path in output.iterdir())}}
    (output/'subset_manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


def weather_attribution_audit(subset,output):
    """Quantify source-grid resolution and alternatives without filling features."""
    import xarray as xr
    from data_ingestion.spatial import assign_grid_cells
    from data_ingestion.era5_to_district import evaporation_monthly
    from data_ingestion.imd_district_climatology import find_grd_files

    subset,output=Path(subset),Path(output)
    if output.exists() or not output.resolve().is_relative_to(ROOT/'data/processed/final_release'):
        raise ValueError('Choose a new isolated weather-attribution audit directory')
    districts=gpd.read_file(subset/'mumbai_districts.shp')
    if len(districts)!=2 or not districts.is_valid.all() or districts.crs is None:
        raise ValueError('Expected two valid, explicitly referenced Mumbai polygons')
    native=districts.copy();native['source_area_km2']=native.area/1e6
    districts=districts.to_crs(4326).rename(columns={'DISTRICT':'district','STATE_UT':'st_nm'})
    mapping={'519':'MH-Mumbai','518':'MH-Mumbai_Suburban'}
    districts['district_id']=districts.DIST_LGD.map(mapping)
    if districts.district_id.isna().any():raise ValueError('Unknown exact source district code')
    old_boundary=ROOT/'data/raw/india_districts.geojson'
    old=gpd.read_file(old_boundary);old=old.loc[old.district.notna()]
    nc=ROOT/'data/processed/era5_india_2002_2024_clean.nc'
    output.mkdir(parents=True)
    rows=[]; footprint_rows=[]; summaries=[]
    with xr.open_dataset(nc,engine='netcdf4') as source:
        time_name='valid_time' if 'valid_time' in source.coords else 'time'
        dates=pd.DatetimeIndex(source[time_name].values)
        temp=source.t2m.values-np.float32(273.15)
        pet=evaporation_monthly(source.pev.values,dict(source.pev.attrs),dates)
        lons,lats=np.meshgrid(source.longitude.values,source.latitude.values)
        points=gpd.GeoDataFrame({'latitude':lats.ravel(),'longitude':lons.ravel(),
            'lat_idx':np.repeat(np.arange(len(source.latitude)),len(source.longitude)),
            'lon_idx':np.tile(np.arange(len(source.longitude)),len(source.latitude))},
            geometry=gpd.points_from_xy(lons.ravel(),lats.ravel()),crs=4326)
        usable=np.isfinite(temp).any(axis=0)&np.isfinite(pet).any(axis=0)
        usable_points=points[usable[points.lat_idx,points.lon_idx]]
        # Preserve the old processor's usable-land rule for this comparison.
        on_land=gpd.sjoin(usable_points,old[['geometry']].to_crs(4326),how='inner',predicate='within')
        usable_points=usable_points.loc[on_land.index.unique()]
        assigned=assign_grid_cells(usable_points,districts)
        for index,district in districts.iterrows():
            did=district.district_id
            selected=assigned.loc[assigned._dist_key.eq(district.st_nm+'___'+district.district)]
            li,lo=selected.lat_idx.to_numpy(),selected.lon_idx.to_numpy()
            nearest_temp=np.nanmean(temp[:,li,lo],axis=1);nearest_pet=np.nanmean(pet[:,li,lo],axis=1)
            # Source-cell footprints are geometric diagnostics. This area-weight
            # alternative differs from the frozen center-point/nearest features.
            candidates=points.loc[points.longitude.between(district.geometry.bounds[0]-.125,district.geometry.bounds[2]+.125)
                &points.latitude.between(district.geometry.bounds[1]-.125,district.geometry.bounds[3]+.125)]
            weights=[]; cell_indices=[]; geometry=native.loc[index].geometry
            for cell in candidates.itertuples():
                x0,x1=cell.longitude-.125,cell.longitude+.125;y0,y1=cell.latitude-.125,cell.latitude+.125
                edge=np.linspace(0,1,17)
                coordinates=[(x0+(x1-x0)*t,y0) for t in edge]+[(x1,y0+(y1-y0)*t) for t in edge[1:]]
                coordinates += [(x1-(x1-x0)*t,y1) for t in edge[1:]]+[(x0,y1-(y1-y0)*t) for t in edge[1:]]
                polygon=gpd.GeoSeries([Polygon(coordinates)],crs=4326).to_crs(native.crs).iloc[0]
                area=polygon.intersection(geometry).area
                if area<=0:continue
                weights.append(area);cell_indices.append((cell.lat_idx,cell.lon_idx))
                footprint_rows.append({'district_id':did,'latitude':cell.latitude,'longitude':cell.longitude,
                    'intersection_area_km2_in_source_lcc':area/1e6,'fraction_of_source_polygon':area/geometry.area,
                    'center_within_polygon':bool(cell.geometry.within(district.geometry)),
                    'both_source_fields_ever_usable':bool(usable[cell.lat_idx,cell.lon_idx])})
            weights=np.asarray(weights)
            fl=np.array([i for i,j in cell_indices]);fo=np.array([j for i,j in cell_indices])
            values_temp=temp[:,fl,fo];values_pet=pet[:,fl,fo]
            valid=np.isfinite(values_temp)&np.isfinite(values_pet)
            denominators=(valid*weights).sum(axis=1)
            weighted_temp=np.divide(np.where(valid,values_temp,0)@weights,denominators,
                out=np.full(len(dates),np.nan),where=denominators>0)
            weighted_pet=np.divide(np.where(valid,values_pet,0)@weights,denominators,
                out=np.full(len(dates),np.nan),where=denominators>0)
            for t,date in enumerate(dates):
                rows.append({'district_id':did,'date':date,'nearest_grid_temperature_degC':nearest_temp[t],
                    'nearest_grid_pet_mm_month':nearest_pet[t],'alternative_available_area_temperature_degC':weighted_temp[t],
                    'alternative_available_area_pet_mm_month':weighted_pet[t],
                    'alternative_finite_area_fraction':denominators[t]/geometry.area,
                    'role':'diagnostic_grid_proxy_not_independent_district_observation'})
            summaries.append({'district_id':did,'source_name':district.district,'source_lgd_code':district.DIST_LGD,
                'geometry_valid':True,'native_projected_area_km2':native.loc[index,'source_area_km2'],
                'geographic_bounds':[float(v) for v in district.geometry.bounds],
                'interior_usable_grid_centers':int((usable_points.geometry.within(district.geometry)).sum()),
                'selected_cells':selected[['latitude','longitude','spatial_method','distance_m']].to_dict('records'),
                'source_cell_footprints_overlapping':len(weights),'diagnostic_months':len(dates),
                'alternative_finite_area_fraction_min':float((denominators/geometry.area).min()),
                'alternative_finite_area_fraction_max':float((denominators/geometry.area).max()),
                'alternative_vs_nearest_max_difference_degC':float(np.nanmax(np.abs(weighted_temp-nearest_temp))),
                'alternative_vs_nearest_max_difference_pet_mm_month':float(np.nanmax(np.abs(weighted_pet-nearest_pet)))})
    proxy=pd.DataFrame(rows);proxy.to_csv(output/'era5_proxy_diagnostics.csv',index=False)
    pd.DataFrame(footprint_rows).to_csv(output/'era5_footprint_cells.csv',index=False)
    # All historical IMD years are local. Aggregate exactly complete calendar
    # months, caching only spatial assignments for identical usable-cell masks.
    rainfall=[]; rain_sources=[]; rain_assignments={}; cache={}
    grid_lats=6.5+np.arange(129)*.25;grid_lons=66.5+np.arange(135)*.25
    glon,glat=np.meshgrid(grid_lons,grid_lats)
    rain_points=gpd.GeoDataFrame({'latitude':glat.ravel(),'longitude':glon.ravel(),
        'lat_idx':np.repeat(np.arange(129),135),'lon_idx':np.tile(np.arange(135),129)},
        geometry=gpd.points_from_xy(glon.ravel(),glat.ravel()),crs=4326)
    for year,path in find_grd_files(ROOT/'data/raw/imd'):
        days=pd.date_range(f'{year}-01-01',f'{year}-12-31')
        if Path(path).stat().st_size!=len(days)*129*135*4:raise ValueError('Invalid existing IMD source byte count')
        raw=np.memmap(path,dtype='<f4',mode='r',shape=(len(days),129,135))
        for month in range(1,13):
            values=np.asarray(raw[days.month==month]); valid=np.isfinite(values)&(values>=0)&(values<=10000)
            totals=np.where(valid.all(axis=0),np.where(valid,values,0).sum(axis=0),np.nan)
            mask=np.isfinite(totals);key=np.packbits(mask).tobytes()
            if key not in cache:cache[key]=assign_grid_cells(rain_points.loc[mask.ravel()],districts)
            selected=cache[key]
            for did,district in districts.set_index('district_id').iterrows():
                chosen=selected.loc[selected._dist_key.eq(district.st_nm+'___'+district.district)]
                cells=chosen[['latitude','longitude','spatial_method','distance_m']].to_dict('records')
                rain_assignments.setdefault(did,{})[str([(x['latitude'],x['longitude']) for x in cells])]=cells
                rainfall.append({'district_id':did,'date':f'{year}-{month:02d}-01',
                    'rainfall_grid_proxy_mm_month':float(np.mean(totals[chosen.lat_idx,chosen.lon_idx])),
                    'n_source_cells':len(chosen),'role':'diagnostic_grid_proxy_not_independent_district_observation'})
        del raw
        rain_sources.append({'year':year,'sha256':sha256(Path(path)),'size_bytes':Path(path).stat().st_size})
    rain=pd.DataFrame(rainfall);rain.to_csv(output/'imd_proxy_diagnostics.csv',index=False)
    representative=[geometry.representative_point() for geometry in native.geometry]
    actual=Transformer.from_crs(native.crs,4326,always_xy=True);declared=Transformer.from_crs(7755,4326,always_xy=True)
    report={'source_archive_sha256':ARCHIVE_SHA256,'baseline_boundary_sha256':sha256(old_boundary),
        'baseline_era5_sha256':sha256(nc),'source_crs_wkt':native.crs.to_wkt(),
        'source_prj_exactly_equals_metadata_epsg7755':bool(native.crs.equals(CRS.from_epsg(7755))),
        'source_prj_used_without_overriding':True,
        'crs_comparison_at_representative_points':[{'source_prj_lon_lat':actual.transform(point.x,point.y),
            'forced_metadata_epsg_lon_lat':declared.transform(point.x,point.y)} for point in representative],
        'era5_districts':summaries,'imd_distinct_assignment_patterns':rain_assignments,
        'imd_source_years':rain_sources,'imd_proxy_months_per_district':rain.groupby('district_id').size().to_dict(),
        'era5_proxy_start':str(proxy.date.min().date()),'era5_proxy_end':str(proxy.date.max().date()),
        'new_weather_grid_observations_acquired':0,'new_groundwater_observations':0,'production_features_changed':False,
        'decision':'Do not fill Mumbai Suburban from a shared out-of-district coarse cell. Footprint-area weighting uses offshore-centered cells and changes the trained center-point/nearest definition; it needs a separate artifact/protocol before any skill claim.',
        'historical_accuracy_evaluation':'Not promoted or scored as a trained district model: target-feature training values would change and the existing frozen compatibility proof requires unchanged historical weather. Existing holdout has already been inspected.',
        'output_sha256':{path.name:sha256(path) for path in sorted(output.glob('*.csv'))}}
    (output/'weather_attribution.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--acquire-dir',type=Path,help='Explicit pinned SoI acquisition; no overwrite, bounded byte-range resume')
    parser.add_argument('--weather-audit',type=Path,help='Create new diagnostic source-grid artifacts from this subset')
    args=parser.parse_args()
    if args.acquire_dir:
        if args.archive or args.output or args.weather_audit:parser.error('--acquire-dir is a separate explicit network step')
        print(json.dumps(acquire_resource(BOUNDARY_URL,args.acquire_dir/'SoI_ABDB_2025.rar',
            expected_size=202524438,expected_sha256=ARCHIVE_SHA256,last_modified='Tue, 12 May 2026 08:51:34 GMT'),indent=2))
        print(json.dumps(acquire_resource(METADATA_URL,args.acquire_dir/'Metadata_ABDB.zip',
            expected_size=38879,expected_sha256=METADATA_SHA256,last_modified='Fri, 29 May 2026 04:41:24 GMT'),indent=2))
    elif not args.archive or not args.output:parser.error('--archive and --output are required for offline subset/audit')
    elif args.weather_audit:
        print(json.dumps(weather_attribution_audit(args.output,args.weather_audit),indent=2))
    else:
        print(json.dumps(subset_soi(args.archive,args.output),indent=2))
