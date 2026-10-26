"""Build an immutable, offline feature snapshot from audited official observations.

Only missing measured district months are filled. Existing measurements and
weather features are preserved. Groundwater carry-forward and calendar lags use
the existing physical-v3 functions; the deployed CSV and database are untouched.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from models.district_registry import get_registry
from models.xgboost_model import (load_feature_matrix, observed_mask, sha256_file,
    dataframe_hash, validate_feature_generation, _write_json)
from preprocessing.pipeline import apply_causal_gwl_imputation
from preprocessing.features import build_gwl_features, FEATURES_LIST

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'official-missing-month-overlay-v2'
GWL_COLUMNS = ['GWL_current', 'GWL_lag_3mo', 'GWL_lag_6mo',
               'gwl_current', 'gwl_lag_3mo', 'gwl_lag_6mo']


def validate_months(frame, *, as_of, registry_ids):
    required = {'district_id', 'date', 'gwl_mean', 'station_count', 'reading_count',
        'first_observation_date', 'last_observation_date', 'source', 'metric', 'units', 'is_observed'}
    if required - set(frame):
        raise ValueError(f'Candidate lacks observation provenance: {sorted(required - set(frame))}')
    frame = frame.copy()
    for column in ('date', 'first_observation_date', 'last_observation_date'):
        frame[column] = pd.to_datetime(frame[column], errors='coerce')
    frame['gwl_mean'] = pd.to_numeric(frame.gwl_mean, errors='coerce')
    cutoff = pd.Timestamp(as_of).normalize()
    month_end = cutoff.to_period('M').to_timestamp() - pd.offsets.MonthBegin(1)
    if (frame.empty or frame.duplicated(['district_id', 'date']).any()
            or set(frame.district_id) - set(registry_ids)
            or frame[['date', 'first_observation_date', 'last_observation_date']].isna().any().any()
            or not frame.date.dt.is_month_start.all() or frame.date.gt(month_end).any()
            or frame.first_observation_date.gt(frame.last_observation_date).any()
            or frame.last_observation_date.gt(cutoff).any()
            or not frame.first_observation_date.dt.to_period('M').eq(frame.date.dt.to_period('M')).all()
            or not frame.last_observation_date.dt.to_period('M').eq(frame.date.dt.to_period('M')).all()
            or not np.isfinite(frame.gwl_mean).all() or frame.gwl_mean.lt(0).any()
            or not frame.is_observed.astype('string').str.lower().eq('true').all()
            or not frame.source.eq('CGWB').all() or not frame.metric.eq('GWL').all()
            or not frame.units.eq('m_bgl').all()):
        raise ValueError('Candidate has invalid canonical observations, depth units or dates.')
    for column in ('station_count', 'reading_count'):
        values = pd.to_numeric(frame[column], errors='coerce')
        if not np.isfinite(values).all() or values.lt(1).any() or values.mod(1).ne(0).any():
            raise ValueError('Candidate station/reading counts must be positive integers.')
        frame[column] = values.astype(int)
    if frame.reading_count.lt(frame.station_count).any():
        raise ValueError('Candidate has fewer readings than station identities.')
    return frame.sort_values(['district_id', 'date']).reset_index(drop=True)


def read_candidate(directory, *, as_of, registry_ids):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    artifact_version = manifest.get('artifact_version')
    if artifact_version not in {'nwdp-cgwb-manual-v1', 'cgwb-nwdp-missing-month-merge-v1'}:
        raise ValueError('Only reviewed manual processing versions are accepted by this overlay.')
    hashes = manifest.get('output_sha256', {})
    filename = 'canonical_district_month_candidates.csv'
    if filename not in hashes or len(hashes) < 2 or not manifest.get('geojson_sha256'):
        raise ValueError('Candidate needs a hashed station audit, monthly aggregate and boundary provenance.')
    for name, expected in hashes.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or sha256_file(path) != expected:
            raise ValueError('Candidate evidence checksum/path differs from its manifest.')
    if manifest['geojson_sha256'] != sha256_file(ROOT / 'data/raw/india_districts.geojson'):
        raise ValueError('Candidate used a different district boundary generation.')
    if manifest.get('crosswalk_sha256') != sha256_file(ROOT / 'data_ingestion/district_crosswalk.csv'):
        raise ValueError('Candidate used a different canonical district crosswalk.')
    if not manifest.get('sources'):
        raise ValueError('Candidate requires its immutable raw resource chain.')
    for source in manifest['sources']:
        if not source.get('downloaded') or sha256_file(source['path']) != source.get('sha256'):
            raise ValueError('Candidate raw resource differs from its acquisition checksum.')
    csv_options = {'float_precision': 'round_trip'} if artifact_version == 'cgwb-nwdp-missing-month-merge-v1' else {}
    months = validate_months(pd.read_csv(directory / filename, dtype={'district_id': str}, **csv_options),
        as_of=as_of, registry_ids=registry_ids)
    if artifact_version == 'cgwb-nwdp-missing-month-merge-v1':
        parent_path = Path(manifest.get('nwdp_parent_manifest_path', ''))
        if (not parent_path.is_file() or sha256_file(parent_path) != manifest.get('nwdp_parent_manifest_sha256')
                or sha256_file(directory/'nwdp_parent_manifest.json') != manifest.get('nwdp_parent_manifest_sha256')):
            raise ValueError('Combined candidate has an altered/missing parent source manifest.')
        parent_card = json.loads(parent_path.read_text(encoding='utf-8'))
        if parent_card.get('artifact_version') != 'nwdp-cgwb-manual-v1':
            raise ValueError('Combined candidate requires the reviewed original NWDP parent.')
        parent_months, _ = read_candidate(parent_path.parent, as_of=as_of, registry_ids=registry_ids)
        keys = ['district_id','date']
        fields = keys + ['gwl_mean','station_count','reading_count','first_observation_date','last_observation_date','source','metric','units','is_observed']
        inherited = months.set_index(keys).reindex(pd.MultiIndex.from_frame(parent_months[keys])).reset_index()
        try:
            pd.testing.assert_frame_equal(parent_months[fields], inherited[fields], check_dtype=False, check_exact=True)
        except AssertionError as error:
            raise ValueError('Combined candidate must preserve every parent month and value exactly.') from error
        extra = months.merge(parent_months[keys],on=keys,how='left',indicator=True).loc[lambda rows:rows['_merge'].eq('left_only')]
        if (len(extra) != manifest.get('additional_observed_months')
                or not extra.date.eq(pd.Timestamp('2025-01-01')).all()):
            raise ValueError('Combined candidate adds only independently audited January 2025 whole months.')
        extraction = Path(manifest.get('extraction_manifest_path',''))
        if not extraction.is_file() or sha256_file(extraction) != manifest.get('extraction_manifest_sha256'):
            raise ValueError('Combined candidate PDF extraction provenance differs.')
    return months, manifest


def enrich_frame(base, months, *, generation, as_of, registry_ids):
    """Pure transformation; target dates after an origin cannot affect its features."""
    months = validate_months(months, as_of=as_of, registry_ids=registry_ids)
    frame = base.copy().sort_values(['district_id', 'date']).reset_index(drop=True)
    frame['date'] = pd.to_datetime(frame.date)
    if (frame.duplicated(['district_id', 'date']).any() or set(frame.district_id) != set(registry_ids)
            or not frame.date.dt.is_month_start.all()):
        raise ValueError('Baseline requires a unique full canonical monthly grid.')
    timeline = pd.date_range(frame.date.min(), frame.date.max(), freq='MS')
    if any(not pd.DatetimeIndex(group.date).equals(timeline) for _, group in frame.groupby('district_id')):
        raise ValueError('Calendar lags require a complete common monthly grid.')
    if ((months.date < timeline.min()) | (months.date > timeline.max())).any():
        raise ValueError('Candidate dates fall outside the baseline feature grid.')
    observed = observed_mask(frame)
    if (observed & frame.is_imputed.astype('string').str.lower().isin(['true', '1'])).any():
        raise ValueError('Baseline observation and imputation flags conflict.')
    frame['gwl'] = pd.to_numeric(frame.gwl_current, errors='coerce').where(observed)
    if not np.isfinite(frame.loc[observed, 'gwl']).all():
        raise ValueError('Baseline observed depths must be finite.')
    indexed = frame.set_index(['district_id', 'date'])
    incoming = months.set_index(['district_id', 'date'])
    overlap = incoming.index.intersection(indexed.index[observed.to_numpy()])
    added = incoming.loc[~incoming.index.isin(overlap)]
    indexed.loc[added.index, 'gwl'] = added.gwl_mean
    preserved = incoming.loc[overlap].copy()
    preserved['retained_existing_gwl'] = indexed.loc[overlap, 'gwl']
    preserved['candidate_difference_m'] = preserved.gwl_mean - preserved.retained_existing_gwl
    # Reuse the deployed causal rules, including the 3-month carry limit.
    rebuilt = pd.concat([apply_causal_gwl_imputation(group) for _, group in indexed.reset_index().groupby('district_id', sort=True)], ignore_index=True)
    rebuilt = rebuilt.drop(columns=GWL_COLUMNS, errors='ignore')
    rebuilt = build_gwl_features(rebuilt)
    for upper, lower in [('GWL_current', 'gwl_current'), ('GWL_lag_3mo', 'gwl_lag_3mo'), ('GWL_lag_6mo', 'gwl_lag_6mo')]:
        rebuilt[lower] = rebuilt[upper]
    rebuilt['feature_generation'] = generation
    completeness = [c for c in FEATURES_LIST if c != 'crop_season_flag']
    rebuilt['data_readiness_score'] = rebuilt[completeness].notna().mean(axis=1) * 100
    rebuilt = rebuilt[list(base.columns)].sort_values(['district_id', 'date']).reset_index(drop=True)
    rebuilt.attrs = {}
    return rebuilt, added.reset_index(), preserved.reset_index()


def prove_frozen_compatibility(base, candidate, train_cutoff):
    """A new data identity never licenses different pre-training inputs or semantics."""
    columns = sorted(c for c in base if c != 'feature_generation')
    if set(columns) != set(c for c in candidate if c != 'feature_generation'):
        raise ValueError('Feature schema changed; a frozen-artifact compatibility proof is unavailable.')
    a = base.sort_values(['district_id', 'date']).reset_index(drop=True)
    b = candidate.sort_values(['district_id', 'date']).reset_index(drop=True)
    if not a[['district_id', 'date']].equals(b[['district_id', 'date']]):
        raise ValueError('Feature grid changed.')
    train = a.date.le(pd.Timestamp(train_cutoff))
    # dtype changes from CSV parsing are irrelevant; numerical values are not.
    try:
        pd.testing.assert_frame_equal(a.loc[train, columns], b.loc[train, columns], check_dtype=False, check_exact=True)
        static = [c for c in columns if c not in GWL_COLUMNS + ['is_observed', 'is_imputed', 'months_since_observation', 'data_readiness_score']]
        pd.testing.assert_frame_equal(a[static], b[static], check_dtype=False, check_exact=True)
    except AssertionError as error:
        raise ValueError('Frozen model requires identical training inputs and unchanged environmental definitions.') from error
    return {'train_target_cutoff': str(pd.Timestamp(train_cutoff).date()),
        'training_rows_checked': int(train.sum()), 'identical_training_values': True,
        'identical_weather_and_schema': True, 'training_subset_sha256': dataframe_hash(a.loc[train, columns]),
        'policy': 'Same immutable model weights; only post-training missing groundwater months added with unchanged physical-v3 rules.'}


def copy_frozen_bundle(base, candidate, destination, *, checkpoint=None):
    from models import climate_forecast_12m as climate
    checkpoint = Path(checkpoint or climate.ARTIFACT_PATH)
    _, card = climate.load_bundle(checkpoint, expected_generation=base.attrs['feature_generation_id'])
    proof = prove_frozen_compatibility(base, candidate, card['train_target_cutoff'])
    pointer = json.loads(checkpoint.read_text(encoding='utf-8'))
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(checkpoint.parent / pointer['model_path'], destination / 'model.json')
    updated = deepcopy(card)
    updated.pop('card_sha256', None)
    updated.update(feature_generation_id=candidate.attrs['feature_generation_id'],
        data_sha256=candidate.attrs['data_sha256'],
        parent_feature_generation_id=base.attrs['feature_generation_id'],
        parent_card_sha256=pointer['card_sha256'], frozen_compatibility=proof,
        baseline_evaluation=updated.pop('evaluation', None),
        evaluation={'status': 'candidate_requires_paired_evaluation', 'weights_retrained': False})
    _write_json(destination / 'model_card.json', updated)
    if sha256_file(destination / 'model.json') != pointer['model_sha256']:
        raise ValueError('Frozen model copy changed bytes.')
    candidate_pointer = {**pointer, 'model_path': 'model.json', 'card_path': 'model_card.json',
        'card_sha256': sha256_file(destination / 'model_card.json')}
    _write_json(destination / 'checkpoint.json', candidate_pointer)
    climate.load_bundle(destination / 'checkpoint.json', expected_generation=candidate.attrs['feature_generation_id'])
    return proof


def build_snapshot(candidate_directory, output, *, as_of, baseline_directory=None):
    """No database writes, network access, default artifact replacement or retraining."""
    output = Path(output).resolve()
    if not output.is_relative_to((ROOT / 'data/processed/enrichment').resolve()) or output.exists():
        raise ValueError('Output must be a new directory under data/processed/enrichment.')
    registry_ids = [row['district_id'] for row in get_registry()]
    base = load_feature_matrix(baseline_directory)
    months, source = read_candidate(candidate_directory, as_of=as_of, registry_ids=registry_ids)
    if source.get('baseline_features_sha256') != base.attrs['feature_manifest']['feature_csv_sha256']:
        raise ValueError('Candidate was audited against a different baseline feature export.')
    implementation_sha = hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode('utf-8')).hexdigest()
    provenance = {'algorithm': VERSION, 'implementation_sha256': implementation_sha,
        'baseline_feature_sha256': base.attrs['feature_manifest']['feature_csv_sha256'],
        'candidate_manifest_sha256': sha256_file(Path(candidate_directory) / 'manifest.json'), 'as_of': as_of}
    generation = 'physical-v3-official-' + hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()[:16]
    candidate, added, overlaps = enrich_frame(base, months, generation=generation, as_of=as_of, registry_ids=registry_ids)
    manifest = {**base.attrs['feature_manifest'], 'generation_id': generation,
        'enrichment': provenance, 'station_provenance_manifest': source,
        'parent_generation_id': base.attrs['feature_generation_id']}
    validate_feature_generation(candidate, manifest)
    candidate.attrs.update(feature_generation_id=generation, data_sha256=dataframe_hash(candidate), data_source='verified official missing-month overlay')
    # Validate compatibility before writing any output.
    from models.climate_forecast_12m import load_bundle
    proof = prove_frozen_compatibility(base, candidate, load_bundle(expected_generation=base.attrs['feature_generation_id'])[1]['train_target_cutoff'])
    output.mkdir(parents=True, exist_ok=False)
    candidate.to_csv(output / 'features_matrix.csv', index=False, float_format='%.17g', lineterminator='\n')
    manifest['feature_csv_sha256'] = sha256_file(output / 'features_matrix.csv')
    _write_json(output / 'feature_manifest.json', manifest)
    # Bind the card to the actual loadable export. CSV round trips can change
    # nullable integer/float dtypes (and therefore the dataframe fingerprint)
    # even when all physical values are identical.
    persisted = load_feature_matrix(output)
    prove_frozen_compatibility(base, persisted, proof['train_target_cutoff'])
    copy_frozen_bundle(base, persisted, output / 'frozen_bundle')
    added.to_csv(output / 'added_observed_months.csv', index=False)
    overlaps.to_csv(output / 'retained_existing_months.csv', index=False)
    before = base.loc[observed_mask(base)].groupby('district_id').date.agg(['count', 'min', 'max'])
    after = candidate.loc[observed_mask(candidate)].groupby('district_id').date.agg(['count', 'min', 'max'])
    coverage = pd.DataFrame(index=registry_ids).join(before.add_prefix('before_')).join(after.add_prefix('after_'))
    coverage['new_observed_months'] = coverage.after_count.fillna(0) - coverage.before_count.fillna(0)
    coverage.to_csv(output / 'district_coverage.csv', index_label='district_id')
    summary = {'version': VERSION, 'generation_id': generation, 'feature_csv_sha256': manifest['feature_csv_sha256'],
        'before_observed_months': int(observed_mask(base).sum()), 'after_observed_months': int(observed_mask(candidate).sum()),
        'new_observed_months': len(added), 'retained_existing_months': len(overlaps),
        'districts_gaining_observed_months': added.district_id.nunique(),
        'newly_observed_districts': int((coverage.before_count.isna() & coverage.after_count.notna()).sum()),
        'frozen_model_compatibility': proof, 'public_database_changed': False,
        'baseline_files_changed': False, 'weather_features_changed': False}
    _write_json(output / 'build_summary.json', summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--baseline-directory', type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(build_snapshot(args.candidates, args.output, as_of=args.as_of,
        baseline_directory=args.baseline_directory), indent=2))


if __name__ == '__main__':
    main()
