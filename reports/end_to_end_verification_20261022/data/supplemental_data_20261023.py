"""Read-only supplemental data QC; write only new sanitized audit evidence."""
from __future__ import annotations
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qs
import numpy as np
import pandas as pd
import xarray as xr

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
RUN = ROOT / 'reports/actual_forecast_validation_20261019'
APP = ROOT / 'reports/candidates/twelve_month_horizon_finalization_20261020/artifact'
CHECKS = []

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def check(name, condition, **detail):
    CHECKS.append({'name': name, 'passed': bool(condition), **detail})

def safe_url(value):
    item = urlsplit(str(value))
    return {'url_without_query': urlunsplit((item.scheme, item.netloc.split('@')[-1], item.path, '', '')),
            'query_parameter_names': sorted(parse_qs(item.query))}

def relative(path):
    return str(Path(path).relative_to(ROOT)).replace('\\', '/')

def counts(series):
    return {str(key): int(value) for key, value in series.value_counts(dropna=False).items()}

def near(a, b):
    return bool(np.allclose(a, b, rtol=0, atol=1e-10, equal_nan=True))

def acquisition_evidence():
    original = RUN / 'source_manifest.json'
    manifest = load(original)
    results = []
    for item in manifest['acquisitions']:
        # Paths are resolved by retained basename, never by remote URL contents.
        filename = str(item['file']).replace('\\', '/').split('/')[-1]
        path = RUN / 'acquired' / filename
        receipt_path = Path(str(path) + '.retrieval.json')
        receipt = load(receipt_path)
        actual = sha(path)
        matches = actual == item['sha256'] == receipt['sha256']
        size_matches = path.stat().st_size == item['bytes'] == receipt['bytes']
        check('acquired_bytes_and_receipt_' + filename, matches and size_matches)
        results.append({
            'file': relative(path), 'bytes': path.stat().st_size,
            'expected_sha256': item['sha256'], 'actual_sha256': actual,
            'hash_matches_manifest_and_receipt': matches,
            'size_matches_manifest_and_receipt': size_matches,
            'receipt_file': relative(receipt_path), 'receipt_sha256': sha(receipt_path),
            'retrieved_at_utc': receipt['retrieved_at_utc'],
            'manifest_retrieval_time_equals_receipt': item['retrieved_at_utc'] == receipt['retrieved_at_utc'],
            'http_status': receipt['http_status'],
            'requested_url': safe_url(receipt['requested_url']),
            'final_url': safe_url(receipt['final_url']),
            'sample_only': receipt.get('sample_only'),
            'headers_omitted': True,
        })
    public = load(ROOT / 'reports/github_release_20261020/PUBLIC_SOURCE_PROVENANCE.json')
    check('private_original_manifest_hash_matches_public_fingerprint', sha(original) == public['original_local_manifest_sha256'])
    metadata = {key: manifest[key] for key in (
        'created_at_utc', 'provider_reported_units', 'actual_reported_date_range',
        'provider_ids', 'rows', 'catalog_metadata_created', 'catalog_metadata_modified',
        'production_data_merged') if key in manifest}
    return {'private_original_manifest_sha256': sha(original),
            'private_original_manifest_not_copied': True, 'headers_never_emitted': True,
            'manifest_allowlisted_dataset_metadata': metadata, 'acquisitions': results,
            'interpretation': 'Recorded current-export receipt; not independently authenticated provider publication or historical value availability.'}

def raw_qc():
    raw = pd.read_csv(RUN / 'acquired/telangana_monthly_2007_2026.csv', encoding='cp1252', dtype=str, keep_default_na=False)
    result = {'missing_or_blank_by_raw_column': {c: int(raw[c].str.strip().eq('').sum()) for c in raw}}
    for column, low, high in [('Latitude', -90, 90), ('Longitude', -180, 180)]:
        value = pd.to_numeric(raw[column], errors='coerce').astype(float)
        result[column] = {'missing_or_nonnumeric': int(value.isna().sum()),
                          'infinite': int(np.isinf(value).sum()),
                          'outside_global_coordinate_range': int((value.lt(low) | value.gt(high)).sum()),
                          'min': float(value.min()), 'max': float(value.max())}
    dates = pd.to_datetime(raw['Date'], format='%d-%m-%Y', errors='coerce')
    raw['audit_month'] = dates.dt.to_period('M').astype(str)
    duplicate = raw.duplicated(['Agency', 'Well ID', 'audit_month'], keep=False)
    result['rows_in_duplicate_agency_id_month_groups'] = int(duplicate.sum())
    result['duplicate_agency_id_month_groups'] = int(raw.loc[duplicate, ['Agency', 'Well ID', 'audit_month']].drop_duplicates().shape[0])
    metadata = ['Latitude', 'Longitude', 'Well Depth, m', 'Aquifer Tapped (Unconfined, Semi-Confined, Confined)',
                'Well Type', 'District Name (as per LGD)', 'Site Name']
    variation = raw.groupby(['Agency', 'Well ID'])[metadata].nunique(dropna=False)
    result['raw_provider_ids_with_metadata_variation'] = int(variation.gt(1).any(axis=1).sum())
    result['raw_ids_with_metadata_variation_by_field'] = {column: int(variation[column].gt(1).sum()) for column in metadata}
    value = pd.to_numeric(raw['Water Level in mbgl'], errors='coerce').astype(float)
    sequence = pd.DataFrame({'agency': raw.Agency, 'id': raw['Well ID'], 'date': dates, 'value': value}).sort_values(['agency', 'id', 'date'])
    previous = sequence.groupby(['agency', 'id']).value.shift()
    previous_date = sequence.groupby(['agency', 'id']).date.shift()
    calendar_gap = (sequence.date.dt.year - previous_date.dt.year) * 12 + sequence.date.dt.month - previous_date.dt.month
    comparable = value.notna().reindex(sequence.index) & previous.notna() & calendar_gap.eq(1)
    result['consecutive_month_comparable_pairs'] = int(comparable.sum())
    result['exact_repeat_values_in_consecutive_month_pairs'] = int((comparable & sequence.value.eq(previous)).sum())
    result['repeat_interpretation'] = 'Descriptive repeated values; these bytes alone cannot distinguish persistent levels, rounding, republication or fresh acquisition.'
    return result

