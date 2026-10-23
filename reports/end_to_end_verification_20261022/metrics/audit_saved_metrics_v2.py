"""Supplemental saved-row audit; only new exclusive writes under metrics/.

No project modules, estimator deserialization, prediction calls, fitting, network,
database, or pipelines. Reconstructs bootstrap rows directly, independently of
the archived weighted-sufficient-statistic calculation. Does not replace v1.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import platform
import sys

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
H12 = ROOT / 'reports/candidates/twelve_month_horizon_20261020'
APP = ROOT / 'reports/candidates/twelve_month_horizon_finalization_20261020'
H6 = ROOT / 'reports/actual_forecast_validation_20261019'
OLD6 = ROOT / 'reports/candidates/six_month_selection_20261017/experiment_v2'
INPUTS, CHECKS = {}, []
METHODS = ['persistence', 'xgb_expanding', 'linear_expanding', 'hgb_12month_fixed']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path):
    data = Path(path).read_bytes()
    INPUTS[Path(path).relative_to(ROOT).as_posix()] = sha(data)
    return data


def read_json(path):
    return json.loads(read_bytes(path))


def read_csv(path):
    read_bytes(path)
    table = pd.read_csv(path)
    for key in ['date', 'target_date', 'seasonal_date']:
        if key in table:
            table[key] = pd.to_datetime(table[key])
    return table


def put(name, value):
    with (OUT / name).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def flag(series):
    return series.astype('string').str.lower().isin(['true', '1'])


def check(label, passed, detail=None):
    CHECKS.append(dict(check=label, passed=bool(passed), detail=detail))


def point(actual, predicted):
    y, p = list(map(float, actual)), list(map(float, predicted))
    errors = [b-a for a, b in zip(y, p)]
    n = len(y)
    mean = math.fsum(y) / n
    sse = math.fsum(e*e for e in errors)
    sst = math.fsum((a-mean)**2 for a in y)
    return dict(n=n, mae_m=math.fsum(map(abs, errors))/n,
                rmse_m=math.sqrt(sse/n), bias_m=math.fsum(errors)/n,
                r2=1-sse/sst if sst else None)


def fingerprint(table, names, horizon):
    ordered = table.sort_values(['district_id', 'date', 'target_date']).reset_index(drop=True)
    ids = [f'{r.district_id}|{r.date:%Y-%m-%d}|{r.target_date:%Y-%m-%d}|{horizon}' for r in ordered.itertuples()]
    targets = [f'{key}|{float(value):.17g}' for key, value in zip(ids, ordered.actual)]
    baseline = [f'{key}|{float(value):.17g}' for key, value in zip(ids, ordered.persistence)]
    result = dict(n=len(table), districts=int(table.district_id.nunique()),
                  states=sorted(table.district_id.str.split('-').str[0].unique()),
                  horizon_months=horizon, exact_horizon=bool(table.target_date.eq(table.date+pd.DateOffset(months=horizon)).all()),
                  unique_case_ids=bool(table.case_id.is_unique),
                  canonical_case_ids_match=ordered.case_id.tolist() == ids,
                  case_key_encoding='Sorted district|origin ISO date|target ISO date|horizon; newline joined, UTF-8, no final newline',
                  value_encoding='case key|binary64 value formatted .17g; newline joined, UTF-8, no final newline',
                  case_ids_sorted_sha256=sha('\n'.join(ids).encode()),
                  observed_target_rows_sha256=sha('\n'.join(targets).encode()),
                  persistence_rows_sha256=sha('\n'.join(baseline).encode()),
                  all_methods_finite_identical_rows=bool(np.isfinite(table[['actual', *names]]).all().all()),
                  model_prediction_rows_sha256={})
    for name in names:
        rows = [f'{key}|{float(value):.17g}' for key, value in zip(ids, ordered[name])]
        result['model_prediction_rows_sha256'][name] = sha('\n'.join(rows).encode())
    return result


def direct_bootstrap(table, model, baseline='persistence', repeats=2000):
    """Rebuild each sampled row list. Same stored draw order, new arithmetic."""
    table = table.reset_index(drop=True)
    districts = sorted(table.district_id.unique())
    months = pd.date_range(table.target_date.min(), table.target_date.max(), freq='MS')
    di, mi = {v:i for i,v in enumerate(districts)}, {v:i for i,v in enumerate(months)}
    index = np.full((len(districts), len(months)), -1, dtype=int)
    for i, row in enumerate(table.itertuples()):
        assert index[di[row.district_id], mi[row.target_date]] == -1
        index[di[row.district_id], mi[row.target_date]] = i
    errors = table[model].to_numpy(float)-table.actual.to_numpy(float)
    base_errors = table[baseline].to_numpy(float)-table.actual.to_numpy(float)
    values = {'district': [], 'district_x_12month_blocks': []}
    counts = {key:[] for key in values}
    rng = np.random.default_rng(42)
    for _ in range(repeats):
        draw_d = rng.integers(0, len(districts), size=len(districts))
        starts = rng.integers(0, len(months), size=math.ceil(len(months)/12))
        draw_t = np.concatenate([(np.arange(12)+s) % len(months) for s in starts])[:len(months)]
        for method, month_indices in [('district', np.arange(len(months))), ('district_x_12month_blocks', draw_t)]:
            rows = index[np.ix_(draw_d, month_indices)].ravel()
            rows = rows[rows >= 0]
            if not len(rows):
                continue
            e, b = errors[rows], base_errors[rows]
            a, q, bias = np.abs(e).mean(), np.sqrt(np.square(e).mean()), e.mean()
            ba, bq, bbias = np.abs(b).mean(), np.sqrt(np.square(b).mean()), b.mean()
            values[method].append([a, q, bias, a-ba, q-bq, bias-bbias])
            counts[method].append(len(rows))
    keys = ['model_mae_m', 'model_rmse_m', 'model_bias_m', 'mae_difference_m', 'rmse_difference_m', 'bias_difference_m']
    return dict(model=model, baseline=baseline, resamples=repeats, seed=42, block_months=12,
                districts=len(districts), target_months=len(months),
                nonempty_replicates={k:len(v) for k,v in values.items()},
                sampled_row_count_range={k:[min(v),max(v)] for k,v in counts.items()},
                interval_95_percentile={method:{key:np.quantile(data,[.025,.975],axis=0)[:,i].tolist() for i,key in enumerate(keys)} for method,data in values.items()})


def main():
    started = datetime.now(timezone.utc).isoformat()
    prior = read_json(OUT / 'metrics.json')
    prior_ci = read_json(OUT / 'bootstrap.json')
    lock = read_json(H12 / 'cohorts/lock.json')
    newlines = []
    for name, expected in lock['implementation_sha256'].items():
        data = read_bytes(ROOT/name)
        receipt = dict(path=name, expected_sha256=expected, raw_sha256=sha(data),
                       lf_normalized_sha256=sha(data.replace(b'\r\n',b'\n')),
                       crlf_count=data.count(b'\r\n'), raw_match=sha(data)==expected,
                       lf_normalized_match=sha(data.replace(b'\r\n',b'\n'))==expected)
        newlines.append(receipt)
        check('newline_normalized_implementation:'+name, receipt['lf_normalized_match'])
    full = read_csv(H12/'evaluation/full_coordinate_predictions.csv')
    strict = read_csv(H12/'evaluation/exact_name_coordinate_predictions.csv')
    tables = {}
    for label, table in [('full_coordinate', full), ('exact_name_coordinate', strict)]:
        eligible = table.loc[flag(table.common_eligible)].copy()
        for period in ['primary', 'secondary']:
            tables[label+'_'+period] = (eligible.loc[eligible.period.eq(period)].copy(), METHODS, 12)
        stable = eligible.loc[eligible.period.eq('primary') & flag(eligible.identical_origin_target_panel)].copy()
        if len(stable):
            tables[label+'_primary_identical_panel'] = (stable, METHODS, 12)
    fixed = read_csv(APP/'artifact/historical_checks.csv').rename(columns={'target_value':'actual','annual_baseline':'persistence'})
    tables['fixed_application_24'] = (fixed, ['persistence','fixed_xgb_2021'], 12)
    old = read_csv(OLD6/'primary_observed_origin_predictions.csv')
    old_names = ['persistence','seasonal_naive','ridge','random_forest','xgboost','hist_gradient_boosting']
    tables['six_month_original_209'] = (old, old_names, 6)
    six = read_csv(H6/'evaluation_v2/historical_predictions_vs_observations.csv')
    six = six.loc[flag(six.primary_common)].copy()
    six_names = ['persistence','seasonal_naive','xgb_expanding','xgb_active_frozen','hgb_locked_historical','linear_expanding']
    tables['six_month_telangana_594'] = (six, six_names, 6)
    fingerprints, arithmetic, independent_ci = {}, {}, []
    for cohort, (table,names,horizon) in tables.items():
        fingerprints[cohort] = fingerprint(table,names,horizon)
        for key in ['exact_horizon','unique_case_ids','canonical_case_ids_match','all_methods_finite_identical_rows']:
            check(cohort+':'+key, fingerprints[cohort][key])
        arithmetic[cohort] = {name:point(table.actual,table[name]) for name in names}
        for name, measured in arithmetic[cohort].items():
            for key,value in measured.items():
                expected = prior[cohort]['models'][name][key]
                check(cohort+':fsum:'+name+':'+key, value==expected if value is None else math.isclose(value,expected,rel_tol=0,abs_tol=1e-10))
        # Test all archived 12-month intervals independently; add descriptive
        # intervals for the fixed 24-case artifact and identical-panel subsets.
        if horizon == 12:
            for name in names:
                result = direct_bootstrap(table,name)
                result['cohort'] = cohort
                independent_ci.append(result)
                archived = next((v for v in prior_ci if v['cohort']==cohort and v['model']==name),None)
                if archived:
                    for method,items in result['interval_95_percentile'].items():
                        for key,value in items.items():
                            check(cohort+':direct_rows_ci:'+name+':'+method+':'+key,
                                  np.allclose(value,archived['interval_95_percentile'][method][key],rtol=0,atol=1e-10))
    # Original209 targets/origins/seasonal baselines joined directly to retained
    # nationwide source features. Reading metadata only; no feature generation.
    source = read_csv(ROOT/'data/processed/features_matrix.csv').set_index(['district_id','date'])
    origin = source.reindex(pd.MultiIndex.from_arrays([old.district_id,old.date]))
    target = source.reindex(pd.MultiIndex.from_arrays([old.district_id,old.target_date]))
    seasonal = source.reindex(pd.MultiIndex.from_arrays([old.district_id,old.target_date-pd.DateOffset(months=12)]))
    for label,frame in [('origin',origin),('target',target),('seasonal',seasonal)]:
        check('original209:'+label+':explicitly_observed_not_imputed', (flag(frame.is_observed)&~flag(frame.is_imputed)).all())
    for label,frame,col in [('origin',origin,'persistence'),('target',target,'actual'),('seasonal',seasonal,'seasonal_naive')]:
        check('original209:'+label+':retained_values_equal',np.allclose(frame.gwl_current.to_numpy(),old[col].to_numpy(),rtol=0,atol=1e-10))
    # Reconstruct the fixed artifact's training membership without loading model.
    snapshot = read_csv(APP/'artifact/features.csv')
    card = read_json(APP/'artifact/xgb_fixed_2021_card.json')
    lookup = snapshot.set_index(['district_id','date'])
    dates = snapshot.date+pd.DateOffset(months=12)
    targets = lookup.reindex(pd.MultiIndex.from_arrays([snapshot.district_id,dates]))
    observed = flag(snapshot.is_observed)&~flag(snapshot.is_imputed)
    imputed = ~flag(snapshot.is_observed)&flag(snapshot.is_imputed)&snapshot.months_since_observation.between(1,3)
    mask = (observed|imputed).to_numpy() & flag(targets.is_observed).to_numpy() & ~flag(targets.is_imputed).to_numpy()
    mask &= np.isfinite(targets.gwl_current).to_numpy() & dates.le(pd.Timestamp(card['train_target_cutoff'])).to_numpy()
    training = snapshot.loc[mask].copy()
    training_ids = [f'{r.district_id}|{r.date:%Y-%m-%d}|{r.date+pd.DateOffset(months=12):%Y-%m-%d}|12' for r in training.itertuples()]
    fixed_training = dict(n=len(training), complete_n=int(np.isfinite(training[card['features']]).all(axis=1).sum()),
                          train_target_cutoff=card['train_target_cutoff'], max_target=str(dates[mask].max().date()),
                          first_evaluation_origin=str(fixed.date.min().date()),
                          membership_sha256=sha('\n'.join(sorted(training_ids)).encode()))
    check('fixed24:training_count',fixed_training['n']==card['train_n'])
    check('fixed24:training_complete_count',fixed_training['complete_n']==card['train_complete_n'])
    check('fixed24:training_membership_hash',fixed_training['membership_sha256']==card['training_case_ids_sha256'])
    check('fixed24:strict_cutoff_before_first_origin_minus12m',pd.Timestamp(card['train_target_cutoff'])==fixed.date.min()-pd.DateOffset(months=12)-pd.Timedelta(days=1))
    # Focused adverse cases and cohort composition for interpretation.
    tails = {}
    for cohort,(table,names,_) in tables.items():
        if cohort not in ['full_coordinate_primary','fixed_application_24','six_month_original_209']:
            continue
        tails[cohort] = {}
        for name in names:
            rank = np.argsort(np.abs(table[name].to_numpy()-table.actual.to_numpy()))[::-1][:5]
            tails[cohort][name] = [{**{k:str(row[k].date()) if k in ['date','target_date'] else str(row[k]) for k in ['case_id','district_id','date','target_date']},
                                   'actual':float(row.actual),'prediction':float(row[name]),'absolute_error_m':float(abs(row[name]-row.actual))}
                                  for _,row in table.iloc[rank].iterrows()]
    put('newline_normalization_receipt.json',newlines)
    put('cohort_fingerprints_v2.json',fingerprints)
    put('independent_arithmetic_v2.json',arithmetic)
    put('direct_row_bootstrap_v2.json',independent_ci)
    put('fixed_training_membership_v2.json',fixed_training)
    put('adverse_cases_v2.json',tails)
    put('supplement_checks_v2.json',CHECKS)
    after = {name:sha((ROOT/name).read_bytes()) for name in INPUTS}
    failures = [v for v in CHECKS if not v['passed']]
    receipt = dict(started_at_utc=started,completed_at_utc=datetime.now(timezone.utc).isoformat(),
                   python=sys.version,executable=sys.executable,platform=platform.platform(),numpy=np.__version__,pandas=pd.__version__,
                   script_sha256=sha(Path(__file__).read_bytes()),inputs_sha256=INPUTS,input_preservation_pass=after==INPUTS,
                   changed_inputs=[name for name in INPUTS if INPUTS[name]!=after[name]],
                   check_count=len(CHECKS),failed_count=len(failures),failures=failures,
                   resampling='Direct sampled row indexing; exact stored sorted districts/month axis, RNG default_rng42, district draw then circular12-month starts, 2000 replicates; district-only still consumes time draws',
                   no_project_imports=True,no_estimator_loading=True,no_fitting=True,no_prediction_calls=True,no_database=True,no_downloads=True)
    put('supplement_run_v2.json',receipt)
    print(json.dumps({k:receipt[k] for k in ['started_at_utc','completed_at_utc','check_count','failed_count','failures','input_preservation_pass']},indent=2))
    return 0 if not failures and after==INPUTS else 1


if __name__ == '__main__':
    sys.exit(main())
