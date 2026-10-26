"""Consolidate acquired-source evidence; this command never downloads or trains."""
import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from models.xgboost_model import sha256_file

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports/data_enrichment'


def _normalize_status(source):
    source = dict(source)
    original = source.get('status', {})
    source['status'] = {name: original.get(name) if isinstance(original.get(name), bool) else None
        for name in ('discovered','accessible','downloaded','parsed','integrated','validated')}
    details = {name:value for name,value in original.items() if not isinstance(value,bool)}
    if details:
        source['status_details'] = details
    return source


def build(candidate_directory, feature_directory):
    candidate_directory, feature_directory = Path(candidate_directory).resolve(), Path(feature_directory).resolve()
    manifest = json.loads((candidate_directory/'manifest.json').read_text(encoding='utf-8'))
    accepted = pd.read_csv(candidate_directory/'accepted_station_records.csv', usecols=['source_resource_id','district_id','date'])
    added = pd.read_csv(feature_directory/'added_observed_months.csv', usecols=['district_id','date'])
    integrated = accepted.merge(added, on=['district_id','date'], how='inner', validate='many_to_one')
    integrated_counts = integrated.groupby('source_resource_id').size().to_dict()
    sources = []
    for entry in manifest['sources']:
        source = dict(entry)
        source.update(id='nwdp_manual_'+entry['id'], resource_id=entry['id'], resource_url=entry['url'],
            landing_page=manifest['source_url'], publisher='CGWB / National Water Informatics Centre',
            role='measured_groundwater_target', units='m_bgl', coordinate_system='source latitude/longitude interpreted as WGS84, screened against project EPSG:4326 polygons',
            spatial_resolution='station; equal-weight station means aggregated to canonical district-month',
            reporting_cadence='manual quarterly; actual calendar timestamps retained',
            license=entry.get('license_title'), attribution='CGWB and NWIC, Ministry of Jal Shakti, Government of India',
            license_caveat='Metadata Other (Open) lacks specific grant URL; raw files remain local.',
            accepted_readings_contributing_to_added_months=int(integrated_counts.get(entry['id'],0)),
            status={'discovered':True,'accessible':True,'downloaded':True,'parsed':True,
                'integrated':entry['id'] in integrated_counts,'validated':True},
            validation_scope='Schema/checksum/measurement/spatial audit; forecast skill is evaluated separately. Header-only resources contain no observations.')
        source.pop('url',None)
        source['verified_cached_at_utc'] = source.pop('downloaded_at_utc',None)
        source['download_date_local'] = '2026-10-26'
        source['download_time_note'] = 'Acquired during this run; acquisition manifest was reconstructed from cached files. Timestamp is cache verification, not a certified initial download instant.'
        for name in ('discovered','accessible','downloaded','parsed','integrated','validated'):
            source.pop(name,None)
        sources.append(source)
    telemetry = json.loads((REPORTS/'telemetry_review.json').read_text(encoding='utf-8'))
    acquisition = json.loads((ROOT/'data/raw/official_enrichment/nwdp_20261026/telemetry_acquisition.json').read_text(encoding='utf-8'))
    telemetry_downloads = {entry['id']:entry.get('downloaded_at_utc') for entry in acquisition['resources']}
    for entry in telemetry['resources']:
        sources.append({**entry, 'id':'nwdp_telemetry_'+entry['id'], 'publisher':'CGWB / NWIC',
            'landing_page':telemetry['dataset_url'], 'resource_url':entry['url'],
            'role':'candidate_groundwater_telemetry_not_integrated', 'units':'provider metres; per-well sign/datum unresolved',
            'downloaded_at_utc':telemetry_downloads.get(entry['id']),
            'status':telemetry['status'], 'decision':telemetry['decision'], 'blockers':telemetry['blockers']})
    nwdp_catalog_path = ROOT/'data_sources/nwdp_resources.json'
    nwdp_catalog = json.loads(nwdp_catalog_path.read_text(encoding='utf-8'))
    for entry in nwdp_catalog['resources']:
        if entry.get('downloaded') is False:
            source = dict(entry)
            source['resource_url'] = source.pop('url')
            source['status'] = {name:source.pop(name,None) for name in ('discovered','accessible','downloaded','parsed','integrated','validated')}
            sources.append(_normalize_status(source))
    archive_path = ROOT/'data/raw/updates/20261015/cgwb/January_WL_1994-2025.pdf'
    sources.append({'id':'cgwb_january_archive_preexisting', 'publisher':'Central Ground Water Board',
        'landing_page':'https://cgwb.gov.in/en/ground-water-level-monitoring',
        'resource_url':'https://cgwb.gov.in/wl_data/January_WL_1994-2025.pdf',
        'role':'complementary_measured_groundwater_archive_not_pooled', 'units':'m_bgl',
        'coverage_period':'Advertised January 1994-2025; existing strict parser inspects January 2025 pages 1-332 only.',
        'acquired_in_this_run':False, 'downloaded_at_utc':None,
        'size_bytes':archive_path.stat().st_size if archive_path.exists() else None,
        'sha256':sha256_file(archive_path) if archive_path.exists() else None,
        'license':'CGWB attribution/copyright policy; raw PDF stays local.',
        'status':{'discovered':True,'accessible':None,'downloaded':archive_path.exists(),'parsed':True,'integrated':False,'validated':False},
        'decision':'Previously acquired and inspected archive, not a new download. Do not pool overlapping products without certified station IDs. Current resource accessibility was not established by the failed web fetch.'})
    evidence_files = [candidate_directory/'manifest.json', REPORTS/'telemetry_review.json',nwdp_catalog_path]
    for filename in ('weather_sources.json','auxiliary_sources.json'):
        path = REPORTS/filename
        payload = json.loads(path.read_text(encoding='utf-8'))
        entries = payload.get('sources', [])
        if isinstance(entries,dict):
            entries = [{'id':key, **value} for key,value in entries.items()]
        sources.extend(_normalize_status(source) for source in entries)
        evidence_files.append(path)
    catalog = {'schema_version':'aquaiq-official-sources-v1','checked_date':'2026-10-26',
        'scope':'Official/scientific source evidence for isolated enrichment; no raw downloads committed.',
        'status_convention':'Boolean stages are independent. null means not established at dataset level; details distinguish metadata-only access and prior probes.',
        'boundary_vintage':'Fixed project mixed 2011/update-2025 snapshot; not certified current or historical administrative boundaries.',
        'evidence_sha256':{str(path.relative_to(ROOT)).replace('\\','/'):sha256_file(path) for path in evidence_files},
        'sources':sources}
    destination = ROOT/'data_sources/catalog.yaml'
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True, width=110),encoding='utf-8')
    coverage = pd.read_csv(feature_directory/'district_coverage.csv')
    coverage.to_csv(REPORTS/'source_coverage.csv',index=False)
    summary = json.loads((feature_directory/'build_summary.json').read_text(encoding='utf-8'))
    (REPORTS/'data_build.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(f'Wrote {len(sources)} source entries and {len(coverage)} canonical district coverage rows.')
    return catalog


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidates',type=Path,required=True);p.add_argument('--feature-directory',type=Path,required=True)
    a=p.parse_args();build(a.candidates,a.feature_directory)
