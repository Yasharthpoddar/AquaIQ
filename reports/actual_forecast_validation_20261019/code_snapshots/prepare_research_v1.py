"""Offline, candidate-only normalization of the official Telangana monthly file.

No fitting, database access, network access, production writes or issuance occurs.
The source Date is a reported date/month label; acquisition and availability are
unknown. Provider well IDs are retained, without certifying replacement history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_ingestion.cgwb_updates import (  # noqa: E402
    build_district_lookup, normalized_state, resolve_district, spatial_districts,
)
from preprocessing.pipeline import (  # noqa: E402
    apply_causal_gwl_imputation, reindex_district_monthly,
)
from preprocessing.features import build_gwl_features  # noqa: E402
from models import xgboost_model as forecast  # noqa: E402

RUN = Path(__file__).resolve().parent
FIELDS = {
    'Well ID': 'provider_well_id', 'State Name (as per LGD)': 'state_name',
    'District Name (as per LGD)': 'district_name', 'Block Name (as per LGD)': 'block',
    'Village (as per LGD, if available)': 'village', 'Site Name': 'site_name',
    'Latitude': 'latitude', 'Longitude': 'longitude', 'Well Type': 'well_type',
    'Well Depth, m': 'well_depth_m',
    'Aquifer Tapped (Unconfined, Semi-Confined, Confined)': 'aquifer',
    'Agency': 'agency', 'Date': 'reported_date_text', 'Water Level in mbgl': 'gwl_m_bgl',
}
IDENTITY = ['state_name', 'district_name', 'block', 'village', 'site_name',
            'latitude', 'longitude', 'well_type', 'well_depth_m', 'aquifer', 'agency']
WEATHER = [c for c in forecast.CANONICAL_FEATURE_COLS if c not in
           ('gwl_current', 'gwl_lag_3mo', 'gwl_lag_6mo')]


def sha(path):
    return forecast.sha256_file(path)


def reject(frame, mask, reason):
    mask = pd.Series(mask, index=frame.index).fillna(False).astype(bool)
    frame.loc[mask, 'exclusion_reason'] = frame.loc[mask, 'exclusion_reason'].map(
        lambda value: value + (';' if value else '') + reason)


def audit_rows(raw, *, end='2026-09-01'):
    """Reject conflicts within a well-month; later metadata never excludes past rows."""
    missing = set(FIELDS) - set(raw)
    if missing:
        raise ValueError(f'Explicit mbgl and provider schema required; missing {sorted(missing)}')
    frame = raw[list(FIELDS)].rename(columns=FIELDS).copy().reset_index(drop=True)
    frame['source_record_number'] = np.arange(1, len(frame) + 1)
    for column in frame:
        if column != 'source_record_number':
            frame[column] = frame[column].astype('string').fillna('').str.strip()
    frame['exclusion_reason'] = ''
    # Exact-format parsing avoids month-first inference. Keep the provider text.
    frame['reported_observation_date'] = pd.to_datetime(
        frame.reported_date_text, format='%d-%m-%Y', errors='coerce')
    frame['date'] = frame.reported_observation_date.dt.to_period('M').dt.to_timestamp()
    for column in ('latitude', 'longitude', 'well_depth_m', 'gwl_m_bgl'):
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    reject(frame, frame.provider_well_id.eq(''), 'missing_provider_well_id')
    reject(frame, frame.agency.eq(''), 'missing_agency')
    reject(frame, frame.state_name.map(normalized_state).ne('telangana'), 'unexpected_source_state')
    reject(frame, frame.reported_observation_date.isna(), 'invalid_reported_date')
    reject(frame, frame.date.gt(pd.Timestamp(end).to_period('M').to_timestamp()), 'outside_registered_month_range')
    reject(frame, ~np.isfinite(frame.gwl_m_bgl), 'nonfinite_depth')
    # Preserve the existing nonnegative model-input policy; negative source values
    # could represent artesian heads and are not independently deemed bad data.
    reject(frame, frame.gwl_m_bgl.lt(0), 'negative_depth_outside_existing_model_contract')
    reject(frame, ~np.isfinite(frame.latitude) | ~frame.latitude.between(6, 38)
           | ~np.isfinite(frame.longitude) | ~frame.longitude.between(68, 98), 'invalid_india_coordinates')
    reject(frame, frame.aquifer.eq(''), 'missing_aquifer_metadata')
    keys = ['agency', 'provider_well_id', 'date']
    grouped = frame.groupby(keys, dropna=False)
    value_conflict = grouped.gwl_m_bgl.transform('nunique', dropna=False).gt(1)
    date_conflict = grouped.reported_observation_date.transform('nunique', dropna=False).gt(1)
    metadata_conflict = pd.Series(False, index=frame.index)
    for column in IDENTITY:
        metadata_conflict |= grouped[column].transform('nunique', dropna=False).gt(1)
    reject(frame, value_conflict, 'conflicting_well_month_depths')
    reject(frame, date_conflict, 'multiple_reported_dates_in_well_month')
    reject(frame, metadata_conflict, 'conflicting_well_month_metadata')
    duplicates = frame.duplicated(keys + ['reported_observation_date', 'gwl_m_bgl', *IDENTITY], keep='first')
    reject(frame, duplicates & ~value_conflict & ~date_conflict & ~metadata_conflict, 'exact_duplicate_well_month')
    # These are descriptive, hindsight metadata diagnostics, never eligibility filters.
    variations = frame.groupby(['agency', 'provider_well_id'], dropna=False)[IDENTITY].nunique(dropna=False)
    changed = variations.gt(1)
    diagnostics = {'provider_ids_with_cross_time_metadata_variation': int(changed.any(axis=1).sum()),
        'cross_time_variation_by_field': {c: int(changed[c].sum()) for c in IDENTITY},
        'cross_time_metadata_variations': [{'agency': key[0], 'provider_well_id': key[1],
            'varying_fields': [c for c in IDENTITY if bool(row[c])]}
            for key, row in changed.loc[changed.any(axis=1)].iterrows()],
        'metadata_variation_policy': 'Descriptive current-vintage QC only; never excludes earlier observations.',
        'aquifer_counts_before_exclusions': {str(k): int(v) for k, v in frame.aquifer.value_counts(dropna=False).items()},
        'all_aquifers_retained_if_otherwise_eligible': True}
    for column in ('actual_acquisition_at', 'first_publication_at', 'first_received_at', 'available_at'):
        frame[column] = pd.NA
    frame['date_semantics'] = 'provider_reported_date_or_month_label_acquisition_freshness_unknown'
    frame['units'] = 'm_bgl'
    return frame, diagnostics


def map_districts(frame, crosswalk, boundaries):
    """Use fixed polygons, state-check and preserve name disagreements; never snap."""
    lookup = build_district_lookup(crosswalk)
    frame = frame.copy()
    coordinates = frame[['latitude', 'longitude']].drop_duplicates().reset_index(drop=True)
    resolved = spatial_districts(coordinates, boundaries, lookup)
    coordinates['district_id'] = [x[0] for x in resolved]
    coordinates['mapping_basis'] = [x[1] for x in resolved]
    frame = frame.merge(coordinates, on=['latitude', 'longitude'], how='left', validate='many_to_one')
    named = [resolve_district(r.state_name, r.district_name, lookup) for r in frame.itertuples()]
    frame['source_name_district_id'] = [x[0] for x in named]
    frame['source_name_mapping_status'] = [x[1] for x in named]
    reject(frame, frame.district_id.isna(), 'unresolved_or_ambiguous_canonical_boundary')
    mismatch = pd.Series([pd.notna(did) and normalized_state(lookup['canonical'][did][1])
        != normalized_state(state) for did, state in zip(frame.district_id, frame.state_name)], index=frame.index)
    reject(frame, mismatch, 'source_state_disagrees_with_boundary')
    frame['source_name_differs_from_fixed_boundary'] = (frame.source_name_district_id.notna()
        & frame.district_id.notna() & frame.source_name_district_id.ne(frame.district_id))
    return frame


def aggregate_monthly(accepted):
    """One clean reading per provider-well/month; equal reading weights as existing policy."""
    if accepted.duplicated(['agency', 'provider_well_id', 'date']).any():
        raise ValueError('Conflicting/duplicate well-months must be resolved explicitly before aggregation')
    monthly, membership = [], []
    for (district, month), rows in accepted.groupby(['district_id', 'date'], sort=True):
        rows = rows.sort_values(['agency', 'provider_well_id'])
        panel = [{'agency': r.agency, 'provider_well_id': r.provider_well_id, 'weight': 1 / len(rows)}
                 for r in rows.itertuples()]
        panel_hash = hashlib.sha256(json.dumps(panel, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        monthly.append({'district_id': district, 'date': month, 'gwl': float(rows.gwl_m_bgl.mean()),
            'well_count': len(rows), 'reading_count': len(rows), 'panel_sha256': panel_hash,
            'first_reported_date': rows.reported_observation_date.min(),
            'last_reported_date': rows.reported_observation_date.max(),
            'aquifer_counts_json': json.dumps(rows.aquifer.value_counts().to_dict(), sort_keys=True),
            'units': 'm_bgl', 'actual_acquisition_at': None, 'available_at': None})
        for r in rows.itertuples():
            membership.append({'district_id': district, 'date': month, 'agency': r.agency,
                'provider_well_id': r.provider_well_id, 'weight': 1 / len(rows),
                'source_record_number': r.source_record_number,
                'gwl_m_bgl': r.gwl_m_bgl, 'reported_observation_date': r.reported_observation_date,
                'latitude': r.latitude, 'longitude': r.longitude, 'aquifer': r.aquifer,
                'well_depth_m': r.well_depth_m, 'panel_sha256': panel_hash})
    return pd.DataFrame(monthly), pd.DataFrame(membership)


def build_research_features(monthly, weather, *, end='2026-09-01', start=None):
    """Reuse causal GWL helpers; exact-key-copy existing weather without new filling."""
    if monthly.empty:
        raise ValueError('No eligible source-backed district-months')
    weather = forecast.encode_crop_season(weather)
    if weather.duplicated(['district_id', 'date']).any():
        raise ValueError('Weather source has duplicate district-months')
    absent = set(WEATHER) - set(weather)
    if absent:
        raise ValueError(f'Weather feature schema missing: {sorted(absent)}')
    start = str(pd.Timestamp(start or monthly.date.min()).to_period('M').to_timestamp().date())
    parts = []
    for _, rows in monthly.groupby('district_id', sort=True):
        regular = reindex_district_monthly(rows[['district_id', 'date', 'gwl']], start, end)
        parts.append(apply_causal_gwl_imputation(regular, max_locf_gap=3))
    grid = pd.concat(parts, ignore_index=True)
    grid = build_gwl_features(grid).rename(columns={'GWL_current': 'gwl_current',
        'GWL_lag_3mo': 'gwl_lag_3mo', 'GWL_lag_6mo': 'gwl_lag_6mo'})
    copied = weather[['district_id', 'date', *WEATHER]].copy()
    copied['date'] = pd.to_datetime(copied.date)
    copied['weather_key_present'] = True
    grid = grid.merge(copied, on=['district_id', 'date'], how='left', validate='one_to_one')
    grid['weather_key_present'] = grid.weather_key_present.fillna(False).astype(bool)
    grid = grid.merge(monthly.drop(columns=['gwl']), on=['district_id', 'date'],
                      how='left', validate='one_to_one')
    grid['origin_month_sin'] = np.sin(2 * np.pi * grid.date.dt.month / 12)
    grid['origin_month_cos'] = np.cos(2 * np.pi * grid.date.dt.month / 12)
    grid['feature_generation'] = 'research-telangana-mbgl-existing-weather-v1'
    grid['source_role'] = 'retrospective_current_vintage_not_issuance_verified'
    return grid.sort_values(['district_id', 'date']).reset_index(drop=True)


def write_csv_new(path, frame):
    with Path(path).open('x', encoding='utf-8', newline='') as handle:
        frame.to_csv(handle, index=False)


def prepare(source, output, *, end='2026-09-01', encoding='cp1252'):
    import geopandas as gpd
    source, output = Path(source).resolve(), Path(output).resolve()
    if not output.is_relative_to(RUN) or output == RUN or output.exists():
        raise ValueError('Use a new, absent normalized output directory within this research run')
    if not source.is_relative_to(RUN / 'acquired'):
        raise ValueError('Source must be an isolated acquisition in this research run')
    feature_path = ROOT / 'data/processed/features_matrix.csv'
    manifest_path = ROOT / 'data/processed/feature_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if sha(feature_path) != manifest['feature_csv_sha256']:
        raise ValueError('Existing verified weather feature bytes changed')
    weather = pd.read_csv(feature_path, parse_dates=['date'])
    forecast.validate_feature_generation(weather, manifest)
    crosswalk_path = ROOT / 'data_ingestion/district_crosswalk.csv'
    boundary_path = ROOT / 'data/raw/india_districts.geojson'
    crosswalk = pd.read_csv(crosswalk_path, dtype=str, keep_default_na=False)
    raw = pd.read_csv(source, encoding=encoding, dtype=str, keep_default_na=False,
                      encoding_errors='strict')
    audit, qc = audit_rows(raw, end=end)
    audit = map_districts(audit, crosswalk, gpd.read_file(boundary_path))
    accepted = audit.loc[audit.exclusion_reason.eq('')].copy()
    monthly, panels = aggregate_monthly(accepted)
    features = build_research_features(monthly, weather, end=end)
    reasons = audit.exclusion_reason.str.split(';').explode()
    qc.update({'source': str(source.relative_to(ROOT)), 'source_sha256': sha(source),
        'source_bytes': source.stat().st_size, 'encoding': encoding,
        'encoding_policy': 'Strict decoding, no replacement; source bytes remain immutable.',
        'weather_features_source': str(feature_path.relative_to(ROOT)), 'weather_sha256': sha(feature_path),
        'weather_generation': manifest['generation_id'], 'weather_columns_copied_without_changes': WEATHER,
        'crosswalk_sha256': sha(crosswalk_path), 'boundaries_sha256': sha(boundary_path),
        'input_rows': len(raw), 'accepted_rows': len(accepted), 'excluded_rows': len(audit) - len(accepted),
        'exclusion_reason_counts': {str(k): int(v) for k, v in reasons[reasons.ne('')].value_counts().items()},
        'provider_wells_accepted': int(accepted.provider_well_id.nunique()),
        'canonical_districts': int(monthly.district_id.nunique()), 'district_months': len(monthly),
        'reported_date_min': str(accepted.reported_observation_date.min()),
        'reported_date_max': str(accepted.reported_observation_date.max()),
        'reported_dates_all_first_day': bool(accepted.reported_observation_date.dt.day.eq(1).all()),
        'measurement_dates_or_month_labels': 'Not independently distinguished; no actual acquisition time inferred.',
        'mapping_basis_counts': {str(k): int(v) for k, v in audit.mapping_basis.value_counts(dropna=False).items()},
        'name_mapping_status_counts': {str(k): int(v) for k, v in audit.source_name_mapping_status.value_counts(dropna=False).items()},
        'source_name_boundary_disagreement_rows': int(audit.source_name_differs_from_fixed_boundary.sum()),
        'aggregation': 'Equal weights over one clean reported observation per agency/provider-well/calendar month; no conflicting month averaged.',
        'panel_contract': 'Observed monthly membership and weights, not a preregistered fixed panel or certified replacement continuity.',
        'datum': 'Source header explicitly says mbgl; measuring-point changes and well replacement history unknown.',
        'availability': 'Acquisition/publication/receipt/availability times unknown per value; current-vintage historical research only.',
        'missing_policy': 'Groundwater LOCF up to3months, exact calendar lags3/6; targets use observed rows only; existing weather copied with its missingness.',
        'end_month': str(pd.Timestamp(end).date()), 'feature_rows': len(features),
        'observed_feature_rows': int(features.is_observed.sum()),
        'weather_missing_key_rows': int((~features.weather_key_present).sum()),
        'weather_nonfinite_counts_on_observed_origins': {c: int(features.loc[features.is_observed, c].isna().sum()) for c in WEATHER},
        'aquifer_counts_accepted': {str(k): int(v) for k, v in accepted.aquifer.value_counts().items()},
        'code_sha256': sha(Path(__file__))})
    output.mkdir(parents=False, exist_ok=False)
    outputs = {'normalized_well_observations.csv': accepted, 'excluded_source_records.csv': audit.loc[audit.exclusion_reason.ne('')],
               'district_monthly_observed.csv': monthly, 'panel_membership.csv': panels,
               'research_features.csv': features,
               'district_mapping_inventory.csv': audit[['state_name', 'district_name', 'district_id',
                   'mapping_basis', 'source_name_district_id', 'source_name_mapping_status',
                   'source_name_differs_from_fixed_boundary']].drop_duplicates()}
    for name, frame in outputs.items():
        write_csv_new(output / name, frame)
    qc['outputs_sha256'] = {name: sha(output / name) for name in outputs}
    with (output / 'quality.json').open('x', encoding='utf-8') as handle:
        json.dump(qc, handle, indent=2, allow_nan=False)
    return qc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--end', default='2026-09-01')
    parser.add_argument('--encoding', default='cp1252')
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output_dir, end=args.end, encoding=args.encoding), indent=2))


if __name__ == '__main__':
    main()
