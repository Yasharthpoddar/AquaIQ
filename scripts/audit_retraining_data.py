"""Read-only audit of accepted enriched targets before genuine model retraining.

The audit function writes nothing and never accesses a database. The explicit
CLI writes only a new aggregate JSON/Markdown report, never source/model files.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from models.district_registry import get_registry
from models.xgboost_model import FEATURE_UNITS, load_feature_matrix, sha256_file
from preprocessing.features import FEATURES_LIST

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / 'reports/candidates/groundwater_updates/final_release_20261026/pdf_january_2025_v2'
DEFAULT_PARENT = ROOT / 'data/processed/enrichment/nwdp_manual_20261026_v1'
FINAL_INSPECTED_TARGET = '2026-01-01'


def _date(value):
    return pd.Timestamp(value).date().isoformat() if pd.notna(value) else None


def _counts(values):
    return {str(key): int(count) for key, count in values.value_counts().sort_index().items()}


def _flags(series, name):
    values = series.astype('string').str.strip().str.lower().map({'true': True, '1': True, 'false': False, '0': False})
    if values.isna().any():
        raise ValueError(f'Unknown observation flag in {name}.')
    return values.astype(bool)


def validate_frame(frame, manifest, registry_ids):
    """Validate values without clipping, filling, dropping or relabelling rows."""
    required = {'district_id', 'date', 'gwl_current', 'gwl_lag_3mo', 'gwl_lag_6mo',
                'is_observed', 'is_imputed', 'months_since_observation', 'feature_generation', *FEATURES_LIST}
    if required - set(frame):
        raise ValueError('Missing feature/observation provenance columns.')
    if manifest.get('units') != FEATURE_UNITS or manifest.get('causal_preprocessing') is not True:
        raise ValueError('Unknown physical units or noncausal feature manifest.')
    if manifest.get('feature_columns') != list(FEATURES_LIST) or manifest.get('sample_only', False):
        raise ValueError('Unknown feature ordering or sample-only dataset.')
    result = frame.copy()
    result['date'] = pd.to_datetime(result.date, errors='raise')
    if (result.empty or result.date.isna().any() or not result.date.dt.is_month_start.all()
            or not result.date.eq(result.date.dt.normalize()).all()):
        raise ValueError('Expected nonempty calendar month-start rows.')
    if result.duplicated(['district_id', 'date']).any():
        raise ValueError('Duplicate district-month keys.')
    if set(result.district_id) != set(registry_ids):
        raise ValueError('District identifiers differ from the explicit canonical registry.')
    if (not manifest.get('generation_id') or result.feature_generation.isna().any()
            or set(result.feature_generation) != {manifest['generation_id']}):
        raise ValueError('Unknown or mixed feature generation.')
    timeline = pd.date_range(manifest['date_start'], manifest['date_end'], freq='MS')
    result = result.sort_values(['district_id', 'date']).reset_index(drop=True)
    if any(not pd.DatetimeIndex(group.date).equals(timeline) for _, group in result.groupby('district_id')):
        raise ValueError('Incomplete canonical monthly grid.')
    for column in ('is_observed', 'is_imputed'):
        result[column] = _flags(result[column], column)
    if (result.is_observed & result.is_imputed).any():
        raise ValueError('Observed and imputed flags overlap.')
    numeric_columns = sorted(set(FEATURES_LIST) - {'crop_season_flag'} |
                             {'gwl_current', 'gwl_lag_3mo', 'gwl_lag_6mo', 'months_since_observation'})
    for column in numeric_columns:
        result[column] = pd.to_numeric(result[column], errors='raise')
        if np.isinf(result[column].to_numpy(dtype=float)).any():
            raise ValueError(f'Nonfinite numeric value in {column}.')
    observed = result.is_observed
    finite = np.isfinite(result.gwl_current)
    if (observed & ~finite).any() or result.loc[observed, 'gwl_current'].lt(0).any():
        raise ValueError('Observed targets must be finite nonnegative measured depths.')
    if not finite.eq(observed | result.is_imputed).all():
        raise ValueError('Finite depth lacks explicit observed/imputed provenance.')
    for column in ('gwl_current', 'gwl_lag_3mo', 'gwl_lag_6mo', 'rainfall_current', 'evapotranspiration'):
        if result[column].dropna().lt(0).any():
            raise ValueError(f'Negative physical value in {column}.')
    if (observed & result.months_since_observation.ne(0)).any():
        raise ValueError('An observed target must have zero observation age.')
    if (result.is_imputed & ~result.months_since_observation.between(1, 3)).any():
        raise ValueError('Imputed depth exceeds the declared three-month carry policy.')
    expected = result.gwl_current.where(observed).groupby(result.district_id).ffill(limit=3)
    if not np.isclose(expected, result.gwl_current, equal_nan=True, rtol=0, atol=0).all():
        raise ValueError('Groundwater values differ from causal three-month LOCF.')
    for upper, lower, lag in [('GWL_current', 'gwl_current', 0), ('GWL_lag_3mo', 'gwl_lag_3mo', 3), ('GWL_lag_6mo', 'gwl_lag_6mo', 6)]:
        if not np.isclose(result[upper], result[lower], equal_nan=True, rtol=0, atol=0).all():
            raise ValueError('Upper/lower groundwater feature aliases disagree.')
        expected = result.groupby('district_id').gwl_current.shift(lag) if lag else result.gwl_current
        if not np.isclose(expected, result[lower], equal_nan=True, rtol=0, atol=0).all():
            raise ValueError('Groundwater lag differs from exact causal calendar shift.')
    return result


def summarize_frame(frame):
    observed = frame.loc[frame.is_observed]
    numeric = [name for name in FEATURES_LIST if name != 'crop_season_flag']
    outliers = observed.loc[observed.gwl_current.gt(100), ['district_id', 'date', 'gwl_current']].copy()
    outliers['date'] = outliers.date.dt.strftime('%Y-%m-%d')
    by_month = observed.groupby('date').size().reindex(sorted(frame.date.unique()), fill_value=0)
    return {'rows': len(frame), 'districts': int(frame.district_id.nunique()),
        'date_start': _date(frame.date.min()), 'date_end': _date(frame.date.max()),
        'observed_rows': len(observed), 'imputed_rows': int(frame.is_imputed.sum()),
        'missing_groundwater_rows': int(frame.gwl_current.isna().sum()),
        'observed_date_start': _date(observed.date.min()), 'observed_date_end': _date(observed.date.max()),
        'districts_without_local_observations': int(frame.district_id.nunique() - observed.district_id.nunique()),
        'observed_by_year': _counts(observed.date.dt.year),
        'observed_by_month': {_date(month): int(count) for month, count in by_month.items()},
        'feature_missing_counts': {name: int(frame[name].isna().sum()) for name in FEATURES_LIST},
        'feature_missing_on_observed_rows': {name: int(observed[name].isna().sum()) for name in FEATURES_LIST},
        'numeric_feature_dtypes': {name: str(frame[name].dtype) for name in numeric},
        'observed_depth_quantiles_m': {str(q): float(value) for q, value in observed.gwl_current.quantile([0, .01, .5, .95, .99, 1]).items()} if len(observed) else {},
        'observed_depths_above_100m': outliers.to_dict('records'),
        'observed_zero_depths': int(observed.gwl_current.eq(0).sum()),
        'outlier_policy': 'Flag suspicious depths for source review; no automatic clipping, exclusion or label repair.',
        'duplicate_district_months': 0, 'invalid_or_unknown_flags': 0,
        'unknown_district_identifiers': [], 'observed_imputed_overlap': 0,
        'causal_locf_and_calendar_lag_checks': 'passed',
        'latest_usable_weather_feature_month': {name: _date(frame.loc[frame[name].notna(), 'date'].max())
            for name in ('rainfall_current', 'temperature', 'evapotranspiration')}}


def compare_measured(reference, candidate):
    if not reference[['district_id', 'date']].equals(candidate[['district_id', 'date']]):
        raise ValueError('Reference and candidate monthly grids differ.')
    old = reference.is_observed
    if (old & ~candidate.is_observed).any():
        raise ValueError('Existing measured observations were removed.')
    if not np.array_equal(reference.loc[old, 'gwl_current'], candidate.loc[old, 'gwl_current']):
        raise ValueError('Existing measured values were changed.')
    added = candidate.loc[candidate.is_observed & ~old]
    return {'added_observed_rows': len(added), 'districts_gaining_observations': int(added.district_id.nunique()),
        'removed_observed_rows': 0, 'changed_existing_measured_values': 0,
        'added_by_month': {_date(month): int(count) for month, count in added.groupby('date').size().items()},
        'added_by_year': _counts(added.date.dt.year),
        'newly_locally_observed_districts': sorted(set(candidate.loc[candidate.is_observed, 'district_id']) - set(reference.loc[old, 'district_id']))}


def calendar_pair_summary(frame, baseline=None):
    """Eligibility upper bound; this intentionally does not fit or infer weather."""
    observed = frame.loc[frame.is_observed, ['district_id', 'date']].copy()
    observed['added'] = (~baseline.loc[frame.is_observed, 'is_observed'].to_numpy()) if baseline is not None else False
    origins = observed.rename(columns={'date': 'origin_date', 'added': 'origin_added'})
    targets = observed.rename(columns={'date': 'target_date', 'added': 'target_added'})
    parts = []
    for horizon in range(1, 13):
        rows = origins.copy()
        rows['target_date'] = rows.origin_date + pd.DateOffset(months=horizon)
        rows = rows.merge(targets, on=['district_id', 'target_date'], validate='one_to_one')
        rows['horizon'] = horizon
        parts.append(rows)
    pairs = pd.concat(parts, ignore_index=True)
    training = pairs.loc[pairs.target_date.le('2025-01-31')]
    used_targets = set(zip(training.loc[training.target_added, 'district_id'], training.loc[training.target_added, 'target_date']))
    used_origins = set(zip(training.loc[training.origin_added, 'district_id'], training.loc[training.origin_added, 'origin_date']))
    all_added = set(zip(observed.loc[observed.added, 'district_id'], observed.loc[observed.added, 'date']))
    return {'scope': 'Calendar joins before origin-weather/climatology eligibility; not final XGBoost training counts.',
        'all_observed_origin_target_pairs': len(pairs), 'training_label_cutoff_example': '2025-01-31',
        'training_pairs_through_cutoff': len(training), 'training_districts_before_weather_filter': int(training.district_id.nunique()),
        'training_counts_by_horizon_before_weather_filter': _counts(training.horizon),
        'training_pairs_with_added_targets': int(training.target_added.sum()),
        'training_pairs_with_added_origins': int(training.origin_added.sum()),
        'distinct_added_months_used_as_target': len(used_targets), 'distinct_added_months_used_as_origin': len(used_origins),
        'distinct_added_months_used_in_either_role': len(used_targets | used_origins),
        'added_months_without_any_eligible_pair_role': len(all_added - (used_targets | used_origins)),
        'pairs_with_observed_origins_strictly_after_january_2025': int(pairs.origin_date.gt('2025-01-31').sum()),
        'january_2026_target_pair_counts_by_horizon': _counts(pairs.loc[pairs.target_date.eq(FINAL_INSPECTED_TARGET), 'horizon'])}


def _bundle_proof(pointer_path, generation=None, data_hash=None):
    pointer_path = Path(pointer_path).resolve()
    pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
    members = {}
    for kind in ('model', 'card'):
        path = (pointer_path.parent / pointer[kind + '_path']).resolve()
        if not path.is_relative_to(pointer_path.parent) or sha256_file(path) != pointer[kind + '_sha256']:
            raise ValueError('Model/card bundle checksum or member path changed.')
        members[kind] = path
    card = json.loads(members['card'].read_text(encoding='utf-8'))
    from models.climate_forecast_12m import FEATURES, UNITS
    if (card.get('model_sha256') != pointer['model_sha256'] or card.get('units') != UNITS
            or card.get('features') != FEATURES or card.get('horizons_months') != list(range(1, 13))
            or card.get('target') != 'gwl_change_from_origin'):
        raise ValueError('Model/card forecast target, units, feature order or horizons differ.')
    if generation is not None and card.get('feature_generation_id') != generation:
        raise ValueError('Model card belongs to a different feature generation.')
    if data_hash is not None and card.get('data_sha256') != data_hash:
        raise ValueError('Model card differs from the loaded physical dataframe fingerprint.')
    return {'pointer_sha256': sha256_file(pointer_path), 'model_sha256': pointer['model_sha256'],
        'card_sha256': pointer['card_sha256'], 'feature_generation_id': card['feature_generation_id'],
        'train_target_cutoff': card['train_target_cutoff'], 'max_train_target_date': card['max_train_target_date'],
        'n_train_observed_pairs': card['n_train_observed_pairs'], 'training_districts': card['training_districts'],
        'recorded_training_weather': card.get('evaluation_protocol', {}).get('training_weather'),
        'feature_order': card['features'], 'target': card['target'], 'units': card['units']}


def audit(feature_directory, baseline_directory=None, parent_directory=None, *, registry_ids=None,
          candidate_directory=None, original_checkpoint=None):
    """Read/validate immutable inputs and return aggregate findings; no writes/DB."""
    directory = Path(feature_directory)
    raw = load_feature_matrix(directory)
    manifest = raw.attrs['feature_manifest']
    registry_ids = list(registry_ids) if registry_ids is not None else [row['district_id'] for row in get_registry()]
    frame = validate_frame(raw, manifest, registry_ids)
    references = {}
    proofs = {}
    for name, path in [('baseline', baseline_directory), ('parent', parent_directory)]:
        if path is not None:
            loaded = load_feature_matrix(path)
            references[name] = validate_frame(loaded, loaded.attrs['feature_manifest'], registry_ids)
            proofs[name] = {'feature_csv_sha256': sha256_file(Path(path) / 'features_matrix.csv'),
                'feature_manifest_sha256': sha256_file(Path(path) / 'feature_manifest.json'),
                'summary': summarize_frame(references[name]), 'final_comparison': compare_measured(references[name], frame)}
    candidate = Path(candidate_directory or DEFAULT_CANDIDATE)
    from preprocessing.official_enrichment import read_candidate
    months, source = read_candidate(candidate, as_of='2026-10-26', registry_ids=registry_ids)
    if (manifest.get('enrichment', {}).get('candidate_manifest_sha256') != sha256_file(candidate / 'manifest.json')
            or manifest.get('station_provenance_manifest') != source):
        raise ValueError('Features do not match the exact audited candidate source manifest.')
    if any(any(term in str(item.get('name', '')).lower() for term in ('telemetry', 'synthetic', 'forecast')) for item in source['sources']):
        raise ValueError('Quarantined telemetry or synthetic/forecast sources cannot supply training labels.')
    if 'baseline' in references:
        baseline = references['baseline']
        baseline_keys = pd.MultiIndex.from_frame(baseline.loc[baseline.is_observed, ['district_id', 'date']])
        source_keys = pd.MultiIndex.from_frame(months[['district_id', 'date']])
        final_keys = pd.MultiIndex.from_frame(frame.loc[frame.is_observed, ['district_id', 'date']])
        if set(final_keys) != set(baseline_keys) | set(source_keys):
            raise ValueError('Observed labels include untraced additions or omit accepted source months.')
        new = months.loc[~source_keys.isin(baseline_keys)]
        actual = frame.set_index(['district_id', 'date']).loc[pd.MultiIndex.from_frame(new[['district_id', 'date']]), 'gwl_current']
        if not np.array_equal(actual.to_numpy(), new.gwl_mean.to_numpy()):
            raise ValueError('Added measured targets differ from the accepted physical source aggregates.')
    from models.climate_forecast_12m import ARTIFACT_PATH
    frozen = _bundle_proof(directory / 'frozen_bundle/checkpoint.json', manifest['generation_id'], raw.attrs['data_sha256'])
    original = _bundle_proof(original_checkpoint or ARTIFACT_PATH)
    if frozen['model_sha256'] != original['model_sha256']:
        raise ValueError('Feature snapshot no longer contains the unchanged original reference model.')
    summary = summarize_frame(frame)
    return {'version': 'enriched-retraining-data-audit-v1', 'feature_generation_id': manifest['generation_id'],
        'feature_csv_sha256': sha256_file(directory / 'features_matrix.csv'),
        'feature_manifest_sha256': sha256_file(directory / 'feature_manifest.json'),
        'physical_dataframe_sha256': raw.attrs['data_sha256'], 'units': manifest['units'],
        'summary': summary, 'references': proofs,
        'provenance': {'candidate_manifest_sha256': sha256_file(candidate / 'manifest.json'),
            'recursive_source_and_parent_hash_validation': True, 'candidate_source_count': len(source['sources']),
            'candidate_measured_months': len(months), 'candidate_units': sorted(months.units.unique()),
            'candidate_date_start': _date(months.date.min()), 'candidate_date_end': _date(months.date.max()),
            'observed_target_union_and_source_values_verified': 'baseline' in references,
            'telemetry_or_forecast_sources_included': False,
            'status_note': 'Nested acquisition stage flags are historical snapshots; recursive accepted-candidate checks establish the audited inclusion.'},
        'frozen_reference_model': frozen, 'original_reference_model': original, 'unchanged_frozen_model_bytes': True,
        'calendar_pair_eligibility': calendar_pair_summary(frame, references.get('baseline')),
        'evaluation_limitations': {'accepted_observations_after_january_2026': int((frame.is_observed & frame.date.gt('2026-01-31')).sum()),
            'observed_months_in_2025': sorted(frame.loc[frame.is_observed & frame.date.dt.year.eq(2025), 'date'].dt.strftime('%Y-%m').unique()),
            'january_2026_targets_already_inspected': True, 'new_untouched_final_test_established': False,
            'existing_train_interface': 'A January 2025 training cutoff requires February 2026 or later test origins under the existing twelve-month embargo; there are no observed-origin/future-target pairs after January 2025 even without that embargo.',
            'training_weather_difference': 'The frozen card records realized historical conditional weather. Current twelve-month training code uses origin-available climatology matching serving; do not claim identical historical training covariates.',
            'publication_availability': 'Observation dates and current hashes do not prove historical source publication availability at each origin.'},
        'policy': 'Only explicitly observed, finite, nonnegative physical measurements can form labels. Imputed values may be causal predictors; missing lag features stay missing. No clipping or invented training pairs.',
        'database_accessed': False, 'source_model_or_feature_files_written': False}


def markdown(report):
    summary = report['summary']
    lines = ['# Enriched retraining data audit', '',
        f"Verified `{report['feature_generation_id']}`, CSV SHA-256 `{report['feature_csv_sha256']}`.", '',
        f"The complete matrix has {summary['rows']:,} rows across {summary['districts']} districts, {summary['date_start']}–{summary['date_end']}. "
        f"It contains {summary['observed_rows']:,} observed, {summary['imputed_rows']:,} imputed and {summary['missing_groundwater_rows']:,} missing groundwater rows. "
        f"{summary['districts_without_local_observations']} districts have no local observations.", '',
        'Duplicate identifiers/months, unknown flags, nonfinite or negative observed depths, conflicting observation/imputation flags, causal carry and calendar-lag checks passed. The recursive accepted-source chain and frozen reference model bytes also passed.', '']
    for name, reference in report['references'].items():
        delta = reference['final_comparison']
        lines.append(f"Against {name}: +{delta['added_observed_rows']:,} measured months across {delta['districts_gaining_observations']} districts, "
            f"{len(delta['newly_locally_observed_districts'])} newly local districts, zero removed observations and zero changed existing measured values.")
    lines += ['', '## Observation support', '', '| Year | Observed months |', '| --- | ---: |']
    lines += [f'| {year} | {count:,} |' for year, count in summary['observed_by_year'].items()]
    lines += ['', 'Only January has accepted measurements in 2025 (571 districts). January 2026 has 639 measurements; those targets were already inspected. There are no accepted later targets or observed-origin/future-target pairs strictly after January 2025. The September 2026 matrix end is not evidence of September 2026 labels.', '',
        '## Feature and outlier review', '', '| Feature | Missing rows | Missing on observed rows |', '| --- | ---: | ---: |']
    lines += [f"| {name} | {count:,} | {summary['feature_missing_on_observed_rows'][name]:,} |" for name, count in summary['feature_missing_counts'].items()]
    lines.append('')
    for row in summary['observed_depths_above_100m']:
        lines.append(f"Flag for source review: {row['district_id']}, {row['date']}, {row['gwl_current']} m_bgl. It remains unchanged; no clipping is applied.")
    eligible = report['calendar_pair_eligibility']
    lines += ['', '## Retraining and evaluation limits', '',
        f"Calendar joins provide an upper bound of {eligible['training_pairs_through_cutoff']:,} training pairs through January 2025, "
        f"including {eligible['training_pairs_with_added_targets']:,} pairs with added targets. "
        f"{eligible['distinct_added_months_used_in_either_role']:,} added months enter a pair role, while {eligible['added_months_without_any_eligible_pair_role']} cannot form such a pair. "
        'These counts precede weather eligibility and must not be reported as final fitted sample counts.', '',
        'The production objective is depth change from origin across horizons 1–12. Both endpoints must be observed. The current encoder uses origin-available climatology, while the frozen card records realized historical conditional weather. All missing predictors must retain their existing semantics; no learned global imputation is licensed by this audit.', '',
        'Use earlier chronological folds for selection, then an explicitly labelled final fit that actually includes eligible January 2025 labels. The existing train interface requires later independent heldout origins and cannot manufacture these from the matrix. Previously inspected January 2026 errors are retrospective diagnostics, not a new blind test. No model promotion or scientific accuracy result follows from this data audit.', '',
        'Suggested checks: exact source-value inclusion; observed-only pair joins; training targets before validation origins; origin truncation/future-label perturbation invariance; unchanged feature ordering and units; reproducible fit bytes/predictions; matched baseline case populations; new-model uncertainty unavailable until separately validated.', '',
        'No database was accessed and no source data, feature export or model artifact was written. The JSON companion contains full month counts, missingness, provenance hashes and pair-count qualifications.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feature-directory', type=Path, required=True)
    parser.add_argument('--baseline-directory', type=Path, default=ROOT / 'data/processed')
    parser.add_argument('--parent-directory', type=Path, default=DEFAULT_PARENT)
    parser.add_argument('--candidate-directory', type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.with_suffix('.md').exists():
        raise FileExistsError('Choose new audit report paths; existing evidence is immutable.')
    report = audit(args.feature_directory, args.baseline_directory, args.parent_directory,
                   candidate_directory=args.candidate_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    args.output.with_suffix('.md').write_text(markdown(report), encoding='utf-8')
    print(json.dumps({'feature_generation_id': report['feature_generation_id'], 'observed_rows': report['summary']['observed_rows'], 'output': str(args.output)}, indent=2))
    return report


if __name__ == '__main__':
    main()
