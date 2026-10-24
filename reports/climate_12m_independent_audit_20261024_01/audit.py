"""Read-only historical audit. Never fit, publish, connect to DB, or serve forecasts."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write(name, value):
    path = OUT / name
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(value, indent=2, allow_nan=False, default=str) + '\n', encoding='utf-8')


def snapshot():
    paths = set()
    for directory in ['data', 'models', 'reports', 'config', 'api', 'tests', 'dashboard/src', 'dashboard/tests']:
        for p in (ROOT / directory).rglob('*'):
            if p.is_file() and not p.is_relative_to(OUT) and '__pycache__' not in p.parts and p.suffix != '.pyc':
                paths.add(p)
    for name in ['.gitignore', '.dockerignore', 'docker-compose.yml', 'dashboard/package.json', 'dashboard/package-lock.json']:
        p = ROOT / name
        if p.exists():
            paths.add(p)
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(paths)}


def preservation(mode):
    files = snapshot()
    if mode == 'before':
        write('preservation_before.json', {'at_utc': datetime.now(timezone.utc).isoformat(), 'files': files,
            'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'status': subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True)})
        print('Protected files hashed:', len(files), flush=True)
    else:
        before = json.loads((OUT / 'preservation_before.json').read_text())['files']
        write('preservation_after.json', {'at_utc': datetime.now(timezone.utc).isoformat(), 'files': files,
            'changed': [p for p in before if p in files and before[p] != files[p]],
            'missing': sorted(set(before) - set(files)), 'new_outside_audit': sorted(set(files) - set(before))})


def recompute():
    outputs = ['reconstructed_historical_cases.csv', 'reconstructed_historical_inputs.csv', 'weather_reference_months.csv',
               'eligibility_counts.csv', 'matched_metrics.csv', 'group_metrics.csv', 'verification.json']
    if any((OUT / name).exists() for name in outputs):
        raise FileExistsError('Use a new uniquely named audit directory to preserve completed results.')
    import numpy as np
    import pandas as pd
    import xgboost as xgb
    import psycopg2
    def forbidden(*args, **kwargs):
        raise RuntimeError('Audit forbids fitting, publishing, and database connections')
    xgb.XGBRegressor.fit = forbidden
    psycopg2.connect = forbidden
    from models import climate_forecast_12m as production
    from models.climate_inputs import forecast_weather
    production.train = production.publish_bundle = forbidden

    manifest = json.loads((ROOT / 'data/processed/feature_manifest.json').read_text())
    csv = ROOT / 'data/processed/features_matrix.csv'
    assert digest(csv) == manifest['feature_csv_sha256']
    frame = pd.read_csv(csv, parse_dates=['date'])
    assert not frame.duplicated(['district_id', 'date']).any()
    assert (frame.date.dt.day == 1).all()
    flag = frame.is_observed.astype('string').str.strip().str.lower().isin(['true', '1'])
    observed = frame.loc[flag & np.isfinite(frame.gwl_current) & frame.gwl_current.ge(0)].copy()
    assert not frame.loc[flag].is_imputed.astype('string').str.lower().isin(['true', '1']).any()
    pointer = json.loads((ROOT / 'models/checkpoints/aquaiq_climate_12m.json').read_text())
    folder = ROOT / 'models/checkpoints'
    model_path, card_path = folder / pointer['model_path'], folder / pointer['card_path']
    assert digest(model_path) == pointer['model_sha256']
    assert digest(card_path) == pointer['card_sha256']
    card = json.loads(card_path.read_text())
    model = xgb.XGBRegressor()
    model.load_model(str(model_path))
    features = card['features']
    assert features == model.get_booster().feature_names
    source = frame.set_index(['district_id', 'date'])
    targets = observed[['district_id', 'date', 'gwl_current']].rename(columns={'date': 'target_date', 'gwl_current': 'actual'})
    cases = []
    membership = []
    # Independent exact-key joins and cumulative realized-weather eligibility.
    for horizon in range(1, 13):
        origins = observed.rename(columns={'date': 'origin_date', 'gwl_current': 'origin_gwl'}).copy()
        origins['target_date'] = origins.origin_date + pd.DateOffset(months=horizon)
        joined = origins.merge(targets, on=['district_id', 'target_date'], validate='one_to_one')
        valid = np.isfinite(joined[['rainfall_current', 'temperature', 'evapotranspiration']]).all(axis=1).to_numpy(copy=True)
        for step in range(1, horizon + 1):
            keys = pd.MultiIndex.from_arrays([joined.district_id, joined.origin_date + pd.DateOffset(months=step)])
            weather = source.reindex(keys)[['rainfall_current', 'temperature', 'evapotranspiration']].to_numpy()
            valid &= np.isfinite(weather).all(axis=1) & (weather[:, [0, 2]] >= 0).all(axis=1)
        test = joined.origin_date.ge('2021-01-01')
        membership.append({'horizon': horizon, 'observed_joined_test': int(test.sum()), 'future_weather_eligible_test': int((test & valid).sum()),
                           'training_pairs': int((joined.target_date.le('2019-12-31') & valid).sum())})
        part = joined.loc[test & valid].copy()
        part['horizon'] = horizon
        cases.append(part)
    eligible = pd.concat(cases, ignore_index=True)
    production_pairs = production.prepare_pairs(frame)
    pp = production_pairs.loc[production_pairs.origin_date.ge('2021-01-01')]
    key = ['district_id', 'origin_date', 'target_date']
    assert set(map(tuple, pp[key].to_numpy())) == set(map(tuple, eligible[key].to_numpy()))
    rows, feature_records, refs = [], [], []
    # Independent reference means and feature encoding; no source evaluation calls.
    for (district, origin), part in eligible.groupby(['district_id', 'origin_date'], sort=True):
        history = frame.loc[frame.district_id.eq(district) & frame.date.le(origin)].sort_values('date').copy()
        known = observed.loc[observed.district_id.eq(district) & observed.date.le(origin)].sort_values('date')
        current = source.loc[(district, origin)]
        assumed = []
        for h in range(1, 13):
            target_date = origin + pd.DateOffset(months=h)
            row = {'date': target_date}
            for name, column in [('rainfall', 'rainfall_current'), ('temperature', 'temperature'), ('evapotranspiration', 'evapotranspiration')]:
                samples = history.loc[history.date.dt.month.eq(target_date.month), ['date', column]].copy()
                valid = np.isfinite(samples[column]) & (samples[column].between(-100, 70) if name == 'temperature' else samples[column].ge(0))
                for flag_column in [column + '_is_imputed', name + '_is_imputed']:
                    if flag_column in history:
                        valid &= history.loc[samples.index, flag_column].astype('string').str.strip().str.lower().isin(['false', '0'])
                        break
                samples = samples.loc[valid].tail(10)
                assert samples.date.dt.year.nunique() >= 3
                row[name] = float(samples[column].mean())
                refs.append({'district_id': district, 'origin_date': origin, 'horizon': h, 'field': name,
                             'latest_reference_month': samples.date.max(), 'earliest_reference_month': samples.date.min(), 'n': len(samples)})
            assumed.append(row)
        path = pd.DataFrame(assumed)
        actual_helper = forecast_weather(frame.loc[frame.district_id.eq(district)], origin + pd.offsets.MonthEnd(0), months=12)
        assert actual_helper['status'] == 'available'
        assert np.allclose(path[['rainfall', 'temperature', 'evapotranspiration']], actual_helper['path'][['rainfall', 'temperature', 'evapotranspiration']], atol=1e-12)
        encoded = []
        for h, row in enumerate(assumed, 1):
            values = {'origin_gwl': current.gwl_current, 'origin_gwl_lag_3mo': current.gwl_lag_3mo, 'origin_gwl_lag_6mo': current.gwl_lag_6mo,
                      'origin_rainfall': current.rainfall_current, 'origin_temperature': current.temperature, 'origin_evapotranspiration': current.evapotranspiration,
                      'horizon_months': float(h), 'origin_month_sin': np.sin(2*np.pi*origin.month/12), 'origin_month_cos': np.cos(2*np.pi*origin.month/12),
                      'target_month_sin': np.sin(2*np.pi*row['date'].month/12), 'target_month_cos': np.cos(2*np.pi*row['date'].month/12),
                      'target_rainfall': row['rainfall'], 'target_temperature': row['temperature'], 'target_evapotranspiration': row['evapotranspiration'],
                      'cumulative_rainfall': sum(v['rainfall'] for v in assumed[:h]),
                      'cumulative_evapotranspiration': sum(v['evapotranspiration'] for v in assumed[:h]), 'mean_temperature': np.mean([v['temperature'] for v in assumed[:h]])}
            encoded.append(values)
        predictions = np.maximum(0, float(current.gwl_current) + model.predict(pd.DataFrame(encoded)[features]))
        for case in part.itertuples():
            seasonal = known.loc[known.date.dt.month.eq(case.target_date.month)]
            season_row = seasonal.iloc[-1] if len(seasonal) else None
            values = {'district_id': district, 'origin_date': origin, 'target_date': case.target_date, 'horizon': case.horizon,
                      'origin_gwl': float(current.gwl_current), 'actual': case.actual, 'predicted': float(predictions[case.horizon-1]),
                      'persistence': float(current.gwl_current), 'seasonal': float(season_row.gwl_current) if season_row is not None else np.nan,
                      'seasonal_reference_date': season_row.date if season_row is not None else pd.NaT,
                      'origin_is_observed': True, 'target_is_observed': True, 'units': 'm_bgl'}
            for method in ['predicted', 'persistence', 'seasonal']:
                values[method + '_error_m'] = values[method] - case.actual
            rows.append(values)
            feature_records.append({**{k:values[k] for k in key}, 'horizon': case.horizon, **encoded[case.horizon-1]})
    table = pd.DataFrame(rows).sort_values(['district_id', 'origin_date', 'horizon'])
    assert not table.duplicated(key).any()
    table.to_csv(OUT / 'reconstructed_historical_cases.csv', index=False)
    inputs = pd.DataFrame(feature_records)
    inputs.to_csv(OUT / 'reconstructed_historical_inputs.csv', index=False)
    pd.DataFrame(refs).to_csv(OUT / 'weather_reference_months.csv', index=False)
    pd.DataFrame(membership).to_csv(OUT / 'eligibility_counts.csv', index=False)
    def metric(part, column):
        error = part[column].to_numpy() - part.actual.to_numpy()
        denominator = ((part.actual - part.actual.mean())**2).sum()
        return {'n': len(part), 'mae_m': float(np.abs(error).mean()), 'rmse_m': float(np.sqrt(np.mean(error**2))),
                'r2': float(1-np.sum(error**2)/denominator) if len(part)>1 and denominator>1e-12 else None,
                'bias_m': float(error.mean())}
    summaries = []
    for cohort, part in [('xgb_persistence', table), ('all_three_matched', table.dropna(subset=['seasonal']))]:
        for horizon in [0] + list(range(1,13)):
            sample = part if horizon == 0 else part.loc[part.horizon.eq(horizon)]
            for method in ['predicted', 'persistence'] + (['seasonal'] if cohort == 'all_three_matched' else []):
                summaries.append({'cohort': cohort, 'horizon': horizon, 'method': method, **metric(sample, method)})
    pd.DataFrame(summaries).to_csv(OUT / 'matched_metrics.csv', index=False)
    grouped = []
    for dimension in ['district_id', 'horizon']:
        for group, part in table.groupby(dimension):
            for method in ['predicted', 'persistence', 'seasonal']:
                sample = part.dropna(subset=[method])
                grouped.append({'dimension': dimension, 'group': str(group), 'method': method, **metric(sample, method)})
    pd.DataFrame(grouped).to_csv(OUT / 'group_metrics.csv', index=False)
    saved = json.loads((ROOT / 'reports/climate_forecast_12m_evaluation.json').read_text())
    deltas = []
    for horizon in [0] + list(range(1,13)):
        reported = saved['evaluation'] if horizon == 0 else saved['evaluation']['by_horizon'][str(horizon)]
        for cohort, methods in [('xgb_persistence', [('predicted', reported['xgboost']), ('persistence', reported['persistence'])]),
                                ('all_three_matched', [('predicted', reported['seasonal_paired']['xgboost']), ('seasonal', reported['seasonal_paired']['baseline'])])]:
            for method, result in methods:
                independent = next(r for r in summaries if r['cohort'] == cohort and r['horizon'] == horizon and r['method'] == method)
                deltas.append({'horizon': horizon, 'cohort': cohort, 'method': method, 'n_matches': result['n'] == independent['n'],
                               **{k:independent[k]-result[k] for k in ['mae_m', 'rmse_m', 'r2']}})
    write('verification.json', {'rows': len(table), 'districts': table.district_id.nunique(),
        'unique_origins': len(table[['district_id','origin_date']].drop_duplicates()),
        'unique_targets': len(table[['district_id','target_date']].drop_duplicates()),
        'origin_start': str(table.origin_date.min()), 'origin_end': str(table.origin_date.max()),
        'target_start': str(table.target_date.min()), 'target_end': str(table.target_date.max()),
        'model_sha256': digest(model_path), 'feature_csv_sha256': digest(csv),
        'summary_differences': deltas,
        'original_row_predictions_saved': False,
        'method': 'Independently joined and encoded historical reconstruction from frozen existing bundle; not issuance or training.',
        'persistence_exact_cases': int(table.persistence.eq(table.actual).sum()),
        'persistence_within_1cm': int(table.persistence.sub(table.actual).abs().le(.01).sum()),
        'xgb_wins_absolute_error_vs_persistence': int(table.predicted.sub(table.actual).abs().lt(table.persistence.sub(table.actual).abs()).sum()),
        'xgb_feature_importance': card['feature_importance']})
    print(pd.DataFrame(summaries).to_string(index=False), flush=True)
    print('CASE DIAGNOSTICS', table.groupby('district_id').agg(n=('actual','size'), unique_targets=('target_date','nunique'), origin_values=('origin_gwl','nunique'), target_values=('actual','nunique')).to_string(), flush=True)


if __name__ == '__main__':
    if sys.argv[1] in ('before', 'after'):
        preservation(sys.argv[1])
    elif sys.argv[1] == 'recompute':
        recompute()
    else:
        raise ValueError('Use before, recompute, or after')