def app_and_cohort():
    accepted = pd.read_csv(RUN / 'normalized_v2/normalized_well_observations.csv', dtype={'provider_well_id': str}, parse_dates=['date'])
    strict = accepted.loc[accepted.source_name_district_id.notna() & accepted.source_name_district_id.eq(accepted.district_id)]
    means = strict.groupby(['district_id', 'date']).gwl_m_bgl.agg(['mean', 'size'])
    features = pd.read_csv(APP / 'features.csv', parse_dates=['date'])
    observed = features.loc[features.is_observed & ~features.is_imputed]
    joined = observed.merge(means, left_on=['district_id', 'date'], right_index=True, validate='one_to_one')
    check('app_observed_means_reproduce_exact_name_coordinate_subset', len(joined) == len(observed) and near(joined.gwl_current, joined['mean']))
    check('app_observed_well_counts_match_exact_name_coordinate_subset', near(joined.well_count, joined['size']))
    # Frozen reported primary selection is used directly, without error-based filtering.
    inventory = pd.read_csv(ROOT / 'reports/candidates/twelve_month_horizon_20261020/cohorts/full_coordinate_inventory.csv', parse_dates=['date', 'target_date'])
    primary = inventory.loc[inventory.period.eq('primary') & inventory.common_eligible].copy()
    qc = pd.read_csv(OUT / 'district_month_geography_qc.csv', parse_dates=['date'])
    paired = primary.merge(qc.rename(columns={'date': 'target_date'}), on=['district_id', 'target_date'], validate='many_to_one')
    origins = primary.merge(qc, on=['district_id', 'date'], validate='many_to_one')
    return {'fixed_app_feature_snapshot': {
        'rows': len(features), 'districts': sorted(features.district_id.unique()),
        'date_min': str(features.date.min()), 'date_max': str(features.date.max()),
        'duplicate_district_month_rows': int(features.duplicated(['district_id', 'date']).sum()),
        'observed_rows': len(observed), 'imputed_rows': int(features.is_imputed.sum()),
        'missing_gwl_rows': int(features.gwl_current.isna().sum()),
        'units': counts(features.units), 'generation': counts(features.feature_generation),
        'actual_acquisition_at_populated': int(features.actual_acquisition_at.notna().sum()),
        'available_at_populated': int(features.available_at.notna().sum()),
        'numeric_missing': {c: int(features[c].isna().sum()) for c in load(APP/'xgb_fixed_2021_card.json')['features']},
        'strict_accepted_source_rows_for_supported_district': len(strict.loc[strict.district_id.isin(features.district_id.unique())]),
        'source_provider_ids_for_supported_district': int(strict.loc[strict.district_id.isin(features.district_id.unique()), 'provider_well_id'].nunique()),
    }, 'full_coordinate_h12_primary_target_panels': {
        'cases': len(paired), 'districts': int(paired.district_id.nunique()),
        'cases_with_any_source_name_coordinate_conflict': int(paired.conflict.gt(0).sum()),
        'mean_unweighted_target_panel_conflict_share': float(paired.conflict_share.mean()),
        'mean_unweighted_target_panel_unresolved_name_share': float(paired.unknown_share.mean()),
        'cases_with_any_conflict_in_origin_or_target': int((paired.conflict.to_numpy() + origins.conflict.to_numpy() > 0).sum()),
        'target_panels_with_readings_exceeding_listed_depth': int(paired.over_depth.gt(0).sum()),
    }}

