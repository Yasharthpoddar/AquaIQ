"""Read-only, chronological comparison of the saved forecaster and alternatives.

python -m models.audit_evaluation --output-dir reports/audit-2026-10-17 --include-monthly

Candidates are fitted in memory. Only reports and per-case predictions are
written; source data, database state and production model bundles are untouched.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from models import xgboost_model as forecast


def comparison_splits(prepared, cutoff):
    """Reserve final target dates before model selection and preprocessing fits."""
    validation_start = (pd.Timestamp(cutoff).to_period('M') + forecast.EMBARGO_MONTHS + 1).to_timestamp()
    validation_end = pd.Timestamp(forecast.CONFIG['date_range']['val_end'])
    train, validation = forecast.temporal_split(prepared, cutoff, validation_start, validation_end)
    final_start = pd.Timestamp(forecast.CONFIG['date_range']['test_start'])
    validation = validation.loc[(validation.target_date <= validation_end) & (validation.target_date < final_start)].copy()
    _, test = forecast.temporal_split(prepared, cutoff, forecast.heldout_origin_start(cutoff),
                                      forecast.CONFIG['date_range']['end'])
    test = test.loc[test.target_date >= final_start].copy()
    return train, validation, test


def _coverage(frame):
    return {'n': len(frame), 'districts': int(frame.district_id.nunique()),
            'origin_start': frame.date.min().date().isoformat() if len(frame) else None,
            'origin_end': frame.date.max().date().isoformat() if len(frame) else None,
            'target_start': frame.target_date.min().date().isoformat() if len(frame) else None,
            'target_end': frame.target_date.max().date().isoformat() if len(frame) else None}


def summarize(frame, names):
    result = {'n': len(frame), 'districts': int(frame.district_id.nunique()), 'models': {}}
    paired = np.isfinite(frame.seasonal_naive.to_numpy(dtype=float))
    result['seasonal_paired_comparison'] = {'n': int(paired.sum()), 'models': {}}
    for name in names:
        valid = np.isfinite(frame[name].to_numpy(dtype=float))
        result['models'][name] = forecast.metrics(frame.loc[valid, 'actual'], frame.loc[valid, name]) if valid.any() else {'n': 0}
        use = paired & valid
        result['seasonal_paired_comparison']['models'][name] = forecast.metrics(frame.loc[use, 'actual'], frame.loc[use, name]) if use.any() else {'n': 0}
    return result


def select_on_validation(validation, names):
    """A model must cover every validation case to compete on overall RMSE."""
    if validation.empty:
        return None
    eligible = [name for name in names if np.isfinite(validation[name].to_numpy(dtype=float)).all()]
    return min(eligible, key=lambda name: forecast.metrics(validation.actual, validation[name])['rmse_m']) if eligible else None


def compare_direct(frame, model, card, alternatives=None):
    prepared = forecast.create_target(forecast.encode_crop_season(frame))
    train, validation, test = comparison_splits(prepared, card['train_target_cutoff'])
    if train.empty:
        raise ValueError('No observed training labels available for comparison.')
    columns = forecast.CANONICAL_FEATURE_COLS
    candidates = alternatives if alternatives is not None else {
        'ridge': make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                               StandardScaler(), Ridge(alpha=10.)),
        'random_forest': make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                                      RandomForestRegressor(n_estimators=150, max_depth=12,
                                          min_samples_leaf=5, max_features=.85, random_state=42, n_jobs=4)),
    }
    for name, candidate in candidates.items():
        print(f'Fitting {name} on {len(train):,} observed labels', flush=True)
        candidate.fit(train[columns], train.target_gwl_6mo)
    names = ['saved_xgboost', 'persistence', 'seasonal_naive', *candidates]
    tables = {}
    for split, rows in [('validation', validation), ('test', test)]:
        table = rows[['district_id', 'date', 'target_date']].rename(columns={'date': 'origin_date'}).reset_index(drop=True)
        table['split'], table['horizon_months'] = split, 6
        table['actual'] = rows.target_gwl_6mo.to_numpy()
        table['saved_xgboost'] = model.predict(rows[columns]) if len(rows) else []
        table['persistence'] = rows.gwl_current.to_numpy()
        table['seasonal_naive'] = rows.seasonal_naive_6mo.to_numpy()
        for name, candidate in candidates.items():
            table[name] = candidate.predict(rows[columns]) if len(rows) else []
        tables[split] = table
    selected = select_on_validation(tables['validation'], names)
    reports = {}
    for split, table in tables.items():
        reports[split] = {**summarize(table, names), 'coverage': _coverage(validation if split == 'validation' else test),
                         'by_district': {str(district): summarize(part, names) for district, part in table.groupby('district_id', sort=True)},
                         'by_horizon_months': {'6': summarize(table, names)}}
    return {
        'protocol': {'training_target_cutoff': card['train_target_cutoff'],
                     'embargo_months': forecast.EMBARGO_MONTHS,
                     'training': _coverage(train),
                     'validation_target_end': forecast.CONFIG['date_range']['val_end'],
                     'final_test_target_start': forecast.CONFIG['date_range']['test_start'],
                     'target': 'groundwater depth, not depletion change', 'units': 'm_bgl',
                     'selection_metric': 'validation RMSE on all validation cases',
                     'preprocessing': 'Ridge/RF median imputer and Ridge scaler fit on training rows only',
                     'alternatives': {'ridge_alpha': 10., 'random_forest_trees': 150, 'random_forest_max_depth': 12,
                                      'random_forest_min_leaf': 5, 'random_forest_max_features': .85, 'seed': 42},
                     'seasonal_baseline': 'exact observed depth at target month one year earlier (origin minus six calendar months)',
                     'origin_policy': 'Known causal origin GWL may be limited forward-fill; target must be observed.'},
        'saved_bundle_id': card['bundle_id'],
        'saved_model_sha256': card['model_sha256'],
        'selected_by_validation': selected,
        'selected_test_metrics': reports['test']['models'].get(selected) if selected else None,
        **reports,
    }, pd.concat(tables.values(), ignore_index=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=forecast.ROOT / 'reports/audit-2026-10-17')
    parser.add_argument('--include-monthly', action='store_true')
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    if output == (forecast.ROOT / 'reports').resolve() or not output.is_relative_to((forecast.ROOT / 'reports').resolve()):
        parser.error('Output must be a dedicated directory under reports/.')
    source = forecast.ROOT / forecast.CONFIG['paths']['data_processed'] / 'features_matrix.csv'
    if not source.is_file():
        parser.error('Verified local features are required; this audit never falls back to the database.')
    frame = forecast.load_feature_matrix()
    model, card = forecast.load_model_bundle(expected_generation=frame.attrs['feature_generation_id'])
    direct, cases = compare_direct(frame, model, card)
    report = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'feature_generation_id': frame.attrs['feature_generation_id'],
              'feature_csv_sha256': forecast.sha256_file(source),
              'data_sha256': frame.attrs['data_sha256'],
              'saved_training_data_sha256': card.get('data_sha256'),
              'production_bundles_replaced': False, 'database_written': False,
              'direct_six_month': direct,
              'limitations': ['The saved bundle and its holdout have already been inspected; this is a reproducibility audit, not a newly blinded trial.',
                              'Sparse observed labels and the small set of recent districts cannot establish nationwide current-period accuracy.',
                              'Aggregate R2 is influenced by depth differences between districts; consult errors and district metrics.',
                              'Historical publication/revision dates and comparable-well panels are unavailable.',
                              'No MAPE is reported because targets can be zero or close to zero.',
                              'No calibrated prediction intervals are claimed; point forecast evaluation does not establish interval coverage.']}
    if args.include_monthly:
        from models import climate_forecast as climate
        monthly_model, monthly_card = climate.load_bundle(expected_generation=frame.attrs['feature_generation_id'])
        _, heldout = climate.split_pairs(climate.prepare_pairs(frame), monthly_card['train_target_cutoff'])
        # Keep observed final labels separate from the earlier validation period.
        final_start = pd.Timestamp(forecast.CONFIG['date_range']['test_start'])
        report['saved_monthly_climate'] = {'model_sha256': monthly_card['model_sha256'],
            'train_target_cutoff': monthly_card['train_target_cutoff'],
            'origin_policy': 'Both origin and target explicitly observed; current estimated anchors and zone fallback are not validated here.',
            'validation': climate.evaluate_assumed_weather(monthly_model, frame, heldout[heldout.target_date < final_start]),
            'test': climate.evaluate_assumed_weather(monthly_model, frame, heldout[heldout.target_date >= final_start])}
    output.mkdir(parents=True, exist_ok=True)
    cases.to_csv(output / 'model_comparison_cases.csv', index=False)
    forecast._write_json(output / 'model_evaluation.json', report)
    print(f"Report: {output / 'model_evaluation.json'}; selected on validation: {direct['selected_by_validation']}", flush=True)
    return report


if __name__ == '__main__':
    main()
