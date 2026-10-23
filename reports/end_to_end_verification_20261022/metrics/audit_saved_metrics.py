"""Audit archived rows/metadata only; no estimator, app, database or pipeline imports.

All writes are exclusive and restricted to this new metrics directory.  Repeating
the audit deliberately refuses to replace completed evidence.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
H12 = ROOT / 'reports/candidates/twelve_month_horizon_20261020'
APP = ROOT / 'reports/candidates/twelve_month_horizon_finalization_20261020'
H6 = ROOT / 'reports/actual_forecast_validation_20261019'
OLD6 = ROOT / 'reports/candidates/six_month_selection_20261017/experiment_v2'
INPUTS = {}
CHECKS = []
F = ['gwl_current', 'gwl_lag_3mo', 'gwl_lag_6mo', 'rainfall_current',
     'rainfall_3mo_avg', 'monsoon_deficit_pct', 'temperature', 'evapotranspiration',
     'water_balance_proxy', 'season_Kharif', 'season_Rabi', 'season_Zaid']
MODELS = ['persistence', 'xgb_expanding', 'linear_expanding', 'hgb_12month_fixed']


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def register(path):
    path = Path(path)
    INPUTS[path.relative_to(ROOT).as_posix()] = digest(path)
    return path


def read_json(path):
    return json.loads(register(path).read_text(encoding='utf-8'))


def read_csv(path):
    table = pd.read_csv(register(path))
    for key in ['date', 'target_date', 'seasonal_date']:
        if key in table:
            table[key] = pd.to_datetime(table[key])
    return table


def put(name, data):
    with (OUT / name).open('x', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2, allow_nan=False)
        handle.write('\n')


def csv(name, table):
    with (OUT / name).open('x', encoding='utf-8', newline='') as handle:
        table.to_csv(handle, index=False)


def check(name, condition, detail=None):
    CHECKS.append({'check': name, 'pass': bool(condition), 'detail': detail})


def flag(values):
    return values.astype('string').str.lower().isin(['true', '1'])


def close(a, b):
    return bool(np.allclose(a, b, rtol=0, atol=1e-10, equal_nan=True))


def measure(y, pred):
    y, pred = np.asarray(y, float), np.asarray(pred, float)
    assert len(y) and np.isfinite(y).all() and np.isfinite(pred).all()
    error = pred - y
    absolute = abs(error)
    denominator = float(np.square(y - y.mean()).sum())
    threshold = len(y) * (np.finfo(float).eps * max(1, abs(y).max())) ** 2
    return dict(n=len(y), mae_m=float(absolute.mean()),
                rmse_m=float(np.sqrt(np.square(error).mean())), bias_m=float(error.mean()),
                r2=float(1 - np.square(error).sum() / denominator) if denominator > threshold else None,
                **{f'ae_p{q}_m': float(np.percentile(absolute, q)) for q in [50, 75, 90, 95, 99]},
                ae_max_m=float(absolute.max()), ae_over_5m=int((absolute > 5).sum()),
                ae_over_10m=int((absolute > 10).sum()), negative_predictions=int((pred < 0).sum()))


def summary(table, names):
    result = dict(n=len(table), districts=int(table.district_id.nunique()),
                  origin_start=str(table.date.min().date()), origin_end=str(table.date.max().date()),
                  target_start=str(table.target_date.min().date()), target_end=str(table.target_date.max().date()),
                  target_months=int(table.target_date.nunique()),
                  models={name: measure(table.actual, table[name]) for name in names})
    for label, key in [('district_macro', table.district_id), ('calendar_month_macro', table.target_date.dt.month)]:
        result[label] = {}
        for name in names:
            scores = [measure(part.actual, part[name]) for _, part in table.groupby(key)]
            result[label][name] = {m: float(np.mean([item[m] for item in scores])) for m in ['mae_m', 'rmse_m', 'bias_m']}
    return result


def group_scores(table, names, label):
    results = []
    for dimension, key in [('district', table.district_id), ('calendar_month', table.target_date.dt.month),
                           ('target_year', table.target_date.dt.year), ('target_period', table.target_date.dt.strftime('%Y-%m'))]:
        for group, part in table.groupby(key):
            for name in names:
                results.append(dict(cohort=label, dimension=dimension, group=str(group), model=name,
                                    **measure(part.actual, part[name])))
    return results


def resample(table, model, baseline='persistence', block_months=12, repeats=2000):
    """Independent reconstruction of saved seed42 paired district/time procedure.

    Draw D districts with replacement, then ceil(T/block) circular block starts;
    truncate the concatenated months to T.  All models retain exactly the same
    resampled paired rows.  District-only draws consume the same time draws as
    the saved algorithm, preserving its RNG sequence.
    """
    districts = sorted(table.district_id.unique())
    months = pd.date_range(table.target_date.min(), table.target_date.max(), freq='MS')
    matrix = np.zeros((len(districts), len(months), 7), dtype=float)
    for i, district in enumerate(districts):
        for row in table.loc[table.district_id.eq(district)].itertuples():
            j = months.get_loc(row.target_date)
            e, b = getattr(row, model) - row.actual, getattr(row, baseline) - row.actual
            matrix[i, j] += [1, abs(e), e * e, e, abs(b), b * b, b]
    rng = np.random.default_rng(42)
    samples = {'district': [], f'district_x_{block_months}month_blocks': []}
    for _ in range(repeats):
        draw_d = rng.integers(0, len(districts), size=len(districts))
        starts = rng.integers(0, len(months), size=int(np.ceil(len(months) / block_months)))
        draw_t = np.concatenate([(np.arange(block_months) + start) % len(months) for start in starts])[:len(months)]
        dw = np.bincount(draw_d, minlength=len(districts))
        tw = np.bincount(draw_t, minlength=len(months))
        for name, weights in [('district', np.ones(len(months))), (f'district_x_{block_months}month_blocks', tw)]:
            totals = np.einsum('i,j,ijk->k', dw, weights, matrix)
            n, ae, se, bias, bae, bse, bbias = totals
            if n:
                samples[name].append([ae/n, np.sqrt(se/n), bias/n, (ae-bae)/n,
                                      np.sqrt(se/n)-np.sqrt(bse/n), (bias-bbias)/n])
    keys = ['model_mae_m', 'model_rmse_m', 'model_bias_m', 'mae_difference_m', 'rmse_difference_m', 'bias_difference_m']
    return dict(model=model, baseline=baseline, districts=len(districts), target_months=len(months),
                resamples=repeats, seed=42, block_months=block_months,
                interval_95_percentile={method: {key: np.quantile(values, [.025, .975], axis=0)[:, i].tolist()
                                                 for i, key in enumerate(keys)} for method, values in samples.items()})


def compare_metrics(actual, expected, label):
    for model, values in actual['models'].items():
        for key, value in values.items():
            if key in expected['models'][model]:
                saved = expected['models'][model][key]
                ok = value is None and saved is None or value is not None and saved is not None and close(value, saved)
                check(f'{label}:{model}:{key}:saved_arithmetic', ok)


def compare_intervals(actual, expected, label):
    for method, intervals in actual['interval_95_percentile'].items():
        for key, limits in intervals.items():
            check(f'{label}:{actual["model"]}:{method}:{key}:saved_interval',
                  close(limits, expected['interval_95_percentile'][method][key]))


def observed_feature_join(table, features, label, horizon):
    keys = features.set_index(['district_id', 'date'])
    origin = keys.reindex(pd.MultiIndex.from_arrays([table.district_id, table.date]))
    target = keys.reindex(pd.MultiIndex.from_arrays([table.district_id, table.target_date]))
    check(label + ':unique_case_ids', table.case_id.is_unique)
    check(label + ':exact_calendar_horizon', table.target_date.eq(table.date + pd.DateOffset(months=horizon)).all())
    check(label + ':source_origin_explicitly_observed_not_imputed', (flag(origin.is_observed) & ~flag(origin.is_imputed)).all())
    check(label + ':source_target_explicitly_observed_not_imputed', (flag(target.is_observed) & ~flag(target.is_imputed)).all())
    check(label + ':source_target_values_equal', close(target.gwl_current.to_numpy(), table.actual.to_numpy()))
    check(label + ':source_origin_baseline_values_equal', close(origin.gwl_current.to_numpy(), table.persistence.to_numpy()))
    return origin, target


def main():
    started = datetime.now(timezone.utc).isoformat()
    protocol = read_json(H12 / 'protocol.json')
    protocol_hash = digest(H12 / 'protocol.json')
    lock = read_json(H12 / 'cohorts/lock.json')
    check('h12:protocol_frozen_hash', protocol_hash == lock['protocol_sha256'])
    for path, expected in protocol['inputs_sha256'].items():
        check('protocol_input_hash:' + path, digest(register(ROOT / path)) == expected)
    for path, expected in lock['implementation_sha256'].items():
        check('locked_implementation_hash:' + path, digest(register(ROOT / path)) == expected)
    for path, expected in lock['files'].items():
        check('locked_cohort_hash:' + path, digest(register(H12 / 'cohorts' / path)) == expected)

    full = read_csv(H12 / 'evaluation/full_coordinate_predictions.csv')
    strict = read_csv(H12 / 'evaluation/exact_name_coordinate_predictions.csv')
    features = read_csv(H6 / 'normalized_v2/research_features.csv')
    strict_features = read_csv(H12 / 'cohorts/strict_features.csv')
    saved_metrics = read_json(H12 / 'evaluation/metrics.json')
    saved_uncertainty = read_json(H12 / 'evaluation/uncertainty.json')
    summaries, groups, intervals = {}, [], []
    tables = {}
    for dataset, table, source in [('full_coordinate', full, features), ('exact_name_coordinate', strict, strict_features)]:
        frozen = read_csv(H12 / 'cohorts' / (dataset + '_inventory.csv'))
        check(dataset + ':frozen_case_order', table.case_id.tolist() == frozen.case_id.tolist())
        check(dataset + ':frozen_common_membership', table.common_eligible.tolist() == frozen.common_eligible.tolist())
        eligible = table.loc[flag(table.common_eligible)].copy()
        observed_feature_join(eligible, source, dataset, 12)
        check(dataset + ':all_four_models_finite_on_identical_cases', np.isfinite(eligible[['actual', *MODELS]]).all().all())
        check(dataset + ':annual_baseline_exactly_origin', close(eligible.persistence, eligible.annual_seasonal_naive)
              and close(eligible.persistence, eligible.gwl_current) and eligible.seasonal_date.eq(eligible.date).all())
        check(dataset + ':no_issuance_timestamp', eligible.forecast_issued_at.isna().all())
        check(dataset + ':availability_unverified', (~flag(eligible.issuance_availability_verified)).all())
        check(dataset + ':saved_protocol_identity', eligible.protocol_sha256.eq(protocol_hash).all())
        for period in ['primary', 'secondary']:
            label = dataset + '_' + period
            part = eligible.loc[eligible.period.eq(period)].copy()
            tables[label] = part
            summaries[label] = summary(part, MODELS)
            compare_metrics(summaries[label], saved_metrics[label], label)
            groups.extend(group_scores(part, MODELS, label))
            for model in MODELS:
                computed = resample(part, model)
                computed['cohort'] = label
                intervals.append(computed)
                saved = next(item for item in saved_uncertainty if item['cohort'] == label and item['model'] == model)
                compare_intervals(computed, saved, label)
        stable = eligible.loc[eligible.period.eq('primary') & flag(eligible.identical_origin_target_panel)]
        label = dataset + '_primary_identical_panel'
        if len(stable):
            summaries[label] = summary(stable, MODELS)
            tables[label] = stable
            groups.extend(group_scores(stable, MODELS, label))
    primary = tables['full_coordinate_primary']
    check('primary_792_and_33', len(primary) == 792 and primary.district_id.nunique() == 33)
    check('primary_balanced_24_per_district', primary.groupby('district_id').size().eq(24).all())
    check('primary_balanced_66_per_calendar_month', primary.groupby(primary.target_date.dt.month).size().eq(66).all())
    quality = read_csv(H12 / 'target_panel_quality.csv')
    check('target_quality_same_primary_cases', set(quality.case_id) == set(primary.case_id))
    summaries['primary_panel_quality'] = dict(n=len(quality), panels_with_conflict=int(quality.conflict.gt(0).sum()),
        mean_conflict_share=float(quality.conflict_share.mean()), mean_unknown_share=float(quality.unknown_share.mean()),
        panels_with_reading_over_well_depth=int(quality.over_depth.gt(0).sum()))

    # Cards are parsed and files hashed; no native estimator deserialization occurs.
    cards = []
    for card_path in sorted((H12 / 'evaluation/models').rglob('*_card.json')):
        card = read_json(card_path)
        model_path = card_path.parent / card['model_path']
        check('card_model_hash:' + card_path.name + ':' + card_path.parent.name,
              digest(register(model_path)) == card['model_sha256'])
        check('card_schema:' + str(card_path.relative_to(H12)), card['feature_schema_sha256'] == hashlib.sha256(
            json.dumps(card['features'], sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest())
        check('card_contract:' + str(card_path.relative_to(H12)), card['horizon_months'] == card['embargo_months'] == 12
              and card['units'] == 'm_bgl' and card['protocol_sha256'] == protocol_hash and not card['shadow_artifact_approved'])
        year = int(card_path.stem.split('_')[-2])
        cohort = full if card_path.parent.name == 'full_coordinate' else strict
        cases = cohort.loc[flag(cohort.common_eligible) & cohort.target_date.dt.year.eq(year)]
        first_origin = cases.date.min()
        cutoff = pd.Timestamp(card['train_target_cutoff'])
        check('card_cutoff:' + str(card_path.relative_to(H12)), pd.Timestamp(card['max_train_target_date']) <= cutoff
              and cutoff == first_origin - pd.DateOffset(months=12) - pd.Timedelta(days=1))
        check('row_model_hash:' + str(card_path.relative_to(H12)), cases[card['model_name'] + '_model_sha256'].eq(card['model_sha256']).all())
        source = features if card_path.parent.name == 'full_coordinate' else strict_features
        lookup = source.set_index(['district_id', 'date'])
        target_date = source.date + pd.DateOffset(months=12)
        target = lookup.reindex(pd.MultiIndex.from_arrays([source.district_id, target_date]))
        valid_origin = flag(source.is_observed) & ~flag(source.is_imputed)
        imputed_origin = ~flag(source.is_observed) & flag(source.is_imputed) & source.months_since_observation.between(1, 3)
        eligible_train = (valid_origin | imputed_origin).to_numpy() & flag(target.is_observed).to_numpy() & ~flag(target.is_imputed).to_numpy()
        eligible_train &= np.isfinite(target.gwl_current).to_numpy() & target_date.le(cutoff).to_numpy()
        if card['family'] == 'linear_regression':
            eligible_train &= np.isfinite(source[card['features']]).all(axis=1).to_numpy()
        train = source.loc[eligible_train].copy()
        ids = train.district_id.astype(str) + '|' + train.date.dt.strftime('%Y-%m-%d') + '|' + (train.date + pd.DateOffset(months=12)).dt.strftime('%Y-%m-%d') + '|12'
        # Per-district OLS may omit unsupported districts; compare the saved total
        # and hash only where its card documents exactly this complete membership.
        ids_hash = hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest()
        check('training_membership_count:' + str(card_path.relative_to(H12)), len(train) == card['train_n'], {'recomputed': len(train), 'card': card['train_n']})
        check('training_membership_hash:' + str(card_path.relative_to(H12)), ids_hash == card['training_case_ids_sha256'])
        cards.append(dict(card=card_path.relative_to(ROOT).as_posix(), family=card['family'], train_n=card['train_n'],
                          cutoff=card['train_target_cutoff'], earliest_eval_origin=str(first_origin.date()),
                          max_train_target=card['max_train_target_date'], model_sha256=card['model_sha256']))

    # Fixed application artifact: separate immutable 24-case check.
    descriptor = read_json(ROOT / 'research/twelve_month_app.json')
    manifest_path = ROOT / descriptor['manifest_path']
    manifest = read_json(manifest_path)
    contract = descriptor['contract']
    canonical_hash = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    check('app:canonical_contract_hash', canonical_hash == descriptor['contract_sha256'] == manifest['contract_sha256'])
    check('app:manifest_hash', digest(manifest_path) == descriptor['manifest_sha256'])
    for role in ['card', 'snapshot', 'input_provenance', 'provenance']:
        check('app:' + role + ':manifest_hash', digest(register(manifest_path.parent / manifest[role + '_path'])) == manifest[role + '_sha256'])
    app_card = read_json(manifest_path.parent / manifest['card_path'])
    check('app:model_hash', digest(register(manifest_path.parent / app_card['model_path'])) == app_card['model_sha256'])
    check('app:card_contract', app_card['features'] == F and app_card['horizon_months'] == app_card['embargo_months'] == 12
          and app_card['train_target_cutoff'] == '2021-12-31' and app_card['first_allowed_origin'] == '2023-01'
          and app_card['protocol_sha256'] == protocol_hash and app_card['configuration_sha256'] == canonical_hash)
    check('app:ordered_feature_schema', app_card['feature_schema_sha256'] == hashlib.sha256(json.dumps(F, separators=(',', ':')).encode()).hexdigest())
    checks = read_csv(APP / 'artifact/historical_checks.csv').rename(columns={'target_value': 'actual', 'annual_baseline': 'persistence'})
    snapshot = read_csv(APP / 'artifact/features.csv')
    observed_feature_join(checks, snapshot, 'app24', 12)
    check('app24:fixed_model_identity', checks.model_sha256.eq(app_card['model_sha256']).all())
    check('app24:no_issuance', checks.forecast_issued_at.isna().all())
    summaries['fixed_application_24'] = summary(checks, ['persistence', 'fixed_xgb_2021'])
    build = read_json(APP / 'artifact_build.json')
    for model, saved_key in [('persistence', 'annual_baseline'), ('fixed_xgb_2021', 'fixed_xgb')]:
        for key, saved in build['own_historical_24_case_check'][saved_key].items():
            key = {'MAE_m': 'mae_m', 'RMSE_m': 'rmse_m', 'R2': 'r2'}.get(key, key)
            check('app24:build_metrics:' + model + ':' + key, close(summaries['fixed_application_24']['models'][model][key], saved))
    example = checks.loc[checks.date.eq(pd.Timestamp('2024-01-01'))].iloc[0]
    summaries['fixed_example'] = {k: str(example[k].date()) if k in ['date', 'target_date'] else float(example[k])
                                 for k in ['date', 'target_date', 'actual', 'persistence', 'fixed_xgb_2021']}
    observed_snapshot = snapshot.loc[flag(snapshot.is_observed) & ~flag(snapshot.is_imputed)]
    latest = observed_snapshot.loc[observed_snapshot.date.idxmax()]
    summaries['latest_fixed_snapshot'] = dict(date=str(latest.date.date()), target=str((latest.date + pd.DateOffset(months=12)).date()),
        origin_m=float(latest.gwl_current), observed_months=len(observed_snapshot), missing_features=[name for name in F if not np.isfinite(latest[name])],
        actual_acquisition_nonmissing=int(snapshot.actual_acquisition_at.notna().sum()), available_at_nonmissing=int(snapshot.available_at.notna().sum()))
    provenance = read_json(APP / 'artifact/input_provenance.json')
    future_sources = []
    def traverse(item, origin, key):
        if isinstance(item, dict):
            for name in ['source_month', 'required_month']:
                value = item.get(name)
                if value and pd.Timestamp(value) > origin:
                    future_sources.append([key, name, value])
            for value in item.values():
                traverse(value, origin, key)
        elif isinstance(item, list):
            for value in item:
                traverse(value, origin, key)
    for row in provenance['rows']:
        traverse(row['inputs'], pd.Timestamp(row['date']), row['date'])
    check('app:provenance_contains_no_future_source_month', not future_sources, future_sources)

    # Original six-month selection test, distinct geography/cohort.
    old = read_csv(OLD6 / 'primary_observed_origin_predictions.csv')
    old_names = ['persistence', 'seasonal_naive', 'ridge', 'random_forest', 'xgboost', 'hist_gradient_boosting']
    summaries['six_month_original_209'] = summary(old, old_names)
    compare_metrics(summaries['six_month_original_209'], read_json(OLD6 / 'test_results.json')['cohorts']['primary_observed_origin'], 'six_month_original_209')
    check('old6:exact_calendar_horizon', old.target_date.eq(old.date + pd.DateOffset(months=6)).all())
    check('old6:unique_paired_cases', old.case_id.is_unique and flag(old.origin_observed).all() and np.isfinite(old[['actual', *old_names]]).all().all())
    groups.extend(group_scores(old, old_names, 'six_month_original_209'))

    # Retained Telangana six-month evidence and independently joined comparisons.
    six = read_csv(H6 / 'evaluation_v2/historical_predictions_vs_observations.csv')
    six_primary = six.loc[flag(six.primary_common)].copy()
    six_names = ['persistence', 'seasonal_naive', 'xgb_expanding', 'xgb_active_frozen', 'hgb_locked_historical', 'linear_expanding']
    summaries['six_month_telangana_594'] = summary(six_primary, six_names)
    observed_feature_join(six_primary, features, 'telangana6', 6)
    groups.extend(group_scores(six_primary, six_names, 'six_month_telangana_594'))
    matches = {}
    for kind, key in [('target', 'target_date'), ('origin', 'date')]:
        right_cols = ['district_id', 'date', 'target_date', 'actual', 'persistence', 'seasonal_naive', 'xgb_expanding', 'linear_expanding']
        matched = primary.merge(six_primary[right_cols], on=['district_id', key], suffixes=('_12', '_6'), validate='one_to_one')
        archived = read_csv(H12 / 'evaluation' / ('six_vs_twelve_same_' + kind + '.csv'))
        check('six_vs_twelve:' + kind + ':saved_join_keys', set(zip(matched.district_id, matched[key])) == set(zip(archived.district_id, archived[key])))
        info = dict(n=len(matched), same_outcomes=kind == 'target', controlled_horizon_effect=False,
                    shared_date_start=str(matched[key].min().date()), shared_date_end=str(matched[key].max().date()))
        for h in [6, 12]:
            info[str(h)] = {model: measure(matched['actual_' + str(h)], matched[model + '_' + str(h)])
                           for model in ['persistence', 'xgb_expanding', 'linear_expanding']}
        info['six_month_seasonal_naive'] = measure(matched.actual_6, matched.seasonal_naive_6)
        if kind == 'target':
            check('six_vs_twelve:matched_targets_equal', close(matched.actual_12, matched.actual_6))
            check('six_vs_twelve:h12_persistence_equals_h6_seasonal', close(matched.persistence_12, matched.seasonal_naive_6))
            saved_intervals = read_json(H12 / 'evaluation/six_vs_twelve_uncertainty.json')
            for model in ['persistence', 'xgb_expanding', 'linear_expanding']:
                part = matched[['district_id', 'target_date', 'actual_12', model + '_12', model + '_6']].rename(columns={'actual_12': 'actual'})
                computed = resample(part, model + '_12', model + '_6')
                computed['cohort'] = 'six_vs_twelve_same_target'
                intervals.append(computed)
                compare_intervals(computed, next(item for item in saved_intervals if item['model'] == model + '_12'), 'six_vs_twelve')
        matches[kind] = info
    summaries['six_vs_twelve'] = matches

    grouped = pd.DataFrame(groups)
    highlights = {}
    for dim in ['district', 'calendar_month']:
        subset = grouped.loc[grouped.cohort.eq('full_coordinate_primary') & grouped.dimension.eq(dim)]
        pivot = subset.pivot(index='group', columns='model', values='rmse_m')
        highlights[dim] = {model: dict(lower_rmse_than_baseline=int((pivot[model] < pivot.persistence).sum()),
                                       groups=int(len(pivot)), losing_groups=pivot.index[pivot[model] >= pivot.persistence].tolist())
                           for model in MODELS[1:]}
    summaries['primary_group_highlights'] = highlights
    failed = [item for item in CHECKS if not item['pass']]
    put('metrics.json', summaries)
    put('bootstrap.json', intervals)
    csv('group_metrics.csv', grouped)
    put('artifact_checks.json', {'cards_without_deserialization': cards, 'checks': CHECKS, 'failures': failed})
    put('input_hashes.json', INPUTS)
    after = {path: digest(ROOT / path) for path in INPUTS}
    put('preservation.json', {'input_files': len(INPUTS), 'all_unchanged': after == INPUTS,
                              'changed': [path for path in INPUTS if after[path] != INPUTS[path]]})
    result = dict(started_at_utc=started, completed_at_utc=datetime.now(timezone.utc).isoformat(),
                  check_count=len(CHECKS), failed_count=len(failed), failures=failed,
                  input_files=len(INPUTS), no_estimator_loading=True, no_fitting=True,
                  no_prediction_calls=True, no_database=True, no_downloads=True,
                  preservation_pass=after == INPUTS)
    put('run.json', result)
    print(json.dumps(result, indent=2))
    return 0 if not failed and after == INPUTS else 1


if __name__ == '__main__':
    sys.exit(main())
