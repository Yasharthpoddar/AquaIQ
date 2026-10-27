"""Pure, candidate-only tools for the prespecified historical accuracy study.

No serving dispatch, database writes, fitted global preprocessing, or target
imputation. Dates here are calendar month starts; origin information is available
through that month's end, as in the existing enriched pair builder.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from models.climate_forecast_12m import FEATURES
from models.monthly_projection import MIN_OBSERVATIONS, MIN_SPAN_MONTHS
from models.xgboost_model import observed_mask

KEYS = ['district_id', 'origin_date', 'target_date', 'horizon']
MIN_CASES, MIN_DISTRICTS = 30, 10


def key_hash(cases):
    if cases.duplicated(KEYS).any():
        raise ValueError('Duplicate forecast case keys.')
    rows = cases[KEYS].sort_values(KEYS).astype(str).to_dict('records')
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def observed_history(frame):
    values = frame.loc[observed_mask(frame) & ~frame.is_imputed].copy()
    values.attrs = {}
    values['date'] = pd.to_datetime(values.date)
    if values.duplicated(['district_id', 'date']).any():
        raise ValueError('Duplicate observed month keys.')
    if not np.isfinite(values.gwl_current).all() or values.gwl_current.lt(0).any():
        raise ValueError('Invalid measured m_bgl depths.')
    return values.sort_values(['district_id', 'date'])


def baseline_cases(cases, frame):
    """Independently resolve the last eligible measurement and exact prior year.

    Imputed calendar values cannot supply either baseline. An unavailable
    seasonal value stays unavailable; it never falls back to persistence.
    """
    result = cases.copy()
    result.attrs = {}
    result['origin_date'] = pd.to_datetime(result.origin_date)
    result['target_date'] = pd.to_datetime(result.target_date)
    key_hash(result)
    months = ((result.target_date.dt.year-result.origin_date.dt.year)*12
              + result.target_date.dt.month-result.origin_date.dt.month)
    if not months.eq(result.horizon).all() or not result.horizon.between(1, 12).all():
        raise ValueError('Targets must use exact M+1 through M+12 horizons.')
    labels = observed_history(frame)
    groups = {did: g for did, g in labels.groupby('district_id', sort=False)}
    records = []
    for row in result.itertuples():
        group = groups.get(row.district_id)
        eligible = (group.loc[group.date.le(row.origin_date)] if group is not None
                    else labels.iloc[:0])
        previous = row.target_date-pd.DateOffset(years=1)
        seasonal = eligible.loc[eligible.date.eq(previous)]
        records.append({
            'persistence': float(eligible.iloc[-1].gwl_current) if len(eligible) else np.nan,
            'persistence_date': eligible.iloc[-1].date if len(eligible) else pd.NaT,
            'seasonal': float(seasonal.iloc[0].gwl_current) if len(seasonal) else np.nan,
            'seasonal_date': previous if len(seasonal) else pd.NaT,
            'observation_count': len(eligible),
            'age': ((row.origin_date.year-eligible.iloc[-1].date.year)*12
                    + row.origin_date.month-eligible.iloc[-1].date.month) if len(eligible) else np.nan,
        })
    for name in records[0] if records else ['persistence', 'persistence_date', 'seasonal',
                                           'seasonal_date', 'observation_count', 'age']:
        result[name] = [r[name] for r in records]
    return result


def metric(cases, method):
    if cases.empty:
        return {'n': 0, 'districts': 0, 'supported': False}
    error = cases[method].to_numpy(float)-cases.actual.to_numpy(float)
    if not np.isfinite(error).all():
        raise ValueError('Match finite predictions before calculating metrics.')
    absolute = pd.Series(np.abs(error), index=cases.index)
    districts = int(cases.district_id.nunique())
    district_means = absolute.groupby(cases.district_id).mean()
    return {'n': len(cases), 'districts': districts,
            'supported': len(cases) >= MIN_CASES and districts >= MIN_DISTRICTS,
            'mae_m': float(absolute.mean()), 'rmse_m': float(np.sqrt(np.mean(error**2))),
            'district_macro_mae_m': float(district_means.mean()),
            'median_absolute_error_m': float(np.median(absolute)),
            'mean_signed_error_m': float(error.mean()),
            'overestimate_fraction': float(np.mean(error > 0)),
            'underestimate_fraction': float(np.mean(error < 0)),
            'equal_fraction': float(np.mean(error == 0)),
            'absolute_error_quantiles_m': {str(q): float(np.quantile(absolute, q))
                                         for q in (.1, .25, .5, .75, .9, .95, .99, 1.)},
            'signed_error_quantiles_m': {str(q): float(np.quantile(error, q))
                                       for q in (.01, .1, .5, .9, .99)},
            'error_histogram': {'edges_m': [-1000000, -10, -5, -2, -1, 0, 1, 2, 5, 10, 1000000],
                'counts': np.histogram(error, [-1000000,-10,-5,-2,-1,0,1,2,5,10,1000000])[0].tolist()}}


def matched(cases, methods):
    key_hash(cases)
    mask = np.isfinite(cases[methods].to_numpy(float)).all(axis=1)
    subset = cases.loc[mask]
    return {'case_keys_sha256': key_hash(subset), 'excluded': int((~mask).sum()),
            'methods': {m: metric(subset, m) for m in methods}}


def district_weights(training):
    """Equal total weight per training district, mean row weight exactly one."""
    if training.empty or training.district_id.isna().any():
        raise ValueError('Nonempty identified training districts required.')
    counts = training.groupby('district_id').district_id.transform('size').to_numpy(float)
    weights = len(training)/(training.district_id.nunique()*counts)
    return weights


def partition(pairs, fold):
    cutoff = pd.Timestamp(fold['train_target_cutoff'])
    first = pd.Timestamp(fold['validation_origin_start'])
    end = pd.Timestamp(fold['validation_target_end'])
    if first < (cutoff.to_period('M')+13).to_timestamp():
        raise ValueError('Twelve-month origin embargo violated.')
    if end >= pd.Timestamp('2023-01-01'):
        raise ValueError('Development targets must precede inspected 2023 windows.')
    train = pairs.loc[pairs.target_date.le(cutoff)].copy()
    valid = pairs.loc[pairs.origin_date.between(first, pd.Timestamp(fold['validation_origin_end']))
                      & pairs.target_date.le(end)].copy()
    if train.empty or valid.empty or train.target_date.max() >= valid.origin_date.min():
        raise ValueError('Empty or overlapping chronological partition.')
    return train, valid


def fold_for_year(year):
    return {'name': f'rolling_{year}', 'year': year,
            'train_target_cutoff': f'{year-2}-12-31',
            'validation_origin_start': f'{year}-01-01',
            'validation_origin_end': f'{year}-12-01',
            'validation_target_end': f'{year+1}-12-31'}


def describe_pairs(pairs):
    if pairs.empty:
        return {'n': 0, 'districts': 0}
    return {'n': len(pairs), 'districts': int(pairs.district_id.nunique()),
            'origin_range': [str(pairs.origin_date.min().date()), str(pairs.origin_date.max().date())],
            'target_range': [str(pairs.target_date.min().date()), str(pairs.target_date.max().date())],
            'by_horizon': {str(int(h)): {'n': len(g), 'districts': int(g.district_id.nunique()),
                'origin_months': int(g.origin_date.nunique()), 'target_months': int(g.target_date.nunique()),
                'supported': len(g) >= MIN_CASES and g.district_id.nunique() >= MIN_DISTRICTS}
                for h, g in pairs.groupby('horizon_months')}}


def choose_folds(pairs):
    """Last two supported pre-2023 years; two eligible inner years per outer.

    Availability rules are independent of residuals and model performance.
    Inner validation targets cannot exceed the outer training-label cutoff.
    """
    eligible, availability = [], []
    for year in range(int(pairs.target_date.min().year)+2, 2022):
        fold = fold_for_year(year)
        train, valid = partition(pairs, fold)
        years = int(train.target_date.dt.year.nunique())
        supported = (len(train) >= 20000 and train.district_id.nunique() >= 250 and years >= 5
                     and len(valid) >= 1000 and valid.district_id.nunique() >= 100)
        availability.append({'fold': fold, 'training': describe_pairs(train),
                             'validation': describe_pairs(valid), 'eligible': bool(supported)})
        if supported:
            eligible.append(fold)
    if len(eligible) < 4:
        raise ValueError('Insufficient history for the declared nested experiment.')
    outer = eligible[-2:]
    for fold in outer:
        inner = [f for f in eligible if pd.Timestamp(f['validation_target_end'])
                 <= pd.Timestamp(fold['train_target_cutoff'])][-2:]
        if len(inner) != 2:
            raise ValueError('Two supported chronological inner folds required.')
        fold['inner_years'] = [f['year'] for f in inner]
    inner_years = sorted({y for f in outer for y in f['inner_years']})
    return {'outer': outer, 'inner': [fold_for_year(y) for y in inner_years],
            'availability': availability}


def metadata(cases, frame, original_frame):
    """Origin-only subgroup descriptors, never full-history count thresholds."""
    out = cases.copy()
    out.attrs = {}
    obs = observed_history(frame)
    old = observed_history(original_frame)
    groups = {d: g for d, g in frame.groupby('district_id')}
    known = {d: g for d, g in obs.groupby('district_id')}
    original = {d: g for d, g in old.groupby('district_id')}
    old_keys = set(zip(old.district_id, old.date))
    added = {d: set(g.date)-{t for did,t in old_keys if did == d} for d,g in known.items()}
    cached, rows = {}, []
    for r in out.itertuples():
        origin = pd.Timestamp(r.origin_date)
        key = (r.district_id, origin)
        if key not in cached:
            g = groups.get(r.district_id, frame.iloc[:0])
            history = known.get(r.district_id, obs.iloc[:0])
            history = history.loc[history.date.le(origin)]
            past_old = original.get(r.district_id, old.iloc[:0])
            past_old = past_old.loc[past_old.date.le(origin)]
            indexed = g.set_index('date')
            record = {'state_id': r.district_id.split('-',1)[0],
                'history_group': '<12' if len(history)<12 else '12-23' if len(history)<24 else '24-59' if len(history)<60 else '60+',
                'gained_history': any(t<=origin for t in added.get(r.district_id, set())),
                'newly_local_history': bool(len(history) and past_old.empty),
                'substantial_original_history': len(past_old)>=24}
            exact = []
            for lag in (3,6):
                date = origin-pd.DateOffset(months=lag)
                value = indexed.loc[date, 'gwl_current'] if date in indexed.index else np.nan
                record[f'finite_calendar_lag_{lag}'] = bool(np.isfinite(value))
                record[f'observed_calendar_lag_{lag}'] = bool(history.date.eq(date).any())
                exact.append(bool(np.isfinite(value)))
            span = ((origin.year-history.iloc[0].date.year)*12+origin.month-history.iloc[0].date.month) if len(history) else 0
            fit_eligible = len(history)>=MIN_OBSERVATIONS and span>=MIN_SPAN_MONTHS
            record['projection_lag_fallback'] = bool(not all(exact) and fit_eligible)
            record['projection_fit_eligible'] = bool(fit_eligible)
            raw = indexed.loc[origin, ['rainfall_current','temperature','evapotranspiration']].to_numpy(float) if origin in indexed.index else np.full(3,np.nan)
            record['origin_weather_raw_available'] = bool(np.isfinite(raw).all())
            record['age_group'] = 'unavailable' if history.empty else '0-3' if (origin.year-history.iloc[-1].date.year)*12+origin.month-history.iloc[-1].date.month<=3 else '4-12' if (origin.year-history.iloc[-1].date.year)*12+origin.month-history.iloc[-1].date.month<=12 else '13+'
            cached[key] = record
        rows.append(cached[key])
    for name in rows[0] if rows else []:
        out[name] = [v[name] for v in rows]
    return out


SUBGROUPS = ['horizon','state_id','tier','history_group','age_group',
             'finite_calendar_lag_3','finite_calendar_lag_6','observed_calendar_lag_3',
             'observed_calendar_lag_6','projection_lag_fallback','origin_weather_raw_available',
             'gained_history','newly_local_history','substantial_original_history']


def diagnostics(cases, methods, *, district_detail=True):
    result = {'all_available': {m: metric(cases.loc[np.isfinite(cases[m])],m) for m in methods},
              'joint': matched(cases,methods), 'subgroups': {}}
    for field in SUBGROUPS + (['district_id'] if district_detail else []):
        if field in cases:
            result['subgroups'][field] = {str(k): {
                **matched(g,methods),
                'all_available': {m:metric(g.loc[np.isfinite(g[m])],m) for m in methods},
                'persistence_paired':matched(g,[m for m in methods if m!='seasonal'])}
                for k,g in cases.groupby(field,dropna=False)}
    changes = {}
    reference = 'origin_gwl' if 'origin_gwl' in cases else 'persistence'
    common = cases.loc[np.isfinite(cases[reference])]
    actual = common.actual-common[reference]
    for method in methods:
        predicted = common[method]-common[reference]
        ok = np.isfinite(predicted)
        a,p = actual[ok].to_numpy(float),predicted[ok].to_numpy(float)
        changes[method] = {'n':len(a),'reference':reference,
            'actual_change_mean_m':float(a.mean()),'predicted_change_mean_m':float(p.mean()),
            'actual_change_sd_m':float(a.std()),'predicted_change_sd_m':float(p.std()),
            'mean_absolute_actual_change_m':float(np.abs(a).mean()),
            'mean_absolute_predicted_change_m':float(np.abs(p).mean()),
            'larger_absolute_change_fraction':float((np.abs(p)>np.abs(a)).mean()),
            'wrong_direction_fraction_nonzero_actual':float((np.sign(p[a!=0])!=np.sign(a[a!=0])).mean()) if np.any(a!=0) else None}
    result['changes'] = changes
    return result


def paired_district_bootstrap(cases, candidate, baseline, repeats=2000):
    subset = cases.loc[np.isfinite(cases[[candidate,baseline]].to_numpy(float)).all(axis=1)].copy()
    subset['difference'] = abs(subset[candidate]-subset.actual)-abs(subset[baseline]-subset.actual)
    means = subset.groupby('district_id').difference.mean().to_numpy()
    if len(means)<MIN_DISTRICTS:
        return {'status':'unsupported','districts':len(means)}
    rng = np.random.default_rng(42)
    values = np.mean(rng.choice(means,(repeats,len(means)),replace=True),axis=1)
    return {'status':'exploratory_district_cluster_bootstrap','districts':len(means),
            'mean_macro_mae_difference_m':float(means.mean()),
            'percentile_95_interval_m':np.quantile(values,[.025,.975]).tolist(),
            'candidate_better_district_fraction':float((means<0).mean()),
            'caveat':'Resamples entire districts; shared target/weather/state dependence across districts remains. Not prospective evidence.'}
