"""Create-only, offline same-provider-well baseline research; never issuance.

Reads the corrected normalized_v2 acquisition only. This diagnostic avoids
changing district means, but does not certify physical well or datum continuity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

RUN = Path(__file__).resolve().parent
SOURCE = RUN / 'acquired/telangana_monthly_2007_2026.csv'
NORMALIZED = RUN / 'normalized_v2/normalized_well_observations.csv'
EXCLUDED = RUN / 'normalized_v2/excluded_source_records.csv'
OUTPUT = RUN / 'well_baselines'
KEYS = ['agency', 'provider_well_id']
IDENTITY = ['latitude', 'longitude', 'well_depth_m', 'aquifer', 'well_type']
COHORTS = {
    'primary_2024_01_to_2025_06': ('2024-01-01', '2025-06-01'),
    'secondary_2025_07_to_2026_05': ('2025-07-01', '2026-05-01'),
}
STRATA = ['all_stable_identity', 'exact_name_spatial_agreement_all3']


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)


def write_csv(path, frame):
    with path.open('x', encoding='utf-8', newline='') as handle:
        frame.to_csv(handle, index=False)


def metric_values(truth, prediction):
    truth, prediction = np.asarray(truth, float), np.asarray(prediction, float)
    error = prediction - truth
    absolute = np.abs(error)
    denominator = float(np.square(truth - truth.mean()).sum()) if len(truth) else 0
    result = {'n': len(truth), 'mae_m': float(absolute.mean()),
              'rmse_m': float(np.sqrt(np.square(error).mean())),
              'bias_m': float(error.mean()),
              'r2': float(1 - np.square(error).sum() / denominator)
                    if len(truth) >= 2 and denominator > 0 else None,
              'max_absolute_error_m': float(absolute.max())}
    result.update({f'absolute_error_p{p}_m': float(np.percentile(absolute, p))
                   for p in [50, 75, 90, 95, 99]})
    return result


def raw_quality(raw, normalized, excluded):
    dates = pd.to_datetime(raw['Date'], format='%d-%m-%Y', errors='coerce')
    values = pd.to_numeric(raw['Water Level in mbgl'], errors='coerce')
    depth = pd.to_numeric(raw['Well Depth, m'], errors='coerce')
    meta_fields = [c for c in raw if c not in ['Well ID', 'Date', 'Water Level in mbgl']]
    changing = {c: int(raw.groupby('Well ID')[c].nunique(dropna=False).gt(1).sum())
                for c in meta_fields}
    ordered = raw[['Well ID']].assign(date=dates, value=values).sort_values(['Well ID', 'date'])
    prior_date = ordered.groupby('Well ID').date.shift()
    prior_value = ordered.groupby('Well ID').value.shift()
    adjacent = (ordered.date.dt.to_period('M').astype('int64')
                - prior_date.dt.to_period('M').astype('int64')).eq(1)
    equal = ordered.value.notna() & ordered.value.eq(prior_value) & adjacent
    run_number = (~equal).cumsum()
    runs = ordered.groupby(['Well ID', run_number]).agg(
        n=('value', 'size'), value=('value', 'first'), start=('date', 'min'), end=('date', 'max'))
    longest = runs.nlargest(10, 'n').reset_index(level=0).reset_index(drop=True)
    longest['start'] = longest.start.dt.strftime('%Y-%m-%d')
    longest['end'] = longest.end.dt.strftime('%Y-%m-%d')
    unique_meta = raw[['Well ID', 'Latitude', 'Longitude', 'Well Depth, m']].drop_duplicates()
    colocated = unique_meta.groupby(['Latitude', 'Longitude'])['Well ID'].nunique()
    named = normalized.source_name_district_id.notna()
    agreement = named & normalized.source_name_district_id.eq(normalized.district_id)
    result = {
        'scope': 'Independent descriptive source QC; no accuracy-driven exclusions.',
        'raw_rows': len(raw), 'raw_provider_well_ids': int(raw['Well ID'].nunique()),
        'raw_source_district_strings': int(raw['District Name (as per LGD)'].nunique()),
        'case_normalized_district_names': int(raw['District Name (as per LGD)'].str.upper().nunique()),
        'reported_date_min': str(dates.min().date()), 'reported_date_max': str(dates.max().date()),
        'invalid_reported_dates': int(dates.isna().sum()),
        'reported_day_of_month_counts': {str(k): int(v) for k, v in dates.dt.day.value_counts().items()},
        'nonnumeric_depth_rows': int(values.isna().sum()),
        'nonnumeric_tokens': raw.loc[values.isna(), 'Water Level in mbgl'].value_counts(dropna=False).to_dict(),
        'negative_depth_rows': int(values.lt(0).sum()), 'zero_depth_rows': int(values.eq(0).sum()),
        'depth_range_m_bgl': [float(values.min()), float(values.max())],
        'depth_greater_than_reported_well_depth_rows': int((values > depth).sum()),
        'well_ids_with_depth_greater_than_reported_well_depth': int(raw.loc[values > depth, 'Well ID'].nunique()),
        'duplicate_well_reported_date_rows': int(raw.duplicated(['Well ID', 'Date'], keep=False).sum()),
        'exact_duplicate_rows': int(raw.duplicated().sum()),
        'well_ids_with_metadata_variation_by_field': changing,
        'coordinate_pairs_with_multiple_well_ids': int(colocated.gt(1).sum()),
        'ids_in_shared_coordinate_pairs': int(colocated[colocated.gt(1)].sum()),
        'equal_adjacent_monthly_numeric_readings': int(equal.sum()),
        'adjacent_well_month_reading_pairs': int(adjacent.sum()),
        'longest_repeated_reading_runs': longest.to_dict('records'),
        'repeat_interpretation': 'Repeated values alone do not prove imputation or fresh acquisition.',
        'accepted_normalized_rows': len(normalized), 'excluded_source_rows': len(excluded),
        'accepted_rows_with_resolvable_source_name': int(named.sum()),
        'accepted_rows_exact_name_spatial_agreement': int(agreement.sum()),
        'accepted_rows_resolvable_name_spatial_disagreement': int((named & ~agreement).sum()),
        'accepted_rows_unknown_source_name_mapping': int((~named).sum()),
        'geography_caveat': 'Coordinates substantially disagree with named districts. Geographic breakdowns are conditional on the retained fixed-polygon mapping.',
        'well_continuity_caveat': 'Provider IDs and matching metadata are not certified physical continuity or replacement/datum records.',
        'date_caveat': 'Provider-reported date or month label; actual acquisition and first availability unknown.',
    }
    return result


def prepare_cases(frame):
    if frame.duplicated(KEYS + ['date']).any():
        raise ValueError('Normalized observations must be unique provider-well/month')
    if not frame.gwl_m_bgl.notna().all() or not np.isfinite(frame.gwl_m_bgl).all():
        raise ValueError('Normalized target rows must be finite observations')
    selected = ['date', 'gwl_m_bgl', 'reported_observation_date', 'district_id',
                'source_name_district_id', *IDENTITY]
    pieces = []
    for cohort, (start, end) in COHORTS.items():
        target = frame.loc[frame.date.between(start, end), KEYS + selected].copy()
        target = target.rename(columns={c: 'target_' + c for c in selected})
        target['origin_date'] = target.target_date - pd.DateOffset(months=6)
        target['seasonal_date'] = target.target_date - pd.DateOffset(months=12)
        for role in ['origin', 'seasonal']:
            reference = frame[KEYS + selected].copy()
            reference = reference.rename(columns={c: role + '_' + c for c in selected})
            target = target.merge(reference, on=KEYS + [role + '_date'], how='left', validate='one_to_one')
        target['cohort'] = cohort
        target['eligibility_reason'] = ''
        def add(mask, reason):
            target.loc[mask, 'eligibility_reason'] = target.loc[mask, 'eligibility_reason'].map(
                lambda text: text + (';' if text else '') + reason)
        add(target.origin_gwl_m_bgl.isna(), 'missing_accepted_observed_origin')
        add(target.seasonal_gwl_m_bgl.isna(), 'missing_accepted_observed_exact_seasonal')
        for field in IDENTITY:
            known = pd.Series(True, index=target.index)
            for role in ['target', 'origin', 'seasonal']:
                value = target[f'{role}_{field}']
                known &= value.notna() & value.astype('string').str.strip().ne('').fillna(False)
            add(~known & target.origin_gwl_m_bgl.notna() & target.seasonal_gwl_m_bgl.notna(),
                'missing_identity_' + field)
            same = target[f'target_{field}'].eq(target[f'origin_{field}']) & target[f'target_{field}'].eq(target[f'seasonal_{field}'])
            add(known & ~same, 'identity_mismatch_' + field)
        target['eligible_stable_identity'] = target.eligibility_reason.eq('')
        geo = pd.Series(True, index=target.index)
        for role in ['target', 'origin', 'seasonal']:
            geo &= (target[f'{role}_source_name_district_id'].notna()
                    & target[f'{role}_source_name_district_id'].eq(target[f'{role}_district_id']))
        target['exact_name_spatial_agreement_all3'] = target.eligible_stable_identity & geo
        target['district_id'] = target.target_district_id
        target['target_calendar_month'] = target.target_date.dt.month
        target['target_period'] = target.target_date.dt.strftime('%Y-%m')
        target['target_year'] = target.target_date.dt.year
        pieces.append(target)
    return pd.concat(pieces, ignore_index=True)


def create_outputs(frame, cases):
    predictions, metrics, panels, complete_panels, large_errors, summaries = [], [], [], [], [], []
    for cohort, (start, end) in COHORTS.items():
        all_cases = cases[cases.cohort.eq(cohort)]
        for stratum in STRATA:
            eligible = all_cases.loc[all_cases.eligible_stable_identity].copy()
            if stratum == 'exact_name_spatial_agreement_all3':
                eligible = eligible.loc[eligible.exact_name_spatial_agreement_all3].copy()
            eligible['stratum'] = stratum
            eligible['persistence_prediction_m_bgl'] = eligible.origin_gwl_m_bgl
            eligible['seasonal_naive_prediction_m_bgl'] = eligible.seasonal_gwl_m_bgl
            for model, column in [('persistence', 'persistence_prediction_m_bgl'),
                                  ('seasonal_naive', 'seasonal_naive_prediction_m_bgl')]:
                eligible[model + '_error_m'] = eligible[column] - eligible.target_gwl_m_bgl
                eligible[model + '_absolute_error_m'] = eligible[model + '_error_m'].abs()
            predictions.append(eligible)
            summary = {'cohort': cohort, 'stratum': stratum, 'n': len(eligible),
                       'provider_well_ids': int(eligible[KEYS].drop_duplicates().shape[0]),
                       'conditional_districts': int(eligible.district_id.nunique()),
                       'candidate_accepted_target_rows': len(all_cases),
                       'target_start': str(eligible.target_date.min().date()) if len(eligible) else None,
                       'target_end': str(eligible.target_date.max().date()) if len(eligible) else None}
            summaries.append(summary)
            if not len(eligible):
                continue
            groups = [('pooled', 'all', eligible)]
            for kind, column in [('district', 'district_id'), ('period', 'target_period'),
                                 ('calendar_month', 'target_calendar_month'), ('year', 'target_year')]:
                groups.extend((kind, str(key), group) for key, group in eligible.groupby(column))
            for kind, key, group in groups:
                for model, column in [('persistence', 'persistence_prediction_m_bgl'),
                                      ('seasonal_naive', 'seasonal_naive_prediction_m_bgl')]:
                    metrics.append({'cohort': cohort, 'stratum': stratum, 'group_type': kind,
                                    'group': key, 'model': model,
                                    'provider_well_ids': int(group[KEYS].drop_duplicates().shape[0]),
                                    **metric_values(group.target_gwl_m_bgl, group[column])})
            for model in ['persistence', 'seasonal_naive']:
                top = eligible.nlargest(20, model + '_absolute_error_m').copy()
                top['ranking_method'] = model
                large_errors.append(top)
            for (district, month), target_rows in all_cases.groupby(['district_id', 'target_date']):
                accepted_sets = []
                for role, delta in [('target', 0), ('origin', 6), ('seasonal', 12)]:
                    date = month - pd.DateOffset(months=delta)
                    f = frame.loc[frame.district_id.eq(district) & frame.date.eq(date)]
                    accepted_sets.append(set(map(tuple, f[KEYS].to_numpy())))
                e = eligible.loc[eligible.district_id.eq(district) & eligible.target_date.eq(month)]
                panels.append({'cohort': cohort, 'stratum': stratum, 'district_id': district,
                               'target_date': month, 'target_wells': len(accepted_sets[0]),
                               'origin_wells': len(accepted_sets[1]), 'seasonal_wells': len(accepted_sets[2]),
                               'common_three_month_provider_ids': len(set.intersection(*accepted_sets)),
                               'eligible_stable_chain_wells': len(e),
                               'eligible_share_of_accepted_target_wells': len(e) / len(target_rows)})
            months = list(pd.date_range(start, end, freq='MS'))
            for district in sorted(all_cases.district_id.unique()):
                e = eligible.loc[eligible.district_id.eq(district)]
                ids = [set(map(tuple, e.loc[e.target_date.eq(month), KEYS].to_numpy())) for month in months]
                common = set.intersection(*ids)
                serialized = [{'agency': agency, 'provider_well_id': well} for agency, well in sorted(common)]
                complete_panels.append({'cohort': cohort, 'stratum': stratum, 'district_id': district,
                                        'registered_target_months': len(months),
                                        'months_with_eligible_cases': int(e.target_date.nunique()),
                                        'distinct_eligible_provider_ids': int(e[KEYS].drop_duplicates().shape[0]),
                                        'common_eligible_ids_every_target_month': len(common),
                                        'common_ids_sha256': canonical_hash(serialized),
                                        'common_ids_json': json.dumps(serialized, sort_keys=True)})
    return {'well_predictions.csv': pd.concat(predictions, ignore_index=True),
            'metrics.csv': pd.DataFrame(metrics), 'monthly_panel_coverage.csv': pd.DataFrame(panels),
            'whole_period_common_panels.csv': pd.DataFrame(complete_panels),
            'large_errors.csv': pd.concat(large_errors, ignore_index=True) if large_errors else pd.DataFrame(),
            'cohort_counts.csv': pd.DataFrame(summaries)}


def main():
    global NORMALIZED, EXCLUDED, OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--normalized-dir', type=Path, default=NORMALIZED.parent)
    parser.add_argument('--output-dir', type=Path, default=OUTPUT)
    args = parser.parse_args()
    normalized_dir = args.normalized_dir.resolve()
    OUTPUT = args.output_dir.resolve()
    if not normalized_dir.is_relative_to(RUN) or not OUTPUT.is_relative_to(RUN) or OUTPUT == RUN:
        raise ValueError('Baseline inputs/outputs must remain within this research run')
    NORMALIZED = normalized_dir / 'normalized_well_observations.csv'
    EXCLUDED = normalized_dir / 'excluded_source_records.csv'
    if not NORMALIZED.is_file() or not EXCLUDED.is_file():
        raise FileNotFoundError('Wait for corrected normalized_v2 outputs; v1 is prohibited')
    if OUTPUT.exists():
        raise FileExistsError('Well-baseline output already exists; never overwrite research evidence')
    quality = json.loads((NORMALIZED.parent / 'quality.json').read_text(encoding='utf-8'))
    if quality.get('code_sha256') == 'fad4695cdcf8c331a21ba1d5aa5158eb70d8f65fb4d754498e5c51e839b1313d':
        raise ValueError('First nullable-depth adapter version is superseded; use corrected normalization')
    if quality['source_sha256'] != sha(SOURCE):
        raise ValueError('Source hash does not match normalized-v2 provenance')
    expected = quality.get('outputs_sha256', {}).get(NORMALIZED.name)
    if expected != sha(NORMALIZED):
        raise ValueError('Normalized-v2 bytes do not match retained quality manifest')
    frame = pd.read_csv(NORMALIZED, dtype={'provider_well_id': str, 'agency': str},
                        parse_dates=['date', 'reported_observation_date'])
    excluded = pd.read_csv(EXCLUDED, dtype={'provider_well_id': str, 'agency': str}, parse_dates=['date'])
    raw = pd.read_csv(SOURCE, encoding='cp1252', dtype=str, keep_default_na=False, encoding_errors='strict')
    protocol = {
        'analysis': 'Calendar-causal same-provider-well persistence and exact-seasonal arithmetic only.',
        'cohorts': COHORTS, 'strata': STRATA,
        'target': 'Source-reported finite accepted mbgl reading in exact origin+6 calendar month; never filled.',
        'keys': KEYS, 'identity_required_equal_all_three_dates': IDENTITY,
        'reference': 'Persistence exact target-6; seasonal naive exact target-12; same agency and provider Well ID.',
        'unknown_identity_policy': 'Exclude unknown or mismatching identity metadata; no fabricated identities.',
        'missing_policy': 'No reference/target imputation or nearest-month substitution.',
        'quality_stratum': 'Exact resolvable named district equals fixed-polygon district at all three dates; quality-defined before errors.',
        'metrics': 'MAE/RMSE/bias/error percentiles in metres; R2 only for n>=2 and nonconstant observed values.',
        'sign': 'Prediction minus observation; positive bias means greater predicted depth below ground.',
        'geography': 'Conditional fixed-polygon labels; substantial source coordinate/name disagreements remain.',
        'continuity': 'Matching provider ID and retained metadata are not certified replacement/measuring-point continuity.',
        'timing': 'Provider-reported date/month labels; actual acquisition/publication/availability unknown. No issuance or prospective evidence.',
        'source_sha256': sha(SOURCE), 'normalized_v2_sha256': sha(NORMALIZED),
        'excluded_source_records_sha256': sha(EXCLUDED), 'code_sha256': sha(Path(__file__)),
    }
    protocol_sha = canonical_hash(protocol)
    cases = prepare_cases(frame)
    outputs = create_outputs(frame, cases)
    outputs['eligibility_all_accepted_targets.csv'] = cases
    reasons = []
    for cohort, (start, end) in COHORTS.items():
        selected = cases.loc[cases.cohort.eq(cohort)]
        for reason, count in selected.loc[selected.eligibility_reason.ne(''), 'eligibility_reason'].str.split(';').explode().value_counts().items():
            reasons.append({'cohort': cohort, 'population': 'accepted_target_chain', 'reason': reason, 'rows': int(count)})
        rejected = excluded.loc[excluded.date.between(start, end)]
        for reason, count in rejected.exclusion_reason.str.split(';').explode().value_counts().items():
            reasons.append({'cohort': cohort, 'population': 'excluded_raw_source_target_rows', 'reason': reason, 'rows': int(count)})
    outputs['exclusion_counts.csv'] = pd.DataFrame(reasons)
    for name, value in outputs.items():
        value['source_sha256'] = protocol['source_sha256']
        value['protocol_sha256'] = protocol_sha
        value['evidence_class'] = 'retrospective_current_vintage_reported_observations_not_issuance_verified'
    notes = raw_quality(raw, frame, excluded)
    notes['source_sha256'] = protocol['source_sha256']
    notes['protocol_sha256'] = protocol_sha
    OUTPUT.mkdir(exist_ok=False)
    write_json(OUTPUT / 'protocol.json', {'protocol': protocol, 'protocol_sha256': protocol_sha})
    for name, value in outputs.items():
        write_csv(OUTPUT / name, value)
    write_json(OUTPUT / 'data_quality_notes.json', notes)
    write_json(OUTPUT / 'integrity.json', {
        'source_sha256': sha(SOURCE), 'normalized_v2_sha256': sha(NORMALIZED),
        'protocol_sha256': protocol_sha,
        'output_sha256': {p.name: sha(p) for p in sorted(OUTPUT.iterdir()) if p.is_file()},
        'no_training_or_model_invocation': True, 'no_forecast_issuance': True,
        'prospective_accuracy_measured': False,
    })
    print(outputs['cohort_counts.csv'].drop(columns=['source_sha256', 'protocol_sha256', 'evidence_class']).to_string(index=False))
    print(outputs['metrics.csv'].loc[outputs['metrics.csv'].group_type.eq('pooled'),
          ['cohort', 'stratum', 'model', 'n', 'mae_m', 'rmse_m', 'bias_m', 'r2']].to_string(index=False))


if __name__ == '__main__':
    main()
