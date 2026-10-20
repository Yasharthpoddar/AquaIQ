"""Frozen, calendar-causal historical evaluation. Never issues a real forecast.

All fitting/outputs are confined to a NEW directory inside this research run.
Publication/acquisition/vintage uncertainty is retained, never filled with dates.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from threadpoolctl import threadpool_limits

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[1]
sys.path.insert(0, str(ROOT))
from models import xgboost_model as direct
from models import six_month_selection as selection

BASELINES = ['persistence', 'seasonal_naive']
NATIVE = [*BASELINES, 'xgb_expanding', 'xgb_active_frozen', 'hgb_locked_historical']
ALL = [*NATIVE, 'linear_expanding']
F = direct.CANONICAL_FEATURE_COLS


def sha(path):
    return direct.sha256_file(path)


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)


def csv(path, frame):
    with Path(path).open('x', encoding='utf-8', newline='') as handle:
        frame.to_csv(handle, index=False)


def make_inventory(frame, protocol):
    frame = direct.encode_crop_season(frame.copy())
    frame['date'] = pd.to_datetime(frame.date)
    if frame.duplicated(['district_id', 'date']).any():
        raise ValueError('Duplicate research district-months')
    primary, secondary = protocol['primary_target_range'], protocol['secondary_target_range']
    frame['target_date'] = frame.date + pd.DateOffset(months=6)
    frame['seasonal_date'] = frame.date - pd.DateOffset(months=6)
    rows = frame.loc[frame.target_date.between(primary[0], secondary[1])].copy()
    for prefix, key in [('target', 'target_date'), ('seasonal', 'seasonal_date')]:
        reference = frame[['district_id', 'date', 'gwl_current', 'is_observed', 'panel_sha256',
                           'well_count', 'first_reported_date', 'last_reported_date']].rename(columns={
            'date': key, 'gwl_current': prefix + '_actual', 'is_observed': prefix + '_observed',
            'panel_sha256': prefix + '_panel_sha256', 'well_count': prefix + '_well_count',
            'first_reported_date': prefix + '_first_reported_date', 'last_reported_date': prefix + '_last_reported_date'})
        rows = rows.merge(reference, on=['district_id', key], how='left', validate='one_to_one')
    rows['case_id'] = 'telangana|' + rows.district_id.astype(str) + '|' + rows.date.dt.strftime('%Y-%m-%d') + '|' + rows.target_date.dt.strftime('%Y-%m-%d')
    rows['period'] = np.where(rows.target_date.between(*primary), 'primary', 'secondary')
    rows['origin_observed'] = direct.observed_mask(rows)
    rows['target_observed'] = direct._parse_bool(rows.target_observed).fillna(False).astype(bool)
    rows['seasonal_observed'] = direct._parse_bool(rows.seasonal_observed).fillna(False).astype(bool)
    rows['reference_eligible'] = (rows.origin_observed & rows.target_observed & rows.seasonal_observed
        & np.isfinite(rows[['gwl_current', 'target_actual', 'seasonal_actual']]).all(axis=1))
    rows['complete_12_features'] = np.isfinite(rows[F]).all(axis=1)
    rows['reference_exclusion_reasons'] = ''
    for flag, reason in [('origin_observed', 'missing_observed_origin'),
                         ('target_observed', 'missing_observed_target'),
                         ('seasonal_observed', 'missing_exact_observed_seasonal')]:
        rows.loc[~rows[flag], 'reference_exclusion_reasons'] += reason + ';'
    assert rows.case_id.is_unique
    assert (rows.target_date == rows.date + pd.DateOffset(months=6)).all()
    return rows


def measure(y, prediction):
    y, prediction = np.asarray(y, dtype=float), np.asarray(prediction, dtype=float)
    result = direct.metrics(y, prediction)
    error, absolute = prediction-y, np.abs(prediction-y)
    result.update(bias_m=float(error.mean()), negative_predictions=int((prediction < 0).sum()),
                  ae_over_5m=int((absolute > 5).sum()), ae_over_10m=int((absolute > 10).sum()))
    result.update({f'ae_p{q}_m': float(np.percentile(absolute, q)) for q in (50, 75, 90, 95, 99)})
    result['ae_max_m'] = float(absolute.max())
    return result


def grouped(table, names, by):
    records = []
    for group, part in table.groupby(by, sort=True):
        for name in names:
            records.append({'group': str(group), 'model': name, **measure(part.actual, part[name])})
    return pd.DataFrame(records)


def uncertainty(table, name, baseline, repeats=2000):
    """Paired district bootstrap and district x circular 6-month block sensitivity."""
    d = sorted(table.district_id.unique())
    months = pd.date_range(table.target_date.min(), table.target_date.max(), freq='MS')
    di, mi = {k:i for i,k in enumerate(d)}, {k:i for i,k in enumerate(months)}
    totals = np.zeros((len(d), len(months), 5))
    for r in table.itertuples():
        a, b = getattr(r, name)-r.actual, getattr(r, baseline)-r.actual
        totals[di[r.district_id], mi[r.target_date]] += [1, abs(a), abs(b), a*a, b*b]
    rng = np.random.default_rng(42)
    distributions = {'district': [], 'district_x_6month_blocks': []}
    for _ in range(repeats):
        district_weights = np.bincount(rng.integers(len(d), size=len(d)), minlength=len(d))
        starts = rng.integers(len(months), size=int(np.ceil(len(months)/6)))
        selected = np.concatenate([(np.arange(6)+s) % len(months) for s in starts])[:len(months)]
        temporal_weights = np.bincount(selected, minlength=len(months))
        for method, weights in [('district', np.ones(len(months))),
                                ('district_x_6month_blocks', temporal_weights)]:
            sums = np.einsum('i,j,ijk->k', district_weights, weights, totals)
            if sums[0]:
                distributions[method].append([(sums[1]-sums[2])/sums[0],
                    np.sqrt(sums[3]/sums[0])-np.sqrt(sums[4]/sums[0])])
    return {'model': name, 'baseline': baseline, 'districts': len(d), 'target_months': len(months),
        'repeats': repeats, 'seed': 42, 'negative_favors_model': True,
        'interval_95_percentile': {method: {'mae_difference_m': np.quantile(values, [.025, .975], axis=0)[:,0].tolist(),
            'rmse_difference_m': np.quantile(values, [.025, .975], axis=0)[:,1].tolist()} for method, values in distributions.items()},
        'limitations': 'Regional dependence, short series, panel changes and unverified historical vintages remain. Descriptive, not confirmatory.'}


def panel_diagnostics(rows, membership):
    panels = {(d, pd.Timestamp(t)): set(part.provider_well_id.astype(str)) for (d,t), part in membership.groupby(['district_id', 'date'])}
    result = []
    for r in rows.itertuples():
        a, b, c = [panels.get((r.district_id, t), set()) for t in (r.date, r.target_date, r.seasonal_date)]
        result.append({'case_id': r.case_id, 'origin_wells': len(a), 'target_wells': len(b), 'seasonal_wells': len(c),
            'origin_target_jaccard': len(a & b)/len(a | b) if a | b else np.nan,
            'all_three_shared_wells': len(a & b & c), 'identical_all_three_panels': a == b == c,
            'identical_origin_target_panels': a == b,
            'weights_fixed_across_origin_target': a == b})
    return pd.DataFrame(result)


def run(normalized, output):
    normalized, output = Path(normalized).resolve(), Path(output).resolve()
    if not normalized.is_relative_to(RUN) or not output.is_relative_to(RUN) or output == RUN or output.exists():
        raise ValueError('Use existing research inputs and an absent output directory within this run')
    protocol = json.loads((RUN/'protocol.json').read_text())
    assert sha(ROOT/'data/processed/features_matrix.csv') == protocol['weather_source']['sha256']
    assert sha(RUN/protocol['source']['file']) == protocol['source']['sha256']
    quality = json.loads((normalized/'quality.json').read_text())
    for name, expected in quality['outputs_sha256'].items():
        assert sha(normalized/name) == expected, f'Normalized input changed: {name}'
    # No fallback DB access is allowed even if a future caller changes a loader.
    direct.get_connection = lambda: (_ for _ in ()).throw(RuntimeError('Database access forbidden'))
    frame = pd.read_csv(normalized/'research_features.csv', parse_dates=['date'])
    membership = pd.read_csv(normalized/'panel_membership.csv', parse_dates=['date'], dtype={'provider_well_id':str})
    cases = direct.create_target(frame)
    cases = cases.loc[cases.target_is_observed].copy()
    inventory = make_inventory(frame, protocol)
    output.mkdir(exist_ok=False)
    artifact_dir = output/'historical_models'
    artifact_dir.mkdir()
    fit_log, model_identity = [], {}
    for name in ALL:
        inventory[name] = np.nan
    inventory.loc[inventory.reference_eligible, 'persistence'] = inventory.loc[inventory.reference_eligible, 'gwl_current']
    inventory.loc[inventory.reference_eligible, 'seasonal_naive'] = inventory.loc[inventory.reference_eligible, 'seasonal_actual']
    computed_at = datetime.now(timezone.utc).isoformat()
    for year in protocol['training']['expanding_years']:
        cutoff = pd.Timestamp(year-2, 12, 31)
        earliest = pd.Timestamp(year-1, 7, 1)
        train = cases.loc[cases.target_date <= cutoff].copy()
        evaluated = inventory.index[inventory.reference_eligible & inventory.target_date.dt.year.eq(year)]
        if not len(evaluated):
            continue
        assert inventory.loc[evaluated, 'date'].min() >= earliest
        assert train.target_date.max() < inventory.loc[evaluated, 'date'].min()
        assert train.target_is_observed.all()
        assert (train.target_date == train.date + pd.DateOffset(months=6)).all()
        model = direct.new_model()
        with threadpool_limits(limits=1):
            model.fit(train[F], train.target_gwl_6mo)
            inventory.loc[evaluated, 'xgb_expanding'] = model.predict(inventory.loc[evaluated, F])
        path = artifact_dir/f'xgb_expanding_{year}.json'
        assert not path.exists()
        model.save_model(path)
        model_identity[f'xgb_expanding_{year}'] = sha(path)
        inventory.loc[inventory.target_date.dt.year.eq(year), 'expanding_train_label_cutoff'] = str(cutoff.date())
        inventory.loc[evaluated, 'xgb_expanding_model_sha256'] = sha(path)
        district_models, district_counts = {}, {}
        complete_train = train.loc[np.isfinite(train[F]).all(axis=1)]
        for district, part in complete_train.groupby('district_id'):
            if len(part) < 12:
                continue
            estimator = LinearRegression()
            with threadpool_limits(limits=1):
                estimator.fit(part[F], part.target_gwl_6mo)
            district_models[district] = estimator
            district_counts[district] = len(part)
            idx = inventory.index[inventory.reference_eligible & inventory.complete_12_features &
                inventory.target_date.dt.year.eq(year) & inventory.district_id.eq(district)]
            if len(idx):
                inventory.loc[idx, 'linear_expanding'] = estimator.predict(inventory.loc[idx, F])
        path = artifact_dir/f'linear_expanding_{year}.joblib'
        assert not path.exists()
        joblib.dump(district_models, path)
        model_identity[f'linear_expanding_{year}'] = sha(path)
        inventory.loc[evaluated, 'linear_bundle_sha256'] = sha(path)
        inventory.loc[evaluated, 'linear_eligible_train_n'] = inventory.loc[evaluated, 'district_id'].map(district_counts).fillna(0)
        record = {'year': year, 'cutoff': str(cutoff.date()), 'first_permitted_origin': str(earliest.date()),
            'train_n': len(train), 'train_districts': int(train.district_id.nunique()),
            'train_origin_min': str(train.date.min().date()), 'train_origin_max': str(train.date.max().date()),
            'max_train_target': str(train.target_date.max().date()), 'evaluation_origin_min': str(inventory.loc[evaluated, 'date'].min().date()),
            'evaluation_n': len(evaluated), 'ols_districts': len(district_models), 'ols_complete_train_counts': district_counts,
            'xgb_parameters': {k: 'NaN (native missing value)' if isinstance(v, float) and np.isnan(v) else v
                               for k,v in model.get_params().items()}, 'xgb_sha256': model_identity[f'xgb_expanding_{year}'],
            'preprocessing': 'No learned scaling or imputation; XGB native missing values, OLS complete training cases only.'}
        fit_log.append(record)
        print(json.dumps({'fit_year': year, 'train_n': len(train), 'evaluation_n': len(evaluated)}), flush=True)

    # Frozen production XGB is read, never fitted or written.
    from xgboost import XGBRegressor
    pointer_path = ROOT/'models/checkpoints/aquaiq_xgb.json'
    pointer = json.loads(pointer_path.read_text())
    path = pointer_path.parent/pointer['model_path']
    assert sha(path) == pointer['model_sha256']
    frozen = XGBRegressor()
    frozen.load_model(path)
    eligible = inventory.index[inventory.reference_eligible]
    inventory.loc[eligible, 'xgb_active_frozen'] = frozen.predict(inventory.loc[eligible, F])
    inventory['xgb_active_frozen_model_sha256'] = sha(path)
    model_identity['xgb_active_frozen'] = sha(path)
    # Exact locked HGB reconstruction solely to test NEW historical source rows.
    legacy = direct.load_feature_matrix()
    legacy_cases = selection.build_cases(legacy, origin_policy='observed')
    training = legacy_cases.loc[legacy_cases.target_date <= '2018-12-31'].copy()
    assert len(training) == 14817, 'Locked historical training membership changed; stop rather than replace candidate'
    lock = json.loads((ROOT/'reports/candidates/six_month_selection_20261017/experiment_v2/selection_lock.json').read_text())
    assert lock['selected_ml'] == protocol['frozen_transfer_comparators']['hgb_locked_reconstructed']['specification']
    assert protocol['frozen_transfer_comparators']['hgb_locked_reconstructed']['train_target_cutoff'] == '2018-12-31'
    estimator = selection.fit_candidate(training, lock['selected_ml'])
    inventory.loc[eligible, 'hgb_locked_historical'] = selection.predict_candidate(estimator, inventory.loc[eligible], lock['selected_ml'])
    path = artifact_dir/'hgb_locked_2018_HISTORICAL_ONLY.joblib'
    assert not path.exists()
    joblib.dump(estimator, path)
    model_identity['hgb_locked_historical'] = sha(path)
    inventory['hgb_locked_historical_model_sha256'] = sha(path)
    fit_log.append({'model': 'hgb_locked_historical', 'train_n': len(training), 'max_train_target': str(training.target_date.max().date()),
        'train_target_cutoff': '2018-12-31', 'training_case_ids_sha256': hashlib.sha256('\n'.join(training.case_id.sort_values()).encode()).hexdigest(),
        'settings': lock['selected_ml'], 'shadow_artifact_approved': False, 'real_shadow_abstention': 'shadow_artifact_not_approved'})
    write_json(artifact_dir/'HISTORICAL_ONLY.json', {'computed_at_utc': computed_at, 'model_sha256': model_identity,
        'protocol_sha256': sha(RUN/'protocol.json'), 'allowed_use': 'Historical research reproduction only; NOT a shadow or production artifact.',
        'shadow_artifact_approved': False, 'fit_log': fit_log})

    inventory['actual'] = inventory.target_actual
    inventory['horizon_months'] = 6
    inventory['computed_at_utc'] = computed_at
    inventory['forecast_issued_at'] = None
    inventory['evaluation_evidence_class'] = 'retrospective_calendar_causal_current_vintage'
    inventory['issuance_availability_verified'] = False
    inventory['source_sha256'] = protocol['source']['sha256']
    inventory['weather_sha256'] = protocol['weather_source']['sha256']
    inventory['configuration_sha256'] = sha(ROOT/'config.yaml')
    inventory['protocol_sha256'] = sha(RUN/'protocol.json')
    inventory['input_sha256'] = [hashlib.sha256(json.dumps({k: None if pd.isna(r[k]) else float(r[k]) for k in selection.FEATURES}, sort_keys=True).encode()).hexdigest() for _,r in inventory.iterrows()]
    inventory['linear_abstention_reason'] = np.where(np.isfinite(inventory.linear_expanding), '',
        np.where(~inventory.reference_eligible, 'ineligible_observed_references',
        np.where(~inventory.complete_12_features, 'missing_model_inputs', 'fewer_than_12_complete_district_training_pairs')))
    inventory['primary_common'] = inventory.period.eq('primary') & inventory.reference_eligible & np.isfinite(inventory[ALL]).all(axis=1)
    inventory['primary_native'] = inventory.period.eq('primary') & inventory.reference_eligible & np.isfinite(inventory[NATIVE]).all(axis=1)
    inventory['secondary_native'] = inventory.period.eq('secondary') & inventory.reference_eligible & np.isfinite(inventory[NATIVE]).all(axis=1)
    panels = panel_diagnostics(inventory, membership)
    inventory = inventory.merge(panels, on='case_id', validate='one_to_one')
    csv(output/'case_inventory.csv', inventory)
    csv(output/'historical_predictions_vs_observations.csv', inventory.loc[inventory.reference_eligible])
    csv(output/'input_features.csv', inventory[['case_id', 'district_id', 'date', *selection.FEATURES, 'input_sha256']])
    csv(output/'panel_diagnostics.csv', panels)
    metrics, intervals = {}, []
    for cohort, names in [('primary_common', ALL), ('primary_native', NATIVE), ('secondary_native', NATIVE)]:
        table = inventory.loc[inventory[cohort]].copy()
        if table.empty:
            metrics[cohort] = {'n': 0, 'status': 'no_eligible_cases'}
            continue
        assert np.isfinite(table[['actual', *names]]).all().all()
        summary = selection.summarize_cases(table, names)
        summary['models'] = {name: measure(table.actual, table[name]) for name in names}
        summary['target_months'] = int(table.target_date.nunique())
        summary['wells_origin_or_target'] = int(membership.merge(pd.concat([table[['district_id','date']], table[['district_id','target_date']].rename(columns={'target_date':'date'})]).drop_duplicates(), on=['district_id','date']).provider_well_id.nunique())
        metrics[cohort] = summary
        for dimension in ['district_id', 'target_year', 'calendar_month', 'target_period']:
            table['target_year'] = table.target_date.dt.year
            table['calendar_month'] = table.target_date.dt.month
            table['target_period'] = table.target_date.dt.strftime('%Y-%m')
            csv(output/f'{cohort}_{dimension}_metrics.csv', grouped(table, names, dimension))
        deletions = []
        for district in sorted(table.district_id.unique()):
            retained = table.loc[table.district_id.ne(district)]
            if len(retained):
                for name in names:
                    deletions.append({'omitted_district':district, 'model':name, **measure(retained.actual,retained[name])})
        csv(output/f'{cohort}_leave_one_district_out.csv', pd.DataFrame(deletions))
        largest = []
        for name in names:
            part = table[['case_id','district_id','date','target_date','actual',name]].copy()
            part['model'] = name
            part['prediction'] = part.pop(name)
            part['absolute_error_m'] = (part.prediction-part.actual).abs()
            largest.append(part.nlargest(20,'absolute_error_m'))
        csv(output/f'{cohort}_large_errors.csv',pd.concat(largest,ignore_index=True))
        if cohort == 'primary_common':
            for name in names:
                if name not in BASELINES:
                    for baseline in BASELINES:
                        intervals.append(uncertainty(table,name,baseline))
    write_json(output/'metrics.json', metrics)
    write_json(output/'paired_uncertainty.json', intervals)
    reasons = inventory.reference_exclusion_reasons.str.split(';').explode()
    leakage = {'calendar_target_exact': bool((inventory.target_date == inventory.date+pd.DateOffset(months=6)).all()),
        'seasonal_date_exact_target_minus_12': bool((inventory.seasonal_date == inventory.target_date-pd.DateOffset(months=12)).all()),
        'eligible_targets_observed': bool(inventory.loc[inventory.reference_eligible,'target_observed'].all()),
        'eligible_origins_observed': bool(inventory.loc[inventory.reference_eligible,'origin_observed'].all()),
        'eligible_seasonal_observed': bool(inventory.loc[inventory.reference_eligible,'seasonal_observed'].all()),
        'six_month_training_embargo_assertions_passed': True, 'fit_log':fit_log,
        'learned_preprocessing':'No fitted normalization/imputation; XGB/HGB native missing, OLS complete training features.',
        'model_selection_or_tuning':False,'historical_source_vintage_verified':False,'actual_issuance_availability_verified':False,
        'actual_acquisition_dates_verified':False,'prospective_predictions_or_outcomes':0,
        'current_export_only':'All historical rows were downloaded in2026; no prior publication/receipt/revision archive established.',
        'production_hgb_abstention_preserved':True,'registered_district_month_cases':len(inventory),
        'reference_eligible':int(inventory.reference_eligible.sum()),
        'reference_exclusions':{str(k):int(v) for k,v in reasons[reasons.ne('')].value_counts().items()},
        'linear_abstentions':inventory.linear_abstention_reason.value_counts().to_dict(),
        'source_panel_limitation':'Monthly observed panels vary; no certified well replacements/datum histories or registered stable-panel generalization.'}
    write_json(output/'leakage_and_eligibility.json', leakage)
    print(json.dumps({key:{'n':v['n'],'districts':v.get('districts'),'models':v.get('models')} for key,v in metrics.items()},indent=2),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--normalized', type=Path, required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    run(args.normalized,args.output_dir)
