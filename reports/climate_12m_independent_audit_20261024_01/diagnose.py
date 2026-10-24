"""Summarize frozen historical reconstruction; no fitting or issuance."""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def dump(name, value):
    path = OUT / name
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False, default=str)
        stream.write('\n')

if __name__ == '__main__':
    if any((OUT/name).exists() for name in ['district_diagnostics.csv','feature_distribution_diagnostics.csv','diagnostics.json','matched_table.md']):
        raise FileExistsError('Use a new uniquely named audit directory to preserve completed results.')
    table = pd.read_csv(OUT / 'reconstructed_historical_cases.csv', parse_dates=['origin_date','target_date','seasonal_reference_date'])
    frame = pd.read_csv(ROOT / 'data/processed/features_matrix.csv', parse_dates=['date'])
    pre = pd.read_csv(ROOT / 'data/processed/preprocessed_wide.csv', parse_dates=['date'])
    unique = pd.concat([table[['district_id','origin_date','origin_gwl']].rename(columns={'origin_date':'date','origin_gwl':'value'}),
                        table[['district_id','target_date','actual']].rename(columns={'target_date':'date','actual':'value'})]).drop_duplicates(['district_id','date'])
    joined = unique.merge(pre, on=['district_id','date'], validate='one_to_one')
    assert np.allclose(joined.value, joined.gwl)
    assert joined.is_observed.astype('string').str.lower().isin(['true','1']).all()
    # Calendar lag equivalence against the preserved preprocessed export.
    for lag in [3,6]:
        lagged = pre[['district_id','date','gwl']].copy()
        lagged['date'] += pd.DateOffset(months=lag)
        matched = frame.merge(lagged, on=['district_id','date'], how='left', validate='one_to_one')
        assert np.allclose(matched[f'gwl_lag_{lag}mo'], matched.gwl, equal_nan=True)
    paired = table.dropna(subset=['seasonal']).copy()
    reference_lag = (paired.target_date.dt.year-paired.seasonal_reference_date.dt.year)*12 + paired.target_date.dt.month-paired.seasonal_reference_date.dt.month
    errors = {}
    for method in ['predicted','persistence','seasonal']:
        part = table.dropna(subset=[method])
        absolute = part[method].sub(part.actual).abs()
        errors[method] = {'n':len(part), 'exact':int(absolute.eq(0).sum()), 'within_1cm':int(absolute.le(.01).sum()),
                          'over_1m':int(absolute.gt(1).sum()), 'over_2m':int(absolute.gt(2).sum()),
                          'over_5m':int(absolute.gt(5).sum()), 'max_absolute_m':float(absolute.max()),
                          'absolute_error_quantiles_m':{str(q):float(absolute.quantile(q)) for q in [0,.25,.5,.75,.9,.95,.99,1]}}
    districts = []
    for district, part in table.groupby('district_id'):
        districts.append({'district_id':district,'n':len(part),'unique_targets':part.target_date.nunique(),
            'target_depths_m':sorted(part.actual.unique().tolist()), 'origin_depths_m':sorted(part.origin_gwl.unique().tolist()),
            'persistence_exact':int(part.persistence.eq(part.actual).sum()),
            'xgb_mae_m':float(part.predicted.sub(part.actual).abs().mean()),
            'persistence_mae_m':float(part.persistence.sub(part.actual).abs().mean()),
            'xgb_bias_m':float(part.predicted.sub(part.actual).mean())})
    pd.DataFrame(districts).to_csv(OUT / 'district_diagnostics.csv', index=False)
    # Feature drift is descriptive, not a different evaluation or a retuning step.
    from models.climate_forecast_12m import prepare_pairs, FEATURES
    pairs = prepare_pairs(frame)
    train = pairs.loc[pairs.target_date.le('2019-12-31')]
    actual_future = pairs.loc[pairs.origin_date.ge('2021-01-01')]
    assumed = pd.read_csv(OUT / 'reconstructed_historical_inputs.csv', parse_dates=['origin_date','target_date'])
    match = assumed.merge(actual_future, on=['district_id','origin_date','target_date'], suffixes=('_assumed','_realized'), validate='one_to_one')
    shift=[]
    for feature in FEATURES:
        a=match[feature+'_assumed']; r=match[feature+'_realized']; t=train[feature]
        shift.append({'feature':feature,'training_mean':float(t.mean()),'training_sd':float(t.std()),
                      'training_min':float(t.min()),'training_max':float(t.max()),
                      'heldout_assumed_mean':float(a.mean()),'heldout_assumed_sd':float(a.std()),
                      'heldout_realized_mean':float(r.mean()),'heldout_realized_sd':float(r.std()),
                      'assumed_vs_realized_mean_absolute_difference':float((a-r).abs().mean()),
                      'assumed_outside_training_range':int(((a<t.min())|(a>t.max())).sum())})
    pd.DataFrame(shift).to_csv(OUT / 'feature_distribution_diagnostics.csv',index=False)
    # Squared-error decomposition explains why pooled R2 can be high across deep/shallow districts.
    mean_by_district=table.groupby('district_id').actual.transform('mean')
    total=float(((table.actual-table.actual.mean())**2).sum())
    within=float(((table.actual-mean_by_district)**2).sum())
    macro={}
    for method in ['predicted','persistence','seasonal']:
        part=paired.copy()
        part['ae']=part[method].sub(part.actual).abs()
        part['se']=(part[method]-part.actual)**2
        macro[method]={'district_macro_mae_m':float(part.groupby('district_id').ae.mean().mean()),
                       'sqrt_district_macro_mse_m':float(np.sqrt(part.groupby('district_id').se.mean().mean()))}
    verification=json.loads((OUT/'verification.json').read_text())
    dump('diagnostics.json',{'all_eligible_feature_labels_match_preprocessed':True,'exact_calendar_lags_match_preprocessed':True,
         'unique_origin_and_target_district_months':len(unique),'train_pairs':len(train),'train_districts':train.district_id.nunique(),
         'max_metric_abs_discrepancy':max(abs(d[k]) for d in verification['summary_differences'] for k in ['mae_m','rmse_m','r2']),
         'all_reported_sample_counts_match':all(d['n_matches'] for d in verification['summary_differences']),
         'errors':errors,'seasonal_reference_lag_months':{str(k):int(v) for k,v in reference_lag.value_counts().sort_index().items()},
         'between_district_fraction_of_target_sum_squares':1-within/total,
         'matched_district_macro':macro,'districts':districts,
         'test_targets_per_year':{str(k):int(v) for k,v in table.groupby(table.target_date.dt.year).size().items()}})
    print(json.dumps(json.loads((OUT/'diagnostics.json').read_text()),indent=2),flush=True)
    metrics=pd.read_csv(OUT/'matched_metrics.csv')
    lines=['| Horizon | Matched N | XGB MAE / RMSE (m) | Persistence MAE / RMSE (m) | Seasonal reference MAE / RMSE (m) |',
           '|---|---:|---:|---:|---:|']
    for h in [0]+list(range(1,13)):
        part=metrics.loc[metrics.cohort.eq('all_three_matched') & metrics.horizon.eq(h)].set_index('method')
        cells=['All' if h==0 else f'M+{h}',str(int(part.loc['predicted','n']))]
        cells += [f'{part.loc[m,"mae_m"]:.3f} / {part.loc[m,"rmse_m"]:.3f}' for m in ['predicted','persistence','seasonal']]
        lines.append('| '+' | '.join(cells)+' |')
    (OUT/'matched_table.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
