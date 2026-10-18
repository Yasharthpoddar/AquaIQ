"""Read-only groundwater label/origin coverage inventory; no models are fitted."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from models import xgboost_model as forecast
from data_ingestion.cgwb_updates import audit_records, build_district_lookup, resolve_district

OUT = Path(__file__).resolve().parent


def ranges(frame, date_col):
    return {"n": int(len(frame)), "districts": int(frame.district_id.nunique()),
            "start": str(frame[date_col].min().date()) if len(frame) else None,
            "end": str(frame[date_col].max().date()) if len(frame) else None}


def summarize(group):
    return {"observed_targets": len(group),
            "origin_month_exists": int(group.origin_exists.sum()),
            "finite_causal_origin": int(group.finite_origin.sum()),
            "observed_origin": int(group.observed_origin.sum()),
            "finite_causal_origin_and_exact_observed_seasonal": int((group.finite_origin & group.finite_seasonal).sum()),
            "observed_origin_and_exact_observed_seasonal": int((group.observed_origin & group.finite_seasonal).sum()),
            "districts_with_finite_origin": int(group.loc[group.finite_origin, 'district_id'].nunique())}


def make_pairs(frame, labels):
    origins = frame[['district_id', 'date', 'gwl_current', 'is_observed', 'months_since_observation']].rename(
        columns={'date': 'origin_date', 'gwl_current': 'origin_gwl', 'is_observed': 'origin_is_observed'})
    origins['origin_exists'] = True
    labels = labels.copy()
    labels['origin_date'] = labels.target_date - pd.DateOffset(months=6)
    joined = labels.merge(origins, on=['district_id', 'origin_date'], how='left', validate='one_to_one')
    seasonal = frame.loc[frame.is_observed, ['district_id', 'date', 'gwl_current']].rename(
        columns={'date': 'seasonal_date', 'gwl_current': 'seasonal_gwl'})
    joined['seasonal_date'] = joined.target_date - pd.DateOffset(months=12)
    joined = joined.merge(seasonal, on=['district_id', 'seasonal_date'], how='left', validate='one_to_one')
    joined['origin_exists'] = joined.origin_exists.fillna(False).astype(bool)
    joined['finite_origin'] = np.isfinite(joined.origin_gwl)
    joined['observed_origin'] = joined.finite_origin & joined.origin_is_observed.fillna(False).astype(bool)
    joined['finite_seasonal'] = np.isfinite(joined.seasonal_gwl)
    return joined


def main():
    frame = forecast.load_feature_matrix()
    labels = frame.loc[frame.is_observed, ['district_id', 'date', 'gwl_current']].rename(
        columns={'date': 'target_date', 'gwl_current': 'target_gwl'})
    pairs = make_pairs(frame, labels)
    pairs['target_year'] = pairs.target_date.dt.year
    pairs['target_month'] = pairs.target_date.dt.strftime('%Y-%m')
    annual = pd.DataFrame([{'target_year': int(k), **summarize(v)} for k, v in pairs.groupby('target_year')])
    monthly = pd.DataFrame([{'target_month': k, **summarize(v)} for k, v in pairs.groupby('target_month')])
    annual.to_csv(OUT / 'label_coverage_by_year.csv', index=False)
    monthly.to_csv(OUT / 'label_coverage_by_month.csv', index=False)
    recent = pairs.loc[pairs.target_date >= '2023-01-01'].copy()
    recent.to_csv(OUT / 'recent_observed_target_origin_coverage.csv', index=False)
    report = {'source': 'data/processed/features_matrix.csv',
              'feature_generation': frame.attrs['feature_generation_id'],
              'feature_sha256': forecast.sha256_file(ROOT/'data/processed/features_matrix.csv'),
              'whole_timeline': summarize(pairs),
              'recent_target_2023_onward': summarize(recent),
              'recent_supported': ranges(recent.loc[recent.finite_origin], 'target_date'),
              'periods': {}, 'candidate_updates': {}}
    for name, start, end in [('development_2002_2019', '2002-01-01','2019-12-31'),
                             ('validation_2020_2022', '2020-01-01','2022-12-31'),
                             ('final_2023_2026','2023-01-01','2026-09-30')]:
        sub = pairs.loc[pairs.target_date.between(start,end)]
        report['periods'][name] = summarize(sub)
    for name, relative in [
        ('january_2025', 'reports/candidates/station_history_20261015/january_2025_audited/canonical_district_month_candidates.csv'),
        ('january_2026', 'reports/candidates/groundwater_updates/20261013/canonical_district_month_candidates.csv')]:
        src = ROOT / relative
        update = pd.read_csv(src, parse_dates=['date']).rename(columns={'date': 'target_date', 'gwl_mean': 'target_gwl'})
        paired = make_pairs(frame, update[['district_id', 'target_date', 'target_gwl']])
        paired.to_csv(OUT / f'{name}_candidate_origin_coverage.csv', index=False)
        report['candidate_updates'][name] = {'source': relative, 'sha256': forecast.sha256_file(src), **summarize(paired)}

    # This source is an unadopted station CSV. Inspect exact-format dates and
    # state-qualified district identities; do not adopt its values as truth.
    manual_path = ROOT/'data/raw/updates/20261013/gwl_manual_quarterly_cgwb_gj_2021_2025.csv'
    manual = pd.read_csv(manual_path)
    manual['observation_date'] = pd.to_datetime(manual['Data Acquisition Time'], format='%d-%m-%Y %H:%M', errors='coerce')
    manual['target_date'] = manual.observation_date.dt.to_period('M').dt.to_timestamp()
    lookup = build_district_lookup(pd.read_csv(ROOT/'data_ingestion/district_crosswalk.csv', dtype=str))
    resolution = [resolve_district(r['State'], r['District'], lookup) for r in manual.to_dict('records')]
    manual['district_id'] = [r[0] for r in resolution]
    manual['mapping_status'] = [r[1] for r in resolution]
    manual['gwl'] = pd.to_numeric(manual['Groundwater Level Quarterly Manual (meter)'], errors='coerce')
    kept = manual.loc[manual.district_id.notna() & manual.target_date.notna() & np.isfinite(manual.gwl)].copy()
    # Exact station/date conflicts and source duplicates are only diagnosed here.
    keys = ['Station', 'Latitude', 'Longitude', 'observation_date']
    conflict_keys = kept.groupby(keys).gwl.transform('nunique').gt(1)
    conflict_count = int(conflict_keys.sum())
    kept = kept.loc[~conflict_keys].drop_duplicates(keys)
    monthly_source = kept.groupby(['district_id', 'target_date'], as_index=False).agg(target_gwl=('gwl', 'mean'), n_station_rows=('gwl','size'))
    proposed = monthly_source.merge(labels[['district_id','target_date','target_gwl']].rename(columns={'target_gwl':'existing_gwl'}),
                                    on=['district_id','target_date'], how='left', validate='one_to_one')
    proposed['existing_observed'] = proposed.existing_gwl.notna()
    paired = make_pairs(frame, proposed)
    paired.to_csv(OUT/'unadopted_manual_source_target_origin_coverage.csv', index=False)
    report['unadopted_manual_source'] = {'source': str(manual_path.relative_to(ROOT)),
        'sha256': forecast.sha256_file(manual_path), 'raw_rows': len(manual),
        'invalid_dates': int(manual.observation_date.isna().sum()),
        'exact_date_start': str(manual.observation_date.min()), 'exact_date_end': str(manual.observation_date.max()),
        'mapping_counts': manual.mapping_status.value_counts().to_dict(), 'conflicting_station_date_rows':conflict_count,
        'candidate_only_not_verified_depth_datum_or_well_panel': True,
        'all': summarize(paired), 'new_observed_target_keys': summarize(paired.loc[~paired.existing_observed]),
        'post2023_new_keys': summarize(paired.loc[~paired.existing_observed & (paired.target_date >= '2023-01-01')])}

    # Assess whether complete, separately audited source history could expand
    # cases. This is a coverage diagnostic, never a production data rebuild.
    import geopandas as gpd
    records = manual.rename(columns={'State':'state_name', 'District':'district_name',
        'Block':'block', 'Village':'village', 'Latitude':'latitude', 'Longitude':'longitude',
        'Groundwater Level Quarterly Manual (meter)':'gwl_m_bgl'}).copy()
    records['reported_date'] = manual.observation_date.dt.strftime('%d-%m-%Y')
    records['source_month'] = manual.observation_date.dt.strftime('%Y-%m')
    audited, strict_monthly = audit_records(records, pd.read_csv(ROOT/'data_ingestion/district_crosswalk.csv', dtype=str),
        as_of='2026-10-17', boundaries=gpd.read_file(ROOT/'data/raw/india_districts.geojson'))
    audited.to_csv(OUT/'unadopted_manual_source_spatial_station_audit.csv', index=False)
    strict_monthly.to_csv(OUT/'unadopted_manual_source_spatial_monthly.csv', index=False)
    strict = strict_monthly[['district_id', 'date', 'gwl_mean']].rename(columns={'date':'target_date','gwl_mean':'target_gwl'})
    additions = strict.merge(labels[['district_id','target_date']].assign(existing=True), on=['district_id','target_date'], how='left')
    additions = additions.loc[additions.existing.isna()].drop(columns='existing')
    combined_labels = pd.concat([labels,additions], ignore_index=True)
    merged = frame[['district_id','date']].merge(combined_labels.rename(columns={'target_date':'date','target_gwl':'observed_gwl'}),
        on=['district_id','date'],how='left',validate='one_to_one').sort_values(['district_id','date'])
    merged['is_observed'] = merged.observed_gwl.notna()
    merged['gwl_current'] = merged.groupby('district_id').observed_gwl.ffill(limit=3)
    merged['months_since_observation'] = np.nan
    hypothetical = make_pairs(merged, combined_labels)
    hypothetical.to_csv(OUT/'unadopted_manual_augmented_label_coverage.csv', index=False)
    report['unadopted_manual_source']['spatial_audit'] = {
        'accepted_station_rows': int(audited.audit_reason.eq('').sum()),
        'rejected_station_rows': int(audited.audit_reason.ne('').sum()),
        'district_months': len(strict), 'new_district_months':len(additions),
        'new_district_months_post2023': int((additions.target_date >= '2023-01-01').sum()),
        'hypothetical_coverage_only_not_used_for_fitting':True,
        'augmented_all':summarize(hypothetical),
        'augmented_final2020_onward':summarize(hypothetical.loc[hypothetical.target_date >= '2020-01-01']),
        'augmented_post2023':summarize(hypothetical.loc[hypothetical.target_date >= '2023-01-01']),
        'caveat':'Unit header says meter; no independent signed depth datum/publication manifest or longitudinal stable well panel was established. Existing observed active keys take precedence; this is not an adopted target release.'}
    (OUT/'coverage_summary.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(report, indent=2, allow_nan=False))
    print(annual.to_string(index=False))


if __name__ == '__main__':
    main()
