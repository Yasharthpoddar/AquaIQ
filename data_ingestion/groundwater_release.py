"""Missing-month recovery from the already verified CGWB January 2025 archive.

Offline only: preserve current measured means, quarantine ambiguous locations,
and never pool potentially mirrored products within an existing district month.
No database, deployed feature export or model writes occur here.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from data_ingestion.cgwb_updates import (build_district_lookup, normalized_state,
    resolve_district, spatial_districts)
from data_ingestion.nwdp_manual import _label, sha256, BOUNDARY_MARGIN_DEGREES, MAX_REVIEW_DEPTH_M

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'cgwb-nwdp-missing-month-merge-v1'
EXTRACTION = ROOT/'reports/candidates/station_history_20261015/january_2025_verified'
PDF = ROOT/'data/raw/updates/20261015/cgwb/January_WL_1994-2025.pdf'
NWDP = ROOT/'reports/candidates/groundwater_updates/enrichment_20261026/nwdp_manual_v1'
FEATURES = ROOT/'data/processed/enrichment/nwdp_manual_20261026_v1/features_matrix.csv'


def repository_path(path):
    """Portable metadata for inputs restored under the release checkout."""
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def load_verified_pdf_records(extraction=EXTRACTION, pdf_path=PDF):
    extraction, pdf_path = Path(extraction), Path(pdf_path)
    manifest = json.loads((extraction/'extraction_manifest.json').read_text(encoding='utf-8'))
    csv_path = extraction/'station_records.csv'
    if (sha256(pdf_path) != manifest.get('source_sha256')
            or sha256(csv_path) != manifest.get('records_sha256')
            or manifest.get('extracted_pages') != [1,332]
            or manifest.get('archive_pages') != 10574
            or manifest.get('selected_observation_month') != '2025-01'
            or manifest.get('units') != 'm_bgl'):
        raise ValueError('January archive/extraction differs from its verified source chain')
    records = pd.read_csv(csv_path, keep_default_na=False)
    if (len(records) != manifest['rows'] or not records.source_sha256.eq(manifest['source_sha256']).all()
            or not records.source_month.eq('2025-01').all()
            or not records.source_page.between(1,332).all() or not records.units.eq('m_bgl').all()):
        raise ValueError('January source rows disagree with the extraction manifest')
    return records, manifest


def observed_keys(features):
    required = {'district_id','date','is_observed'}
    if required-set(features):
        raise ValueError('Current snapshot lacks explicit observation provenance')
    flags = features.is_observed.astype('string').str.lower().map({'true':True,'false':False,'1':True,'0':False})
    dates = pd.to_datetime(features.date, errors='coerce')
    if flags.isna().any() or dates.isna().any() or not dates.dt.is_month_start.all() or features.duplicated(['district_id','date']).any():
        raise ValueError('Current snapshot has unknown flags, dates or duplicate months')
    return set(zip(features.loc[flags,'district_id'],dates.loc[flags]))


def audit_pdf_records(records, crosswalk, boundaries, *, as_of, boundary_margin=BOUNDARY_MARGIN_DEGREES):
    """Audit source-specific named locations; do not assert physical well IDs."""
    if records.empty or not np.isfinite(boundary_margin) or boundary_margin < BOUNDARY_MARGIN_DEGREES:
        raise ValueError('Nonempty source and declared conservative boundary margin required')
    frame = records.copy().reset_index(drop=True)
    reasons = [[] for _ in range(len(frame))]
    def reject(mask, reason):
        for index in frame.index[pd.Series(mask,index=frame.index).fillna(True)]:
            reasons[index].append(reason)
    for column in ['latitude','longitude','gwl_m_bgl']:
        frame[column] = pd.to_numeric(frame[column],errors='coerce')
    frame['observation_date'] = pd.to_datetime(frame.reported_date,format='%d-%m-%Y',errors='coerce')
    frame['date'] = frame.observation_date.dt.to_period('M').dt.to_timestamp()
    reject(frame.observation_date.isna(),'invalid_reported_date')
    reject(frame.observation_date.gt(pd.Timestamp(as_of).normalize()),'future_observation')
    reject(frame.observation_date.dt.strftime('%Y-%m').fillna('').ne('2025-01') | frame.source_month.ne('2025-01'),'unverified_source_month')
    reject(frame.units.ne('m_bgl'),'unverified_depth_units')
    reject(~np.isfinite(frame.gwl_m_bgl),'nonfinite_depth')
    reject(frame.gwl_m_bgl.lt(0),'negative_depth_review')
    reject(frame.gwl_m_bgl.gt(MAX_REVIEW_DEPTH_M),'depth_over_300m_review')
    reject(~np.isfinite(frame.latitude) | ~frame.latitude.between(6,38)
        | ~np.isfinite(frame.longitude) | ~frame.longitude.between(68,98),'invalid_india_coordinates')
    labels = frame[['block','village']].fillna('').map(_label)
    reject(labels.isin(['','-']).any(axis=1),'incomplete_source_location_label')
    lookup = build_district_lookup(crosswalk)
    assignments = spatial_districts(frame,boundaries,lookup)
    frame['district_id'] = [item[0] for item in assignments]
    frame['mapping_basis'] = [item[1] for item in assignments]
    reject(frame.district_id.isna(),'unresolved_canonical_district')
    reject([pd.notna(did) and normalized_state(lookup['canonical'][did][1]) != normalized_state(state)
        for did,state in zip(frame.district_id,frame.state_name)],'source_state_disagrees_with_boundary')
    polygons = boundaries.loc[boundaries.district.notna() & boundaries.district.astype(str).str.strip().ne('')].to_crs('EPSG:4326').copy()
    polygons['canonical_id'] = [resolve_district(row.st_nm,row.district,lookup)[0] for row in polygons.itertuples()]
    geometries = polygons.dissolve(by='canonical_id').geometry.to_dict()
    from shapely.geometry import Point
    reject([bool(pd.notna(did) and np.isfinite(lat) and np.isfinite(lon)
        and Point(lon,lat).distance(geometries[did].boundary) <= boundary_margin)
        for did,lat,lon in zip(frame.district_id,frame.latitude,frame.longitude)],'near_boundary_coordinate_review')
    frame['coordinate_key'] = [json.dumps([normalized_state(state),f'{lat:.5f}',f'{lon:.5f}'])
        for state,lat,lon in zip(frame.state_name,frame.latitude,frame.longitude)]
    frame['location_label'] = labels.astype(str).agg('|'.join,axis=1)
    # No source district component: a rename does not identify another well.
    frame['station_key'] = [hashlib.sha256((coord+'|'+label).encode()).hexdigest()
        for coord,label in zip(frame.coordinate_key,frame.location_label)]
    aliases = frame.groupby(['coordinate_key','date'],dropna=False).location_label.transform('nunique').gt(1)
    reject(aliases,'ambiguous_colocated_location_labels')
    identity = ['station_key','observation_date']
    conflicts = frame.groupby(identity,dropna=False).gwl_m_bgl.transform('nunique').gt(1)
    reject(conflicts,'conflicting_location_date_depths')
    reject(frame.duplicated(identity+['gwl_m_bgl'],keep='first') & ~conflicts,'duplicate_location_date_depth')
    frame['audit_reason'] = [';'.join(values) for values in reasons]
    return frame


def aggregate_pdf(audit):
    accepted = audit.loc[audit.audit_reason.eq('')]
    station = accepted.groupby(['district_id','date','station_key'],as_index=False).agg(
        gwl=('gwl_m_bgl','mean'),reading_count=('gwl_m_bgl','size'),
        first_observation_date=('observation_date','min'),last_observation_date=('observation_date','max'))
    monthly = station.groupby(['district_id','date'],as_index=False).agg(gwl_mean=('gwl','mean'),
        station_count=('station_key','size'),reading_count=('reading_count','sum'),
        first_observation_date=('first_observation_date','min'),last_observation_date=('last_observation_date','max'))
    for key,value in {'source':'CGWB','metric':'GWL','units':'m_bgl','is_observed':True,
            'date_basis':'calendar_month_of_source_reported_observation_date',
            'provenance_product':'CGWB_January_2025_unconfined_PDF'}.items():
        monthly[key]=value
    return station,monthly


def build(output, *, as_of='2026-10-26', current_features=FEATURES, nwdp_directory=NWDP,
        extraction=EXTRACTION, pdf_path=PDF):
    """Publish candidate files only, with strict missing-month source precedence."""
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to((ROOT/'reports/candidates/groundwater_updates').resolve()):
        raise ValueError('Choose a new ignored groundwater-update candidate directory')
    current_features,nwdp_directory = Path(current_features),Path(nwdp_directory)
    feature_manifest = json.loads(current_features.with_name('feature_manifest.json').read_text(encoding='utf-8'))
    if sha256(current_features) != feature_manifest['feature_csv_sha256']:
        raise ValueError('Current feature snapshot checksum changed')
    nwdp_manifest = json.loads((nwdp_directory/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in nwdp_manifest['output_sha256'].items():
        if sha256(nwdp_directory/name) != digest:
            raise ValueError('NWDP parent evidence checksum changed')
    records,extraction_manifest = load_verified_pdf_records(extraction,pdf_path)
    crosswalk = pd.read_csv(ROOT/'data_ingestion/district_crosswalk.csv',dtype=str,keep_default_na=False)
    import geopandas as gpd
    boundaries = gpd.read_file(ROOT/'data/raw/india_districts.geojson')
    audit = audit_pdf_records(records,crosswalk,boundaries,as_of=as_of)
    station,monthly = aggregate_pdf(audit)
    features = pd.read_csv(current_features,usecols=['district_id','date','is_observed'])
    keys = observed_keys(features)
    monthly['already_observed_current'] = [(did,date) in keys for did,date in zip(monthly.district_id,monthly.date)]
    additions = monthly.loc[~monthly.already_observed_current].drop(columns='already_observed_current').copy()
    parent = pd.read_csv(nwdp_directory/'canonical_district_month_candidates.csv',parse_dates=['date','first_observation_date','last_observation_date'])
    if set(zip(parent.district_id,parent.date)) & set(zip(additions.district_id,additions.date)):
        raise ValueError('Missing-month precedence failed: products would be pooled')
    combined = pd.concat([parent,additions],ignore_index=True).sort_values(['district_id','date'])
    selected_keys = set(zip(additions.district_id,additions.date))
    audit['integration_decision'] = ['retained_current_measured_month' if (did,date) in keys else
        'additional_missing_measured_month' if not reason and (did,date) in selected_keys else 'quarantined_source_row'
        for did,date,reason in zip(audit.district_id,audit.date,audit.audit_reason)]
    zero = set(features.district_id)-{did for did,_ in keys}
    recovered = sorted(set(additions.district_id)&zero)
    output.mkdir(parents=True,exist_ok=False)
    frames = {'station_records.csv':records,'station_audit.csv':audit,
        'accepted_station_records.csv':audit.loc[audit.audit_reason.eq('')],
        'rejected_station_records.csv':audit.loc[audit.audit_reason.ne('')],
        'station_months.csv':station,'additional_district_month_candidates.csv':additions,
        'canonical_district_month_candidates.csv':combined}
    hashes={}
    for name,frame in frames.items():
        frame.to_csv(output/name,index=False,lineterminator='\n'); hashes[name]=sha256(output/name)
    (output/'nwdp_parent_manifest.json').write_text(json.dumps(nwdp_manifest,indent=2)+'\n',encoding='utf-8')
    hashes['nwdp_parent_manifest.json']=sha256(output/'nwdp_parent_manifest.json')
    reasons=Counter(reason for values in audit.audit_reason for reason in values.split(';') if reason)
    pdf_source={'id':'cgwb_january_2025_unconfined_pdf','name':'CGWB January 2025 unconfined archive',
        'url':extraction_manifest['source_url'],'path':repository_path(pdf_path),
        'sha256':extraction_manifest['source_sha256'],'size_bytes':Path(pdf_path).stat().st_size,
        'downloaded':True,'parsed':True,'acquired_this_run':False,'units':'m_bgl',
        'publisher':'Central Ground Water Board, Ministry of Jal Shakti',
        'license':'CGWB attribution/copyright policy; no separate license specified',
        'license_url':'https://cgwb.gov.in/en/copyright-policy'}
    manifest={'artifact_version':VERSION,'processing_version':VERSION,'as_of':as_of,
        'candidate_only':True,'database_modified':False,'source_rows':len(records),
        'accepted_source_rows':int(audit.audit_reason.eq('').sum()),'rejected_source_rows':int(audit.audit_reason.ne('').sum()),
        'rejection_reasons':dict(reasons),'sources':nwdp_manifest['sources']+[pdf_source],
        'crosswalk_sha256':sha256(ROOT/'data_ingestion/district_crosswalk.csv'),
        'geojson_sha256':sha256(ROOT/'data/raw/india_districts.geojson'),
        'baseline_features_sha256':nwdp_manifest['baseline_features_sha256'],
        'parent_enriched_features_sha256':feature_manifest['feature_csv_sha256'],
        'nwdp_parent_manifest_path':repository_path(nwdp_directory/'manifest.json'),
        'nwdp_parent_manifest_sha256':sha256(nwdp_directory/'manifest.json'),
        'extraction_manifest_path':repository_path(Path(extraction)/'extraction_manifest.json'),
        'extraction_manifest_sha256':sha256(Path(extraction)/'extraction_manifest.json'),
        'output_sha256':hashes,'units':{'gwl':'m_bgl'},'pdf_district_months':len(monthly),
        'pdf_overlapping_current_months':int(monthly.already_observed_current.sum()),
        'additional_observed_months':len(additions),'districts_gaining_months':int(additions.district_id.nunique()),
        'newly_locally_observed_districts':recovered,'remaining_zero_history_districts':len(zero)-len(recovered),
        'new_source_readings_contributing':int(audit.integration_decision.eq('additional_missing_measured_month').sum()),
        'boundary_margin_degrees':BOUNDARY_MARGIN_DEGREES,'review_depth_upper_m':MAX_REVIEW_DEPTH_M,
        'source_precedence':'Preserve all current genuine district-month means; NWDP original candidate retains precedence; PDF contributes whole missing months only. No station pooling across products.',
        'limitations':['PDF block/village/coordinate fingerprints are source locations, not certified well IDs.',
            'The dataset title states unconfined aquifer, not per-well construction/datum metadata.',
            'Fixed mixed-vintage project boundaries are not independently certified historical administration.',
            'New 2025 measurements extend observed history; previously inspected final-period labels cannot establish a new blind accuracy gain.',
            'No telemetry rows are converted or integrated.']}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return manifest


def write_review(output):
    """Reproduce aggregate source diagnostics offline from immutable evidence."""
    from data_ingestion.nwdp_manual import parse_telemetry_csv, _fingerprint
    output=Path(output)
    candidate=ROOT/'reports/candidates/groundwater_updates/final_release_20261026/pdf_january_2025_v2'
    card=json.loads((candidate/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in card['output_sha256'].items():
        if sha256(candidate/name)!=digest:
            raise ValueError('PDF candidate evidence changed')
    raw=ROOT/'data/raw/official_enrichment/nwdp_20261026'
    acquisition=json.loads((raw/'telemetry_acquisition.json').read_text(encoding='utf-8'))
    frames=[];profiles=[]
    for source in acquisition['resources']:
        frame=parse_telemetry_csv(source['path'],source_url=source['url'],resource_id=source['id'],expected_sha256=source['sha256'])
        for column in ['latitude','longitude','gwl_m_bgl','RL_MSL']:
            frame[column]=pd.to_numeric(frame[column],errors='coerce')
        frame['station_key']=[_fingerprint(state,label,lat,lon)
            for state,label,lat,lon in zip(frame.state_name,frame.station_name,frame.latitude,frame.longitude)]
        frame['resource_id']=source['id'];frames.append(frame)
        profiles.append({**{name:source.get(name) for name in ['id','name','url','sha256','size_bytes','downloaded_at_utc','license_id','license_title']},
            'rows':len(frame),'stations':int(frame.station_key.nunique()),
            'negative_rows':int(frame.gwl_m_bgl.lt(0).sum()),'zero_rows':int(frame.gwl_m_bgl.eq(0).sum()),
            'positive_rows':int(frame.gwl_m_bgl.gt(0).sum()),'missing_elevation_rows':int(frame.RL_MSL.isna().sum()),
            'zero_elevation_rows':int(frame.RL_MSL.eq(0).sum()),'positive_elevation_rows':int(frame.RL_MSL.gt(0).sum()),
            'first_observation_date':str(frame.observation_date.min().date()),'last_observation_date':str(frame.observation_date.max().date()),
            'units':'provider metres; not converted to depth below ground',
            'status':{'discovered':True,'accessible':True,'downloaded':True,'parsed':True,'integrated':False,'validated':False}})
    telemetry=pd.concat(frames,ignore_index=True)
    manual=pd.read_csv(NWDP/'accepted_station_records.csv',usecols=['station_key','observation_timestamp','observation_date','gwl_m_bgl'])
    manual['observation_date']=pd.to_datetime(manual.observation_date)
    manual['observation_timestamp']=pd.to_datetime(manual.observation_timestamp)
    td=telemetry.groupby(['station_key','observation_date'],as_index=False).gwl_m_bgl.mean()
    md=manual.groupby(['station_key','observation_date'],as_index=False).gwl_m_bgl.mean()
    paired=td.merge(md,on=['station_key','observation_date'],suffixes=('_telemetry','_manual'))
    signed=telemetry.groupby('station_key').gwl_m_bgl.agg(['min','max'])
    mixed=int((signed['min'].lt(0)&signed['max'].gt(0)).sum())
    exact=telemetry[['station_key','observation_timestamp']].merge(manual[['station_key','observation_timestamp']],on=['station_key','observation_timestamp'])
    proposed=pd.read_csv(candidate/'station_audit.csv',parse_dates=['observation_date'])
    proposed=proposed.loc[proposed.integration_decision.eq('additional_missing_measured_month')].copy()
    proposed['coordinate_day']=[f'{lat:.5f}|{lon:.5f}|{date:%Y-%m-%d}' for lat,lon,date in zip(proposed.latitude,proposed.longitude,proposed.observation_date)]
    manual_sources=json.loads((raw/'manual_acquisition.json').read_text(encoding='utf-8'))
    observed_2025=[]
    for source in manual_sources['resources']:
        if sha256(source['path']) != source['sha256']:
            raise ValueError('Manual source bytes changed during collision review')
        frame=pd.read_csv(source['path'],usecols=['Latitude','Longitude','Data Acquisition Time'])
        frame['date']=pd.to_datetime(frame['Data Acquisition Time'],format='%d-%m-%Y %H:%M',errors='coerce').dt.normalize()
        observed_2025.append(frame.loc[frame.date.dt.year.eq(2025)])
    observed_2025=pd.concat(observed_2025,ignore_index=True)
    provider_keys={f'{lat:.5f}|{lon:.5f}|{date:%Y-%m-%d}' for lat,lon,date in zip(observed_2025.Latitude,observed_2025.Longitude,observed_2025.date)}
    evidence=ROOT/'data/raw/official_enrichment/final_release_20261026/groundwater'
    guidance=evidence/'high_frequency_guidance_2026.pdf'
    refresh=json.loads((evidence/'manual_2026_refresh_check.json').read_text(encoding='utf-8')) if (evidence/'manual_2026_refresh_check.json').exists() else None
    if refresh and not all(row.get('sha256')=='cc7824b6b3b72f9e9818f1ca4edab27eeb37b82d6af4092c9d7801d5389d03b6' for row in refresh['resources']):
        raise ValueError('Refreshed manual headers differ from the previously validated empty CSV schema')
    report={'version':'final-groundwater-evidence-v1','production_database_changed':False,
        'pdf_candidate_manifest_path':repository_path(candidate/'manifest.json'),'pdf_candidate_manifest_sha256':sha256(candidate/'manifest.json'),
        'pdf_measurements':{key:card[key] for key in ['source_rows','accepted_source_rows','rejected_source_rows','rejection_reasons',
            'pdf_district_months','pdf_overlapping_current_months','additional_observed_months','districts_gaining_months',
            'newly_locally_observed_districts','remaining_zero_history_districts','new_source_readings_contributing']},
        'cross_product_review':{'nwdp_2025_source_rows':len(observed_2025),'additional_pdf_rows':len(proposed),
            'shared_exact_coordinate_day_keys':len(set(proposed.coordinate_day)&provider_keys),
            'policy':'Keep current district means; add only whole missing months. Coordinates/day are conservative collision screens, not certified common well IDs.'},
        'telemetry':{'resources':profiles,'rows':len(telemetry),'stations':int(telemetry.station_key.nunique()),
            'stations_with_both_negative_and_positive_values':mixed,'accepted_manual_station_fingerprint_overlap':len(set(telemetry.station_key)&set(manual.station_key)),
            'accepted_manual_same_day_pairs':len(paired),'accepted_manual_exact_timestamp_pairs':len(exact),
            'raw_signed_daily_difference_mae_m':float((paired.gwl_m_bgl_telemetry-paired.gwl_m_bgl_manual).abs().mean()) if len(paired) else None,
            'difference_interpretation':'Unconverted source difference, not forecast MAE or evidence licensing a sign transformation.',
            'release_requirements':['Provider-certified per-well exported variable, sign convention and units.',
                'Stable well identifiers and installation/reference-elevation, sensor-depth and cable-length metadata.',
                'Manual dip calibration/correction and maintenance/clock logs, with sufficient independently accepted overlap.',
                'Station-balanced temporal aggregation, quality flags and a prospective verification period.'],
            'integrated':False,'conversion_performed':False},
        'sources':[{'id':'cgwb_january_2025_reused','publisher':'Central Ground Water Board','landing_page':'https://cgwb.gov.in/en/ground-water-level-monitoring',
            'resource_url':card['sources'][-1]['url'],'sha256':card['sources'][-1]['sha256'],'size_bytes':card['sources'][-1]['size_bytes'],
            'actual_observation_period':'January 2025','acquired_this_run':False,'role':'genuine_missing_month_observation_target',
            'license':'CGWB attribution/copyright policy; no separate open-data grant supplied','license_url':'https://cgwb.gov.in/en/copyright-policy',
            'status':{'discovered':True,'accessible':None,'downloaded':True,'parsed':True,'integrated':True,'validated':True},
            'validation_scope':'Strict source/coordinates/date/duplicate screening and isolated candidate generation; not independent future accuracy.'},
            {'id':'cgwb_high_frequency_guidance_2026','publisher':'Central Ground Water Board, Ministry of Jal Shakti',
            'landing_page':'https://cgwb.gov.in/cgwbpnm/public/publication-detail/1932','resource_url':'https://cgwb.gov.in/cgwbpnm/public/download/1932',
            'sha256':sha256(guidance),'size_bytes':guidance.stat().st_size,'pages':124,'publication_date':'February 2026','download_date':'2026-10-26',
            'role':'source_validation_and_datum_requirements_not_measurements','license':'CGWB copyright/attribution policy; raw PDF local',
            'license_url':'https://cgwb.gov.in/en/copyright-policy','relevant_pdf_pages':[49,50,53,54,55,115],
            'status':{'discovered':True,'accessible':True,'downloaded':True,'parsed':True,'integrated':False,'validated':True},
            'finding':'Guidance requires installation/reference metadata and manual-dip validation; it flags negative/zero depths rather than prescribing a blanket sign flip. It does not supply station-specific correction logs.'}],
        'fresh_manual_resource_check':refresh,
        'source_code_sha256':sha256(__file__),
        'tests':{'command':'python -B -m pytest tests/test_groundwater_release.py -p no:cacheprovider -q --disable-warnings --basetemp=scratch/pytest-final-groundwater-verified','passed':24,'failed':0},
        'limitations':['Source location fingerprints are not certified physical wells; the PDF title describes an unconfined dataset, not individual construction metadata.',
            'Project boundary vintage is mixed; no historical observations were migrated to a new geography.',
            'The inspected old final periods cannot be reused as genuinely new blind evaluation after seeing outcomes.',
            'Future manual metadata timestamps changed overnight but all acquired small bodies still contain zero observations.']}
    if refresh:
        metadata=evidence/'manual_metadata_current.json'
        report['sources'].append({'id':'nwdp_manual_2026_refresh_check','publisher':'CGWB / National Water Informatics Centre',
            'landing_page':'https://nwdp.nwic.gov.in/dataset/gwl-manual-quarterly-central-ground-water-board-department',
            'resource_url':'https://nwdp.nwic.gov.in/api/3/action/package_show?id=gwl-manual-quarterly-central-ground-water-board-department',
            'metadata_sha256':sha256(metadata),'metadata_size_bytes':metadata.stat().st_size,
            'role':'current_resource_availability_and_empty_schema_check','license':'Other (Open); specific license URL not supplied',
            'checked_date':'2026-10-26','resource_count':len(refresh['resources']),'observation_rows':refresh['total_observation_rows'],
            'status':{'discovered':True,'accessible':True,'downloaded':True,'parsed':True,'integrated':False,'validated':True},
            'validation_scope':'31 small current CSV bodies match the hash of the previously schema-validated empty header; nightly timestamps do not signify observations.'})
    yearbook=evidence/'wb_an_sikkim_2024_2025.pdf'
    if yearbook.exists():
        acquisition_card=json.loads(yearbook.with_suffix('.acquisition.json').read_text(encoding='utf-8'))
        if sha256(yearbook)!=acquisition_card['sha256']:
            raise ValueError('State yearbook bytes differ from acquisition evidence')
        report['sources'].append({'id':'cgwb_wb_andaman_sikkim_yearbook_2024_2025',
            'publisher':'Central Ground Water Board, Eastern Region',
            'landing_page':'https://cgwb.gov.in/cgwbpnm/public/publication-detail/2027',
            'resource_url':acquisition_card['url'],'sha256':acquisition_card['sha256'],
            'size_bytes':acquisition_card['bytes'],'downloaded_at_utc':acquisition_card['downloaded_at_utc'],
            'http_last_modified':acquisition_card['http_last_modified'],'pages':197,
            'role':'regional_yearbook_context_and_measurement_metadata_review',
            'license':'CGWB copyright/attribution policy; no separate open-data grant supplied; raw PDF remains local',
            'license_url':'https://cgwb.gov.in/en/copyright-policy',
            'status':{'discovered':True,'accessible':True,'downloaded':True,'parsed':True,'integrated':False,'validated':False},
            'validation_scope':'Relevant text/figures reviewed; no additional numeric station-depth table accepted.',
            'relevant_pdf_pages':[194,195,196],
            'finding':'Sikkim narrative describes four confined-aquifer piezometers, so the January archive dataset title cannot certify individual aquifer type. Generic measured m_bgl values are retained without reinterpreting them as a certified unconfined water table.',
            'date_caveat':'Published label is 2024-2025 but Sikkim running headers say 2023-24. Observation dates must come from actual tables, never these inconsistent labels.'})
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output',type=Path);mode.add_argument('--review-output',type=Path)
    p.add_argument('--as-of',default='2026-10-26');a=p.parse_args(argv)
    if a.review_output:
        result=write_review(a.review_output);print(json.dumps({'pdf_measurements':result['pdf_measurements'],'telemetry':{k:v for k,v in result['telemetry'].items() if k!='resources'}},indent=2));return
    result=build(a.output,as_of=a.as_of)
    print(json.dumps({k:result[k] for k in ['source_rows','accepted_source_rows','rejected_source_rows',
        'pdf_district_months','pdf_overlapping_current_months','additional_observed_months',
        'districts_gaining_months','newly_locally_observed_districts','remaining_zero_history_districts',
        'new_source_readings_contributing','rejection_reasons']},indent=2))


if __name__=='__main__':
    main()