def weather_metadata():
    imd = load(ROOT/'data/processed/imd_rainfall_district_monthly.manifest.json')
    era = load(ROOT/'data/processed/era5_district_monthly.manifest.json')
    rain = pd.read_csv(ROOT/'data/processed/imd_rainfall_district_monthly.csv')
    fallback = rain.loc[rain.spatial_method.ne('within')]
    top = fallback.groupby(['st_nm', 'district']).agg(rows=('distance_m', 'size'), max_distance_m=('distance_m', 'max')).sort_values('max_distance_m', ascending=False).head(10)
    with xr.open_dataset(ROOT/'data/processed/era5_india_2002_2024_clean.nc', engine='netcdf4') as dataset:
        variables = {}
        for name in ('t2m', 'pev', 'pet'):
            if name in dataset:
                attrs = dataset[name].attrs
                variables[name] = {key: attrs[key] for key in ('units', 'GRIB_units', 'GRIB_stepType', 'GRIB_stream', 'long_name') if key in attrs}
        time_name = 'valid_time' if 'valid_time' in dataset else 'time'
        times = pd.to_datetime(dataset[time_name].values)
        nc = {'dimensions': dict(dataset.sizes), 'time_min': str(times.min()), 'time_max': str(times.max()), 'variables_allowlisted_metadata': variables}
    active = pd.read_csv(ROOT/'data/processed/features_matrix.csv', parse_dates=['date'])
    monthly = []
    for date, part in active.loc[active.date.ge('2025-01-01')].groupby('date'):
        monthly.append({'month': date.strftime('%Y-%m'), 'source_marked_gwl': int((part.is_observed & ~part.is_imputed).sum()),
                        'finite_imputed_gwl': int((part.is_imputed & part.gwl_current.notna()).sum()),
                        'missing_gwl': int(part.gwl_current.isna().sum()),
                        **{'finite_' + c: int(part[c].notna().sum()) for c in ('rainfall_current', 'temperature', 'evapotranspiration')}})
    tail = active.loc[active.date.isin(pd.to_datetime(['2026-01-01', '2026-02-01']))]
    base = active.loc[active.date.eq('2025-12-01'), ['district_id', 'rainfall_current']]
    joined = tail.merge(base, on='district_id', suffixes=('_tail', '_dec2025'), validate='many_to_one')
    check('national_jan_feb2026_rainfall_is_dec2025_carry_including_missingness', near(joined.rainfall_current_tail, joined.rainfall_current_dec2025))
    # Calendar lag consistency is checked directly from the saved monthly grid.
    for lag in (3, 6):
        mismatch = 0
        for _, part in active.sort_values(['district_id', 'date']).groupby('district_id'):
            mismatch += int((~np.isclose(part['gwl_lag_' + str(lag) + 'mo'], part.gwl_current.shift(lag), rtol=0, atol=1e-10, equal_nan=True)).sum())
        check('national_saved_calendar_gwl_lag_' + str(lag), mismatch == 0, mismatch_rows=mismatch)
    return {'IMD_manifest': {key: imd[key] for key in ('artifact_version', 'units', 'daily_aggregation', 'spatial_fallback', 'baseline_start', 'baseline_end', 'n_years', 'climatology_purpose')},
            'ERA5_manifest': {key: era[key] for key in ('artifact_version', 'units', 'source_evaporation_variable', 'source_evaporation_units', 'source_evaporation_step_type', 'et_conversion', 'spatial_fallback', 'nearest_district_count', 'date_start', 'date_end')},
            'ERA5_retained_nc_metadata': nc,
            'IMD_fallback_top10_district_state_distances': top.reset_index().to_dict(orient='records'),
            'IMD_fallback_district_state_pairs': int(fallback[['district', 'st_nm']].drop_duplicates().shape[0]),
            'active_month_status_2025_2026': monthly,
            'source_release_receipt_revision_availability': 'Not established per contributing value or historical issue time; weather-specific fill flags absent from the feature CSV.',
            'verification_limit': 'Source metadata and conversion/spatial code inspected only. Original annual-grid/monthly spatial aggregation was not regenerated.'}

def main():
    path = OUT/'supplemental_data_summary_20261023.json'
    if path.exists():
        raise FileExistsError(path.name)
    started = datetime.now(timezone.utc).isoformat()
    result = {'started_utc': started, 'acquisition_evidence': acquisition_evidence(),
              'raw_telangana_qc': raw_qc(), 'app_and_cohort': app_and_cohort(),
              'weather_metadata': weather_metadata(), 'checks': CHECKS,
              'completed_utc': datetime.now(timezone.utc).isoformat(),
              'no_model_pipeline_database_or_network_imports': True}
    with path.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, default=str, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': str(path), 'checks': len(CHECKS), 'failed': [c['name'] for c in CHECKS if not c['passed']],
                      'acquired_files': len(result['acquisition_evidence']['acquisitions']),
                      'app_and_cohort': result['app_and_cohort']}, indent=2))
    return int(any(not item['passed'] for item in CHECKS))

if __name__ == '__main__':
    sys.exit(main())
