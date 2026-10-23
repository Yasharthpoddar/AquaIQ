"""Read retained bytes/CSVs only; no AquaIQ pipeline, estimator, DB or network imports.

All output is create-only in this new audit's data directory. Original HTTP
headers are never emitted: only explicitly allowlisted transport metadata is read.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qs

import numpy as np
import pandas as pd
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RUN = ROOT / 'reports/actual_forecast_validation_20261019'
NORM = RUN / 'normalized_v2'
APP = ROOT / 'reports/candidates/twelve_month_horizon_finalization_20261020/artifact'
CHECKS = []
HASHES = []


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(name, value):
    with (OUT / name).open('x', encoding='utf-8', newline='') as f:
        json.dump(value, f, indent=2, allow_nan=False, default=str)
        f.write('\n')


def csv_new(name, value):
    with (OUT / name).open('x', encoding='utf-8', newline='') as f:
        value.to_csv(f, index=False)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def check(name, ok, **details):
    CHECKS.append(dict(name=name, passed=bool(ok), **details))


def pin(path, expected, context):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    actual = sha(path) if path.is_file() else None
    HASHES.append(dict(path=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                       context=context, expected_sha256=expected, actual_sha256=actual,
                       exists=path.is_file(), matches=actual == expected))


def numbers(series):
    return pd.to_numeric(series, errors='coerce').astype(float)


def near(a, b, atol=1e-10):
    return bool(np.allclose(np.asarray(a, float), np.asarray(b, float), atol=atol, rtol=0, equal_nan=True))


def norm(value):
    s = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode()
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', s.lower().replace('&', ' and ')).split())


def basic(frame, keys, date, values):
    result = {'rows': len(frame), 'distinct_keys': len(frame[keys].drop_duplicates()),
              'duplicate_key_rows_beyond_first': int(frame.duplicated(keys).sum()),
              'invalid_dates': int(pd.to_datetime(frame[date], errors='coerce').isna().sum()),
              'date_min': str(frame[date].min()), 'date_max': str(frame[date].max()),
              'numeric': {}}
    for col in values:
        s = numbers(frame[col])
        result['numeric'][col] = {'missing_or_nonnumeric': int(s.isna().sum()),
              'infinite': int(np.isinf(s).sum()), 'negative': int(s.lt(0).sum()),
              'zero': int(s.eq(0).sum()), 'min': float(s.min()) if s.notna().any() else None,
              'max': float(s.max()) if s.notna().any() else None}
    return result


def safe_url(value):
    u = urlsplit(str(value))
    return {'url_without_query': urlunsplit((u.scheme, u.netloc.split('@')[-1], u.path, '', '')),
            'query_parameter_names': sorted(parse_qs(u.query))}


def source_transport():
    manifest = load(RUN / 'source_manifest.json')
    safe = []
    for obj in manifest.get('acquisitions', []):
        item = {}
        for k in ('path', 'relative_path', 'retrieved_at_utc', 'retrieved_at', 'sha256',
                  'bytes', 'status', 'http_status', 'status_code', 'content_type'):
            if k in obj:
                item[k] = obj[k]
        for k in ('url', 'source_url', 'requested_url', 'final_url'):
            if k in obj:
                item[k] = safe_url(obj[k])
        item['headers_not_emitted'] = True
        safe.append(item)
    receipt = load(RUN / 'acquired/telangana_monthly_2007_2026.csv.retrieval.json')
    sanitized = {k: receipt[k] for k in ('retrieved_at_utc', 'retrieved_at', 'sha256', 'bytes',
                                       'status', 'http_status', 'status_code', 'content_type') if k in receipt}
    for k in ('url', 'source_url', 'requested_url', 'final_url'):
        if k in receipt:
            sanitized[k] = safe_url(receipt[k])
    sanitized['headers_not_emitted'] = True
    public = load(ROOT / 'reports/github_release_20261020/PUBLIC_SOURCE_PROVENANCE.json')
    check('public_derivative_identifies_original_private_manifest',
          public['original_local_manifest_sha256'] == sha(RUN / 'source_manifest.json'))
    return {'acquisitions_allowlisted_fields_only': safe,
            'telangana_receipt_allowlisted_fields_only': sanitized,
            'interpretation': 'Transport retrieval time identifies local receipt of current export, not historical per-reading acquisition/publication/availability.'}


def hash_chains():
    quality = load(NORM / 'quality.json')
    pin(RUN / 'acquired/telangana_monthly_2007_2026.csv', quality['source_sha256'], 'normalized_v2 quality')
    for name, expected in quality['outputs_sha256'].items():
        pin(NORM / name, expected, 'normalized_v2 output')
    pin(ROOT / 'data/raw/india_districts.geojson', quality['boundaries_sha256'], 'normalized boundary')
    pin(ROOT / 'data_ingestion/district_crosswalk.csv', quality['crosswalk_sha256'], 'normalized crosswalk')
    scenario = load(ROOT / 'research/experimental_scenario_sources.json')
    for prefix in ('feature_csv', 'feature_manifest', 'district_crosswalk'):
        pin(scenario[prefix + '_path'], scenario[prefix + '_sha256'], 'national scenario lock')
    descriptor = load(ROOT / 'research/twelve_month_app.json')
    compact = json.dumps(descriptor['contract'], sort_keys=True, separators=(',', ':')).encode()
    check('direct_descriptor_canonical_contract_hash', hashlib.sha256(compact).hexdigest() == descriptor['contract_sha256'])
    pin(descriptor['manifest_path'], descriptor['manifest_sha256'], 'direct descriptor')
    manifest = load(APP / 'manifest.json')
    for prefix in ('card', 'snapshot', 'input_provenance', 'provenance'):
        pin(APP / manifest[prefix + '_path'], manifest[prefix + '_sha256'], 'direct bundle manifest')
    card = load(APP / manifest['card_path'])
    pin(APP / card['model_path'], card['model_sha256'], 'direct card model bytes; not loaded')
    for relative, expected in card['input_sha256'].items():
        pin(relative, expected, 'direct card source chain')
    feature_manifest = load(ROOT / 'data/processed/feature_manifest.json')
    pin('data/processed/features_matrix.csv', feature_manifest['feature_csv_sha256'], 'active feature manifest')
    pin('data/processed/preprocessed_wide.csv', feature_manifest['preprocessed_csv_sha256'], 'active feature manifest preprocessed bytes')
    for name in ('imd_rainfall_district_monthly', 'era5_district_monthly'):
        m = load(ROOT / ('data/processed/' + name + '.manifest.json'))
        pin('data/processed/' + name + '.csv', m['csv_sha256'], 'weather export manifest')
        pin('data/raw/india_districts.geojson', m['geojson_sha256'], 'weather boundary')
        if name.startswith('imd'):
            for source in m['sources']:
                p = Path(source['path'])
                if not p.is_absolute():
                    p = ROOT / p
                pin(p, source['sha256'], 'IMD retained annual grid; byte identity only')
        else:
            # Manifest retains an older build-machine path. Current local file has
            # the same expected SHA; this is relocation, not a rewritten manifest.
            pin('data/processed/era5_india_2002_2024_clean.nc', m['source_sha256'], 'ERA5 source relocated from recorded historical path')
    return {'feature_generation_id': feature_manifest['generation_id'],
            'direct_units': card['feature_units'], 'direct_cutoff': card['train_target_cutoff'],
            'direct_allowed_use': card['allowed_use'], 'direct_supported_ids': card['supported_district_ids'],
            'direct_model_sha256': card['model_sha256'], 'no_deserialization': True,
            'national_scenario_units': scenario['units'],
            'national_unit_qualification': scenario['units_qualification']}


def normalized_data():
    raw = pd.read_csv(RUN / 'acquired/telangana_monthly_2007_2026.csv', encoding='cp1252',
                      dtype=str, keep_default_na=False)
    accepted = pd.read_csv(NORM / 'normalized_well_observations.csv', dtype={'provider_well_id': str},
                           parse_dates=['date', 'reported_observation_date'])
    rejected = pd.read_csv(NORM / 'excluded_source_records.csv', dtype={'provider_well_id': str})
    monthly = pd.read_csv(NORM / 'district_monthly_observed.csv', parse_dates=['date'])
    panels = pd.read_csv(NORM / 'panel_membership.csv', dtype={'provider_well_id': str}, parse_dates=['date'])
    features = pd.read_csv(NORM / 'research_features.csv', parse_dates=['date'])
    raw['parsed_reported_date'] = pd.to_datetime(raw['Date'], format='%d-%m-%Y', errors='coerce')
    raw['month'] = raw.parsed_reported_date.dt.to_period('M').dt.to_timestamp()
    raw['depth_numeric'] = numbers(raw['Water Level in mbgl'])
    raw['well_depth_numeric'] = numbers(raw['Well Depth, m'])
    raw_keys = ['Agency', 'Well ID', 'month']
    res = {'raw': basic(raw, raw_keys, 'parsed_reported_date', ['depth_numeric', 'well_depth_numeric']),
            'accepted': basic(accepted, ['agency', 'provider_well_id', 'date'], 'date', ['gwl_m_bgl', 'well_depth_m']),
            'monthly': basic(monthly, ['district_id', 'date'], 'date', ['gwl']),
            'features': basic(features, ['district_id', 'date'], 'date', ['gwl_current', 'rainfall_current', 'temperature', 'evapotranspiration'])}
    for label, frame, idcol in [('raw', raw, 'Well ID'), ('accepted', accepted, 'provider_well_id')]:
        res[label]['provider_ids'] = int(frame[idcol].nunique())
    res['raw']['reported_day_counts'] = {str(k): int(v) for k, v in raw.parsed_reported_date.dt.day.value_counts().sort_index().items()}
    res['raw']['exact_full_record_duplicates_beyond_first'] = int(raw.drop(columns=['parsed_reported_date', 'month', 'depth_numeric', 'well_depth_numeric']).duplicated().sum())
    res['raw']['readings_exceed_listed_well_depth'] = int(raw.depth_numeric.gt(raw.well_depth_numeric).sum())
    res['accepted']['districts'] = int(accepted.district_id.nunique())
    res['accepted']['reported_day_counts'] = {str(k): int(v) for k, v in accepted.reported_observation_date.dt.day.value_counts().sort_index().items()}
    res['accepted']['readings_exceed_listed_well_depth'] = int(accepted.gwl_m_bgl.gt(accepted.well_depth_m).sum())
    res['accepted']['availability_populated'] = {k: int(accepted[k].notna().sum()) for k in ('actual_acquisition_at', 'first_publication_at', 'first_received_at', 'available_at')}
    res['accepted']['aquifer_counts'] = {str(k): int(v) for k, v in accepted.aquifer.value_counts(dropna=False).items()}
    coordinates = accepted[['provider_well_id', 'latitude', 'longitude']].drop_duplicates()
    shared = coordinates.groupby(['latitude', 'longitude']).provider_well_id.nunique()
    res['accepted']['coordinate_pairs_shared_by_multiple_ids'] = int(shared.gt(1).sum())
    metadata = ['latitude', 'longitude', 'well_depth_m', 'aquifer', 'well_type', 'district_name', 'site_name']
    variation = accepted.groupby(['agency', 'provider_well_id'])[metadata].nunique(dropna=False)
    res['accepted']['provider_ids_with_cross_time_metadata_change_after_exclusions'] = int(variation.gt(1).any(axis=1).sum())
    res['rejected_rows'] = len(rejected)
    res['exclusion_reason_counts'] = {str(k): int(v) for k, v in rejected.exclusion_reason.str.split(';').explode().value_counts().items()}
    check('accepted_plus_excluded_partition_raw_source', len(accepted) + len(rejected) == len(raw)
          and set(accepted.source_record_number).isdisjoint(set(rejected.source_record_number))
          and set(accepted.source_record_number) | set(rejected.source_record_number) == set(range(1, len(raw) + 1)))
    source_rows = raw.iloc[accepted.source_record_number.to_numpy() - 1].reset_index(drop=True)
    check('accepted_depths_reproduce_exact_source_rows', near(accepted.gwl_m_bgl, source_rows.depth_numeric))
    check('accepted_provider_ids_reproduce_source_rows', accepted.provider_well_id.str.strip().equals(source_rows['Well ID'].str.strip()))
    check('accepted_source_dates_reproduce_exact_day_before_month_normalization',
          accepted.reported_observation_date.reset_index(drop=True).equals(source_rows.parsed_reported_date)
          and accepted.date.equals(accepted.reported_observation_date.dt.to_period('M').dt.to_timestamp()))
    means = accepted.groupby(['district_id', 'date']).gwl_m_bgl.agg(['mean', 'size'])
    joined = monthly.merge(means, left_on=['district_id', 'date'], right_index=True, validate='one_to_one')
    check('district_arithmetic_means_independently_recomputed', near(joined.gwl, joined['mean']), max_absolute_difference_m=float(np.abs(joined.gwl - joined['mean']).max()))
    check('equal_reading_count_and_provider_count_per_month', np.array_equal(joined.well_count, joined['size']) and np.array_equal(joined.reading_count, joined['size']))
    panel_sum = panels.groupby(['district_id', 'date']).weight.sum()
    size = panels.groupby(['district_id', 'date']).provider_well_id.transform('size')
    check('panel_weights_sum_one_and_equal_weight', near(panel_sum, np.ones(len(panel_sum))) and near(panels.weight, 1 / size))
    panel_hash_mismatches = 0
    for _, part in panels.groupby(['district_id', 'date'], sort=False):
        values = [{'agency': r.agency, 'provider_well_id': r.provider_well_id, 'weight': 1 / len(part)}
                  for r in part.sort_values(['agency', 'provider_well_id']).itertuples()]
        expected = hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        panel_hash_mismatches += int(not part.panel_sha256.eq(expected).all())
    check('all_panel_hashes_independently_recomputed', panel_hash_mismatches == 0, panels_checked=len(panel_sum), mismatches=panel_hash_mismatches)
    # Direct CSV reconstruction of bounded causal GWL and exact calendar lags.
    feature_mismatches = Counter()
    monthly_lookup = monthly.set_index(['district_id', 'date']).gwl
    for did, part in features.groupby('district_id', sort=False):
        part = part.sort_values('date')
        direct = monthly_lookup.reindex(pd.MultiIndex.from_arrays([[did] * len(part), part.date])).to_numpy()
        expected = pd.Series(direct).ffill(limit=3)
        feature_mismatches['gwl_current'] += int((~np.isclose(part.gwl_current, expected, rtol=0, atol=1e-10, equal_nan=True)).sum())
        feature_mismatches['is_observed'] += int((part.is_observed.to_numpy() != np.isfinite(direct)).sum())
        feature_mismatches['is_imputed'] += int((part.is_imputed.to_numpy() != (~np.isfinite(direct) & np.isfinite(expected))).sum())
        for lag in (3, 6):
            feature_mismatches['gwl_lag_' + str(lag)] += int((~np.isclose(part['gwl_lag_' + str(lag) + 'mo'], expected.shift(lag), rtol=0, atol=1e-10, equal_nan=True)).sum())
    res['causal_gwl_reconstruction_mismatches'] = dict(feature_mismatches)
    check('retained_research_gwl_locf3_observation_flags_and_calendar_lags_recomputed', not any(feature_mismatches.values()))
    return res, accepted, monthly, features


def geography(accepted, monthly):
    cw = pd.read_csv(ROOT / 'data_ingestion/district_crosswalk.csv', dtype=str, keep_default_na=False)
    lookup = defaultdict(set)
    for r in cw.itertuples():
        lookup[(norm(r.canonical_state), norm(r.canonical_name))].add(r.canonical_district_id)
    boundaries = load(ROOT / 'data/raw/india_districts.geojson')
    polygons, identities = [], []
    for feature in boundaries['features']:
        p = feature['properties']
        if not p.get('district'):
            continue
        candidates = lookup[(norm(p['st_nm']), norm(p['district']))]
        if len(candidates) != 1:
            raise ValueError('Independent boundary canonical resolution is ambiguous')
        polygons.append(shape(feature['geometry']))
        identities.append(next(iter(candidates)))
    tree = STRtree(polygons)
    coords = accepted[['latitude', 'longitude']].drop_duplicates()
    assigned = {}
    for r in coords.itertuples():
        p = Point(r.longitude, r.latitude)
        candidates = {identities[int(i)] for i in tree.query(p, predicate='intersects')}
        assigned[(r.latitude, r.longitude)] = next(iter(candidates)) if len(candidates) == 1 else None
    spatial_ids = [assigned[(r.latitude, r.longitude)] for r in accepted.itertuples()]
    named_ids = []
    for r in accepted.itertuples():
        candidates = lookup.get((norm(r.state_name), norm(r.district_name)), set())
        named_ids.append(next(iter(candidates)) if len(candidates) == 1 else None)
    named = pd.Series(named_ids, index=accepted.index)
    conflict = named.notna() & named.ne(accepted.district_id)
    unknown = named.isna()
    agree = named.notna() & named.eq(accepted.district_id)
    check('accepted_saved_coordinate_districts_match_independent_polygon_intersection', accepted.district_id.tolist() == spatial_ids,
          unique_coordinate_pairs_checked=len(coords), all_rows=len(accepted))
    check('accepted_saved_name_ids_match_independent_crosswalk_resolution', named.fillna('').tolist() == accepted.source_name_district_id.fillna('').tolist())
    check('accepted_saved_name_conflict_flag_matches_independent_resolution', np.array_equal(conflict, accepted.source_name_differs_from_fixed_boundary))
    n = len(accepted)
    res = {'accepted_rows': n, 'resolvable_name_coordinate_conflicts': int(conflict.sum()),
            'unresolved_source_names': int(unknown.sum()), 'exact_name_coordinate_agreement': int(agree.sum()),
            'conflict_fraction_of_all_accepted': float(conflict.mean()),
            'conflict_fraction_of_resolvable_names': float(conflict.sum() / named.notna().sum()),
            'unknown_name_fraction': float(unknown.mean()), 'exact_agreement_fraction': float(agree.mean()),
            'independently_rechecked_coordinate_pairs': len(coords),
            'not_authoritative_location_verification': True}
    agg = accepted[['district_id', 'date', 'gwl_m_bgl', 'well_depth_m']].copy()
    agg['conflict'] = conflict
    agg['unknown'] = unknown
    agg['over_depth'] = agg.gwl_m_bgl.gt(agg.well_depth_m)
    qc = agg.groupby(['district_id', 'date']).agg(total=('conflict', 'size'), conflict=('conflict', 'sum'), unknown=('unknown', 'sum'), over_depth=('over_depth', 'sum')).reset_index()
    for c in ('conflict', 'unknown', 'over_depth'):
        qc[c + '_share'] = qc[c] / qc.total
    csv_new('district_month_geography_qc.csv', qc)
    cohort = pd.read_csv(ROOT / 'reports/candidates/twelve_month_horizon_20261020/cohorts/full_coordinate_inventory.csv', parse_dates=['date', 'target_date'])
    # Selection is the frozen reported primary cohort, never chosen from errors.
    primary = cohort.loc[cohort.primary_common].copy() if 'primary_common' in cohort else None
    if primary is None:
        res['primary_inventory_columns'] = list(cohort.columns)
    else:
        paired = primary.merge(qc.rename(columns={'date': 'target_date'}), on=['district_id', 'target_date'], validate='many_to_one')
        res['primary_panels'] = {'cases': len(paired), 'cases_with_any_conflict': int(paired.conflict.gt(0).sum()),
             'mean_conflict_share': float(paired.conflict_share.mean()), 'mean_unresolved_share': float(paired.unknown_share.mean()),
             'panels_with_depth_exceeds_listed_well_depth': int(paired.over_depth.gt(0).sum())}
    return res


def weather_and_active(features):
    active = pd.read_csv(ROOT / 'data/processed/features_matrix.csv', parse_dates=['date'])
    imd = pd.read_csv(ROOT / 'data/processed/imd_rainfall_district_monthly.csv')
    era = pd.read_csv(ROOT / 'data/processed/era5_district_monthly.csv')
    for df in (imd, era):
        df['date'] = pd.to_datetime(dict(year=df.year, month=df.month, day=1))
    res = {'active_features': basic(active, ['district_id', 'date'], 'date', ['gwl_current', 'rainfall_current', 'temperature', 'evapotranspiration']),
           'IMD_export': basic(imd, ['district', 'st_nm', 'year', 'month'], 'date', ['rainfall_mm']),
           'ERA5_export': basic(era, ['district', 'st_nm', 'year', 'month'], 'date', ['temperature', 'evapotranspiration'])}
    for label, df in [('IMD_export', imd), ('ERA5_export', era)]:
        res[label]['district_state_pairs'] = len(df[['district', 'st_nm']].drop_duplicates())
    res['IMD_export']['spatial_method_counts'] = {str(k): int(v) for k, v in imd.spatial_method.value_counts(dropna=False).items()}
    res['IMD_export']['nearest_max_distance_m'] = float(imd.distance_m.max())
    obs = active.is_observed & ~active.is_imputed & np.isfinite(active.gwl_current)
    imp = active.is_imputed & np.isfinite(active.gwl_current)
    res['active_features'].update({'districts': int(active.district_id.nunique()), 'source_marked_observed_rows': int(obs.sum()),
        'finite_imputed_rows': int(imp.sum()), 'missing_gwl_rows': int((~np.isfinite(active.gwl_current)).sum()),
        'observed_and_imputed_rows': int((active.is_observed & active.is_imputed).sum()),
        'finite_without_observed_or_imputed_flags': int((np.isfinite(active.gwl_current) & ~(active.is_observed | active.is_imputed)).sum())})
    newest = active.date.max()
    now = pd.Period('2026-10', freq='M')
    freshness = []
    for did, part in active.groupby('district_id'):
        observed = part.loc[part.is_observed & ~part.is_imputed & np.isfinite(part.gwl_current)]
        last = observed.date.max() if len(observed) else None
        freshness.append({'district_id': did, 'source_marked_observation_months': len(observed),
            'latest_source_marked_month': last.strftime('%Y-%m') if last is not None else None,
            'calendar_age_at_october2026': int(now.ordinal - last.to_period('M').ordinal) if last is not None else None,
            'finite_imputed_months': int((part.is_imputed & np.isfinite(part.gwl_current)).sum()),
            'finite_current_gwl_in_latest_grid_month': bool(np.isfinite(part.loc[part.date.eq(newest), 'gwl_current']).any())})
    fresh = pd.DataFrame(freshness)
    csv_new('district_freshness.csv', fresh)
    res['active_features']['latest_source_marked_month_district_counts'] = {str(k): int(v) for k, v in fresh.latest_source_marked_month.fillna('NONE').value_counts().sort_index().items()}
    res['active_features']['only_imputed_lifetime_districts'] = int((fresh.source_marked_observation_months.eq(0) & fresh.finite_imputed_months.gt(0)).sum())
    res['active_features']['latest_grid_month'] = newest.strftime('%Y-%m')
    res['active_features']['latest_grid_finite_gwl_districts'] = int(fresh.finite_current_gwl_in_latest_grid_month.sum())
    for col in ('rainfall_current', 'temperature', 'evapotranspiration'):
        res['active_features']['latest_finite_' + col] = str(active.loc[np.isfinite(active[col]), 'date'].max())
    # Copy identity and missingness, independently of the research adapter.
    weather_cols = ['rainfall_current', 'rainfall_3mo_avg', 'monsoon_deficit_pct', 'temperature', 'evapotranspiration', 'water_balance_proxy']
    joint = features[['district_id', 'date', *weather_cols]].merge(active[['district_id', 'date', *weather_cols]], on=['district_id', 'date'], suffixes=('_research', '_active'), validate='one_to_one')
    check('normalized_research_existing_weather_exact_key_copy_including_missingness', len(joint) == len(features) and all(near(joint[c + '_research'], joint[c + '_active']) for c in weather_cols), rows_checked=len(joint))
    check('active_water_balance_is_rainfall_minus_ET', near(active.water_balance_proxy, active.rainfall_current - active.evapotranspiration))
    # Tail is 2024-12 ERA5 carried exactly to Jan/Feb2025, never new climate observation.
    tails = features.loc[features.date.isin(pd.to_datetime(['2025-01-01', '2025-02-01']))]
    base = features.loc[features.date.eq(pd.Timestamp('2024-12-01')), ['district_id', 'temperature', 'evapotranspiration']]
    tail = tails.merge(base, on='district_id', suffixes=('_tail', '_dec2024'), validate='many_to_one')
    res['weather_carry_tail'] = {'research_jan_feb2025_rows': len(tail),
        'temperature_equal_dec2024': int(np.isclose(tail.temperature_tail, tail.temperature_dec2024).sum()),
        'ET_equal_dec2024': int(np.isclose(tail.evapotranspiration_tail, tail.evapotranspiration_dec2024).sum()),
        'interpretation': 'Existing bounded carries, not newly observed 2025 ERA5; historical availability unverified.'}
    return res


def git_asset_visibility():
    files = sorted({h['path'].replace('\\', '/') for h in HASHES})
    tracked_reply = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True)
    tracked = set(tracked_reply.stdout.decode().split('\0'))
    ignored_reply = subprocess.run(['git', 'check-ignore', '--stdin', '-z'], cwd=ROOT,
        input=('\0'.join(files) + '\0').encode(), capture_output=True)
    if ignored_reply.returncode not in (0, 1):
        raise RuntimeError('git check-ignore failed')
    ignored = set(ignored_reply.stdout.decode().split('\0'))
    result = [{'path': f, 'tracked': f in tracked, 'ignored': f in ignored} for f in files]
    return {'commands': [{'command': 'git ls-files -z', 'exit_status': tracked_reply.returncode},
                         {'command': 'git check-ignore --stdin -z', 'exit_status': ignored_reply.returncode}],
            'asset_counts': {'tracked': sum(x['tracked'] for x in result),
                             'ignored_untracked': sum(x['ignored'] and not x['tracked'] for x in result)},
            'assets': result}


def main():
    if (OUT / 'data_summary.json').exists():
        raise FileExistsError('Audit output already exists; never overwrite evidence')
    started = datetime.now(timezone.utc).isoformat()
    identities = hash_chains()
    transport = source_transport()
    normalized, accepted, monthly, features = normalized_data()
    geo = geography(accepted, monthly)
    weather = weather_and_active(features)
    visibility = git_asset_visibility()
    write('hash_verification.json', {'checks': HASHES, 'total': len(HASHES),
          'mismatches': [x for x in HASHES if not x['matches']]})
    write('source_transport_safe.json', transport)
    write('source_asset_visibility.json', visibility)
    summary = {'started_utc': started, 'completed_utc': datetime.now(timezone.utc).isoformat(),
               'identities': identities, 'normalized_telangana': normalized, 'geography': geo,
               'weather_and_active_release': weather, 'checks': CHECKS,
               'method': 'Independent direct retained-byte/hash/CSV arithmetic and polygon intersection; no AquaIQ pipeline/model/DB/network imports or commands.',
               'limitations': ['Hashes establish retained byte identity, not provider authenticity or per-reading historical availability.',
                 'Weather conversion/spatial code and metadata inspected; full original grid aggregation not regenerated.',
                 'Provider IDs and equal weights are reproducible proxies, not certified physical-well/replacement/datum continuity.']}
    write('data_summary.json', summary)
    print(json.dumps({'checks': len(CHECKS), 'failed': [x['name'] for x in CHECKS if not x['passed']],
                      'hash_checks': len(HASHES), 'hash_mismatches': sum(not x['matches'] for x in HASHES),
                      'accepted_rows': len(accepted), 'geography': geo, 'output': str(OUT)}, indent=2))
    return int(any(not x['passed'] for x in CHECKS) or any(not x['matches'] for x in HASHES))


if __name__ == '__main__':
    sys.exit(main())
