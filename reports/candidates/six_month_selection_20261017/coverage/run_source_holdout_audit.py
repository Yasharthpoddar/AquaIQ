"""Prepare optional source-only observed cases without fitting or active writes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from models import xgboost_model as forecast

OUT = Path(__file__).resolve().parent
DATASET_URL = 'https://nwdp.nwic.gov.in/dataset/gwl-manual-quarterly-central-ground-water-board-department'
RESOURCE_ID = 'ef17ded9-be74-48e6-9359-f3a19daeea4a'
RESOURCE_URL = DATASET_URL + '/resource/' + RESOURCE_ID
DOWNLOAD_URL = 'https://nwdp.nwic.gov.in/dataset/956add67-cba9-41a5-9d5c-96d73db44aef/resource/ef17ded9-be74-48e6-9359-f3a19daeea4a/download/gwl_manual_quarterly_cgwb_gj_2021_2025.csv'
CLIMATE = ['rainfall_current','rainfall_3mo_avg','monsoon_deficit_pct','temperature','evapotranspiration','water_balance_proxy','crop_season_flag']


def main():
    source = ROOT/'data/raw/updates/20261013/gwl_manual_quarterly_cgwb_gj_2021_2025.csv'
    raw = pd.read_csv(source)
    audit = pd.read_csv(OUT/'unadopted_manual_source_spatial_station_audit.csv')
    monthly = pd.read_csv(OUT/'unadopted_manual_source_spatial_monthly.csv', parse_dates=['date'])
    frame = forecast.load_feature_matrix()
    observed = frame.loc[frame.is_observed, ['district_id','date','gwl_current']]
    overlaps = monthly.merge(observed, on=['district_id','date'], how='inner', validate='one_to_one')
    overlaps['source_minus_active_m'] = overlaps.gwl_mean - overlaps.gwl_current
    overlaps.to_csv(OUT/'source_manual_active_observation_overlap.csv',index=False)

    # Preserve this source's observations as a separate benchmark. No source
    # averages are mixed with old district averages, even at overlapping keys.
    district_ids = sorted(monthly.district_id.unique())
    timeline = pd.MultiIndex.from_product([district_ids, pd.date_range(monthly.date.min(),monthly.date.max(),freq='MS')],
                                         names=['district_id','date']).to_frame(index=False)
    timeline = timeline.merge(monthly[['district_id','date','gwl_mean','station_count','reading_count']],on=['district_id','date'],how='left',validate='one_to_one')
    timeline['is_observed'] = timeline.gwl_mean.notna()
    timeline['gwl_current'] = timeline.groupby('district_id').gwl_mean.ffill(limit=3)
    timeline['is_imputed'] = timeline.gwl_current.notna() & ~timeline.is_observed
    row_number = timeline.groupby('district_id').cumcount()
    last_observed_row = row_number.where(timeline.is_observed).groupby(timeline.district_id).ffill()
    timeline['months_since_observation'] = row_number - last_observed_row
    for lag in [3,6]:
        lagged = timeline[['district_id','date','gwl_current']].copy()
        lagged['date'] += pd.DateOffset(months=lag)
        timeline = timeline.merge(lagged.rename(columns={'gwl_current':f'gwl_lag_{lag}mo'}),on=['district_id','date'],how='left',validate='one_to_one')
    timeline = timeline.merge(frame[['district_id','date',*CLIMATE]],on=['district_id','date'],how='left',validate='one_to_one')
    timeline['feature_generation'] = 'candidate-source-manual-gj-' + forecast.sha256_file(source)[:12]
    timeline.to_csv(OUT/'source_manual_optional_features.csv',index=False)
    prepared = forecast.create_target(forecast.encode_crop_season(timeline))
    strict = prepared.loc[prepared.is_observed & prepared.target_is_observed & prepared.seasonal_naive_6mo.notna()].copy()
    strict['source_benchmark'] = 'source_only_manual_gj'
    strict['climate_numeric_features_finite'] = np.isfinite(strict[[c for c in CLIMATE if c!='crop_season_flag']].to_numpy(float)).all(axis=1)
    target_keys = observed[['district_id','date']].rename(columns={'date':'target_date'}).assign(target_already_observed_active=True)
    strict = strict.merge(target_keys,on=['district_id','target_date'],how='left',validate='one_to_one')
    strict['target_already_observed_active'] = strict.target_already_observed_active.fillna(False).astype(bool)
    accepted = audit.loc[audit.audit_reason.isna()].copy()
    accepted['date'] = pd.to_datetime(accepted['date'])
    panels = accepted.groupby(['district_id','date']).station_key.agg(set).to_dict()
    stable_panel_rows = []
    for row in strict.itertuples():
        origin_panel = panels[(row.district_id,row.date)]
        target_panel = panels[(row.district_id,row.target_date)]
        seasonal_panel = panels[(row.district_id,row.target_date-pd.DateOffset(months=12))]
        stable_panel_rows.append({'district_id':row.district_id,'date':row.date,'target_date':row.target_date,
            'origin_station_count':len(origin_panel),'target_station_count':len(target_panel),
            'seasonal_station_count':len(seasonal_panel),
            'origin_target_shared_station_count':len(origin_panel & target_panel),
            'all_three_shared_station_count':len(origin_panel & target_panel & seasonal_panel),
            'origin_target_station_jaccard':len(origin_panel & target_panel)/len(origin_panel | target_panel)})
    stable_panel = pd.DataFrame(stable_panel_rows)
    stable_panel.to_csv(OUT/'source_manual_optional_station_panel_overlap.csv',index=False)
    columns = ['district_id','date','target_date','gwl_current','target_gwl_6mo','seasonal_naive_6mo',
               *[c for c in forecast.CANONICAL_FEATURE_COLS if c!='gwl_current'],
               'station_count','reading_count','is_observed','target_is_observed','months_since_observation',
               'source_benchmark','climate_numeric_features_finite','target_already_observed_active']
    strict[columns].to_csv(OUT/'source_manual_optional_exact_observed_cases.csv',index=False)
    strict.loc[~strict.target_already_observed_active,columns].to_csv(OUT/'source_manual_optional_unused_target_cases.csv',index=False)

    climate_cols = [c for c in CLIMATE if c!='crop_season_flag']
    reason_counts = {}
    for text in audit.audit_reason.dropna():
        for reason in text.split(';'):
            reason_counts[reason] = reason_counts.get(reason,0)+1
    temporal = []
    for period, group in strict.groupby(strict.target_date.dt.strftime('%Y-%m')):
        temporal.append({'target_month':period,'n':len(group),'districts':int(group.district_id.nunique()),
            'n_targets_not_in_active':int((~group.target_already_observed_active).sum()),
            'n_all_climate_features_finite':int(group.climate_numeric_features_finite.sum())})
    same_value = np.isclose(overlaps.gwl_mean,overlaps.gwl_current,rtol=0,atol=1e-9)
    report = {'purpose':'Optional source-only holdout, never model selection or training. No models fitted.',
        'source':str(source.relative_to(ROOT)),'source_sha256':forecast.sha256_file(source),
        'source_size_bytes':source.stat().st_size,'source_row_count':len(raw),'columns':list(raw.columns),
        'raw_null_count':{c:int(v) for c,v in raw.isna().sum().items()},
        'raw_blank_dash_count':{c:int(raw[c].astype('string').str.strip().isin(['','-']).sum()) for c in raw.columns},
        'raw_exact_duplicate_rows':int(raw.duplicated().sum()),
        'date_parse':'explicit %d-%m-%Y %H:%M; original month-first generic audit dates were inaccurate for this CSV',
        'reported_date_min':str(pd.to_datetime(raw['Data Acquisition Time'],format='%d-%m-%Y %H:%M').min()),
        'reported_date_max':str(pd.to_datetime(raw['Data Acquisition Time'],format='%d-%m-%Y %H:%M').max()),
        'source_agencies':raw.Agency.value_counts(dropna=False).to_dict(),
        'source_states':raw.State.value_counts(dropna=False).to_dict(),
        'units':{'raw_header':'Groundwater Level Quarterly Manual (meter)',
            'unit_meters_established':True,'below_ground_datum_explicit_in_local_header':False,
            'RL_MSL_nonnull_rows':int(raw.RL_MSL.notna().sum()),
            'interpretation':'Depth below ground is consistent with CGWB manual monitoring and positive readings but the downloaded CSV header/available metadata do not explicitly certify its vertical datum.'},
        'mapping':'actual point intersects exactly one fixed canonical district polygon; source-state mismatch rejected; no nearest snapping',
        'boundaries_sha256':forecast.sha256_file(ROOT/'data/raw/india_districts.geojson'),
        'crosswalk_sha256':forecast.sha256_file(ROOT/'data_ingestion/district_crosswalk.csv'),
        'accepted_rows':int(audit.audit_reason.isna().sum()),'rejected_rows':int(audit.audit_reason.notna().sum()),
        'rejection_reasons':reason_counts,'district_month_count':len(monthly),'district_count':int(monthly.district_id.nunique()),
        'mean_method':'Unique station/date readings; all conflicting station/date values excluded; station-month means averaged equally within district month.',
        'negative_depth_policy':'Existing cgwb_updates strict nonnegative-depth policy retained, excluding29 source rows. Negative values could be artesian measurements; their interpretation was not established and they are not automatically called invalid observations.',
        'overlapping_active_observed_months':len(overlaps),'overlap_equal_values_at_1e_9':int(same_value.sum()),
        'overlap_different_values':int((~same_value).sum()),
        'no_active_values_overridden':True,
        'unused_target_cases':int((~strict.target_already_observed_active).sum()),
        'strict_case_count':len(strict),'strict_case_district_count':int(strict.district_id.nunique()),
        'strict_case_target_periods':temporal,
        'climate_missing_count_on_strict_origins':{c:int(strict[c].isna().sum()) for c in climate_cols},
        'gwl_lag_missing_count_on_strict_origins':{c:int(strict[c].isna().sum()) for c in ['gwl_lag_3mo','gwl_lag_6mo']},
        'station_panel_proxy_on_strict_cases':{
            'cases_with_any_shared_station_origin_and_target':int(stable_panel.origin_target_shared_station_count.gt(0).sum()),
            'cases_with_any_shared_station_all_three_dates':int(stable_panel.all_three_shared_station_count.gt(0).sum()),
            'median_origin_target_jaccard':float(stable_panel.origin_target_station_jaccard.median()),
            'min_origin_target_jaccard':float(stable_panel.origin_target_station_jaccard.min()),
            'caveat':'Station proxy uses normalized source location plus coordinates rounded5decimals; stable unique well IDs are absent.'},
        'causal_feature_method':'Each groundwater origin/target/seasonal value must be observed in this independent station source. Missing monthly groundwater history forward-filled at most3months to construct lag3/lag6; target never filled. Same-origin climate features copied from checksum-verified causal active features; no target climate used.',
        'protocol_advice':'Keep source-only benchmark separate from chronological primary results. Its station composition and sampling differ; do not mix monthly means with active aggregates. Use only unused-target cases after locking model parameters, and report datum/provenance caveats.',
        'local_download_manifest_found':False,
        'prior_local_source_reference':'reports/AquaIQ_Data_Refresh_Update.md states Gujarat NWIC download2021–2025 contains readings only throughAugust2023; not previously merged.',
        'official_catalog_reference':DATASET_URL,'official_resource_reference':RESOURCE_URL,
        'official_download_url':DOWNLOAD_URL,
        'online_metadata_seen_2026_10_17':{'catalog_provider':'CGWB','resource_label':'Ground Water Level CGWB Gujarat (2021 - 2025) Manual Quarterly','resource_data_last_updated':'2026-01-24','csv_format':True},
        'limitations':['Original download has no saved transport response or digital signature.',
            'A separate source can contain the same underlying wells and is not a spatial independence claim.',
            'Quarterly source does not provide operational publication/revision lags.',
            'Station population changes across months; district depths are not longitudinal matched-well changes.',
            'The source name says2021–2025 but actual maximum reported date is2023-08-30.']}
    try:
        response = requests.get(DOWNLOAD_URL,timeout=(5,10))
        response.raise_for_status()
        digest = hashlib.sha256(response.content).hexdigest()
        report['online_byte_verification'] = {'http_status':response.status_code,'bytes':len(response.content),
            'sha256':digest,'matches_local_source':digest==report['source_sha256'],
            'content_type':response.headers.get('content-type'),'etag':response.headers.get('etag')}
    except requests.RequestException as error:
        report['online_byte_verification'] = {'status':'unavailable','error':str(error)}
    report['output_sha256'] = {p.name:forecast.sha256_file(p) for p in [OUT/'source_manual_optional_features.csv',
        OUT/'source_manual_optional_exact_observed_cases.csv',OUT/'source_manual_optional_unused_target_cases.csv',
        OUT/'source_manual_active_observation_overlap.csv',OUT/'source_manual_optional_station_panel_overlap.csv']}
    (OUT/'source_manual_optional_audit.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__ == '__main__':
    main()
