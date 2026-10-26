"""Retrospective fixed-panel evaluation; never trains, publishes or touches the DB.

Run: python -m scripts.evaluate_state_xgboost --output reports/<new-directory>
Output must not already exist. Source month flags are not publication timestamps.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from models import state_forecast as state


def exact_panel_mean(labels, districts, month):
    keys = pd.MultiIndex.from_tuples([(d, pd.Timestamp(month)) for d in districts])
    values = labels.reindex(keys)
    return float(values.mean()) if len(values) and values.notna().all() else None


def metrics(rows, column):
    if not len(rows):
        return dict(n=0, mae_m=None, rmse_m=None, r2=None)
    actual = rows.actual.to_numpy(float)
    error = rows[column].to_numpy(float) - actual
    variance = float(np.sum((actual - actual.mean()) ** 2))
    return dict(n=len(rows), mae_m=float(np.abs(error).mean()),
                rmse_m=float(np.sqrt(np.mean(error ** 2))),
                r2=1-float(np.sum(error ** 2))/variance if len(rows) > 1 and variance > 1e-12 else None)


def comparisons(rows):
    output = {}
    for name, columns in [('xgb_and_observed_persistence', ['xgboost', 'persistence']),
                          ('all_three_matched', ['xgboost', 'persistence', 'seasonal_naive'])]:
        matched = rows.dropna(subset=columns)
        output[name] = {model: metrics(matched, model) for model in columns}
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    frame = state.get_feature_matrix()
    _, card = state.climate.load_bundle(expected_generation=frame.attrs.get('feature_generation_id'))
    assert pd.Timestamp(card['train_target_cutoff']) <= pd.Timestamp('2019-12-31'), 'Protocol requires a pre-2020 training cutoff.'
    obs = frame.loc[state.state_observed_mask(frame) & np.isfinite(frame.gwl_current) & frame.gwl_current.ge(0)].copy()
    labels = obs.set_index(['district_id', 'date']).gwl_current
    if not labels.index.is_unique:
        raise ValueError('Ambiguous target district-month keys.')
    origins = [pd.Timestamp(year=y, month=m, day=1) for y in range(2021, 2026) for m in (1, 5, 8, 11)]
    cases, exclusions, panels = [], [], []
    for origin in origins:
        cutoff = origin + pd.offsets.MonthEnd(0)
        latest = obs.loc[obs.date.le(origin)].sort_values('date').groupby('district_id').gwl_current.last()
        for code in state.STATES_REGISTRY:
            value = state.forecast_state_twelve_months(code, cutoff)
            common = dict(state_id=code, origin_month=origin.date().isoformat(), as_of=cutoff.date().isoformat())
            if value['status'] != 'forecast':
                exclusions.append(dict(**common, horizon=None, reason=value['status'], detail=value.get('message')))
                continue
            ids = value['contributing_district_ids']
            panels.append(dict(**common, panel_id=value['panel_id'], districts=ids,
                               coverage_pct=value['district_coverage_pct']))
            persist = latest.reindex(ids)
            if persist.isna().any():
                raise ValueError('Eligible panel lacks an origin-observed persistence reference.')
            for row in value['forecast']:
                target = pd.Timestamp(row['target_date'])
                actual = exact_panel_mean(labels, ids, target)
                if actual is None:
                    exclusions.append(dict(**common, horizon=row['horizon'], reason='incomplete_observed_target_panel',
                                           detail='At least one fixed-panel district has no source-marked observed target month.'))
                    continue
                seasonal_date = target - pd.DateOffset(years=1)
                seasonal = exact_panel_mean(labels, ids, seasonal_date) if seasonal_date <= origin else None
                cases.append(dict(**common, target_month=row['target_date'], horizon=row['horizon'],
                    panel_id=value['panel_id'], n_districts=len(ids), coverage_pct=value['district_coverage_pct'],
                    actual=actual, xgboost=row['predicted_gwl'], persistence=float(persist.mean()),
                    estimated_anchor=value['estimated_current_gwl_m_bgl'], seasonal_naive=seasonal,
                    seasonal_reference_month=seasonal_date.date().isoformat(), units='m_bgl'))
        print(f'{origin:%Y-%m}: {len(cases)} eligible cases; {len(exclusions)} exclusions', flush=True)
    columns = ['state_id','origin_month','as_of','target_month','horizon','panel_id','n_districts',
               'coverage_pct','actual','xgboost','persistence','estimated_anchor','seasonal_naive','seasonal_reference_month','units']
    cases = pd.DataFrame(cases, columns=columns)
    for model in ('xgboost', 'persistence', 'seasonal_naive'):
        cases[model + '_error_m'] = cases[model] - cases.actual
    cases.to_csv(args.output / 'cases.csv', index=False)
    pd.DataFrame(exclusions).to_csv(args.output / 'exclusions.csv', index=False)
    (args.output / 'panels.json').write_text(json.dumps(panels, indent=2), encoding='utf-8')
    result = dict(protocol='Frozen deployed XGBoost, retrospective origin-limited inputs, fixed equal district panels',
        model_sha256=card['model_sha256'], train_target_cutoff=card['train_target_cutoff'],
        data_sha256=frame.attrs.get('data_sha256'), feature_generation=frame.attrs.get('feature_generation_id'),
        origins=[d.date().isoformat() for d in origins], attempted_state_origins=len(origins)*len(state.STATES_REGISTRY),
        available_state_origins=len(panels), eligible_cases=len(cases),
        target_range=[str(cases.target_month.min()), str(cases.target_month.max())] if len(cases) else None,
        comparison=comparisons(cases), by_horizon={str(h): comparisons(g) for h,g in cases.groupby('horizon')},
        by_state={s: comparisons(g) for s,g in cases.groupby('state_id')},
        limitations=[
            'This is a new retrospective diagnostic on previously inspected historical data, not an untouched final test or prospective campaign.',
            'No model training, tuning, selection or promotion. Origins fixed before looking at outcomes; 2020 is embargoed.',
            'A target is eligible only when every origin-selected district has an exact observed month label. Panel never shrinks to fit target availability.',
            'Persistence is each panel district latest observed depth at origin, averaged equally. Seasonal naive requires exact target-minus-12-month observed values for the full panel.',
            'Weather uses origin-limited historical climatology; current anchors and lags can be estimated across gaps. No realized future weather supplied.',
            'Publication, retrieval and measurement acquisition times remain unknown. Monthly cutoff is a retrospective timing assumption, not evidence of live availability.',
            'State labels are equally weighted source-marked district measurements, not independently collected representative state observations. Stable well IDs and composition remain unknown.',
            'Unobserved target months are excluded, never imputed. Available cases may be strongly selected and unrepresentative.'],
        evidence_hashes={name: hashlib.sha256((args.output/name).read_bytes()).hexdigest() for name in ('cases.csv','exclusions.csv','panels.json')})
    (args.output/'evaluation.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(result['comparison'], indent=2), flush=True)


if __name__ == '__main__':
    main()
