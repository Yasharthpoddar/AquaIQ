"""Phase-1 audit: read saved evidence only; no estimator imports, fits or DB access.

Run snapshot, analyze, then verify. Outputs use exclusive creation. Existing
source datasets, reports and checkpoints are never rewritten.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OLD = ROOT / 'reports/candidates/six_month_selection_20261017'
EXP = OLD / 'experiment_v2'
NAMES = ['persistence', 'seasonal_naive', 'ridge', 'random_forest',
         'xgboost', 'hist_gradient_boosting']
CHECK_ONLY = False


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(name, value):
    if CHECK_ONLY:
        assert read(HERE / name) == value, name
        return
    with (HERE / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def csv(name, frame):
    if CHECK_ONLY:
        assert (HERE / name).read_text(encoding='utf-8') == frame.to_csv(index=False, lineterminator='\n'), name
        return
    with (HERE / name).open('x', encoding='utf-8', newline='') as stream:
        frame.to_csv(stream, index=False)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def inventory():
    paths = {ROOT / name for name in git('ls-files').splitlines()}
    for base in ['data', 'models/checkpoints', 'reports']:
        paths.update(p for p in (ROOT / base).rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha(p)}
            for p in sorted(paths) if p.is_file() and HERE not in p.parents
            and '__pycache__' not in p.parts and p.name not in ['.env']}


def snapshot():
    write('baseline_inventory.json', {
        'commit': git('rev-parse', 'HEAD'), 'branch': git('branch', '--show-current'),
        'status_at_snapshot': git('status', '--short', '--untracked-files=all'),
        'history': git('log', '-5', '--oneline').splitlines(),
        'python': sys.version,
        'packages': {name: importlib.metadata.version(name) for name in
                     ['numpy', 'pandas', 'scikit-learn', 'xgboost', 'pytest', 'Flask', 'psycopg2-binary']},
        'protected_files': inventory(),
        'scope': 'Tracked files plus all data, checkpoints and pre-existing reports. No secret values read. Database not accessed.'})


def metrics(frame, name):
    actual = frame.actual.to_numpy(float)
    error = frame[name].to_numpy(float) - actual
    sse = float(np.square(error).sum())
    resolved = len(actual) > 1 and np.ptp(actual) > 8*np.finfo(float).eps*max(1., float(np.abs(actual).max()))
    return {'n': len(frame), 'mae_m': float(np.abs(error).mean()),
            'rmse_m': float(np.sqrt(sse / len(frame))),
            'r2': float(1 - sse / np.square(actual - actual.mean()).sum()) if resolved else None}


def frames():
    lock = read(EXP / 'selection_lock.json')
    valid = None
    for family, item in lock['selected_by_family'].items():
        path = EXP / 'validation' / (item['candidate_id'] + '.csv')
        assert sha(path) == read(path.with_suffix('.json'))['case_csv_sha256']
        table = pd.read_csv(path, parse_dates=['date', 'target_date'])
        if valid is None:
            valid = table.drop(columns='prediction').copy()
        else:
            assert valid.case_id.tolist() == table.case_id.tolist()
            np.testing.assert_array_equal(valid.actual, table.actual)
            common = [key for key in table.columns if key != 'prediction']
            pd.testing.assert_frame_equal(valid[common], table[common])
        valid[family] = table.prediction.to_numpy()
    result = {'validation': valid}
    result.update({name: pd.read_csv(EXP / f'{name}_predictions.csv', parse_dates=['date', 'target_date'])
                   for name in read(EXP / 'test_results.json')['cohorts']})
    return result


def bootstrap(frame, name, baseline):
    err = frame.assign(ma=(frame[name]-frame.actual).abs(), ba=(frame[baseline]-frame.actual).abs(),
                       ms=(frame[name]-frame.actual)**2, bs=(frame[baseline]-frame.actual)**2)
    totals = err.groupby('district_id').agg(n=('actual', 'size'), ma=('ma','sum'), ba=('ba','sum'),
                                          ms=('ms','sum'), bs=('bs','sum')).to_numpy()
    chosen = np.random.default_rng(42).integers(0, len(totals), size=(2000, len(totals)))
    sums = totals[chosen].sum(axis=1)
    return {key: np.quantile(value, [.025, .975]).tolist() for key, value in {
        'mae_difference_m': (sums[:,1]-sums[:,2])/sums[:,0],
        'rmse_difference_m': np.sqrt(sums[:,3]/sums[:,0])-np.sqrt(sums[:,4]/sums[:,0])}.items()}


def analyze():
    all_frames = frames()
    pooled, distributions, groups, influence, cohorts, intervals = [], [], [], [], {}, {}
    stored = read(EXP / 'test_results.json')['cohorts']
    stored['validation'] = read(EXP / 'validation_summary.json')
    for cohort, frame in all_frames.items():
        assert frame.case_id.is_unique
        assert np.isfinite(frame[['actual', *NAMES]].to_numpy(float)).all()
        assert (frame.target_date == frame.date + pd.DateOffset(months=6)).all()
        cohorts[cohort] = {
            'cases': len(frame), 'districts': frame.district_id.nunique(),
            'distinct_origins': frame.date.nunique(), 'distinct_target_months': frame.target_date.nunique(),
            'origin_start': str(frame.date.min().date()), 'origin_end': str(frame.date.max().date()),
            'target_start': str(frame.target_date.min().date()), 'target_end': str(frame.target_date.max().date()),
            'target_year_counts': {str(k):int(v) for k,v in frame.target_date.dt.year.value_counts().sort_index().items()},
            'target_calendar_month_counts': {str(k):int(v) for k,v in frame.target_date.dt.month.value_counts().sort_index().items()}}
        for name in NAMES:
            result = metrics(frame, name)
            for key, value in result.items():
                expected = stored[cohort]['models'][name][key]
                assert value == expected if value is None else np.isclose(value, expected, rtol=1e-10, atol=1e-10)
            pooled.append({'cohort': cohort, 'model': name, **result})
            errors = frame[name] - frame.actual
            distributions.append({'cohort':cohort, 'model':name, 'bias_m':float(errors.mean()),
                **{f'absolute_error_{label}_m':float(errors.abs().quantile(q)) for label,q in
                   [('median',.5), ('p90',.9), ('p95',.95), ('max',1.)]},
                'cases_over_5m':int(errors.abs().gt(5).sum())})
            for group_type, series in [('district',frame.district_id), ('target_calendar_month',frame.target_date.dt.month),
                                       ('target_year',frame.target_date.dt.year)]:
                for key, part in frame.groupby(series):
                    groups.append({'cohort':cohort, 'model':name, 'group_type':group_type,
                                   'group':str(key), **metrics(part, name)})
        intervals[cohort] = {}
        for name in NAMES[2:]:
            intervals[cohort][name] = {}
            for baseline in NAMES[:2]:
                actual_ci = bootstrap(frame, name, baseline)
                saved_ci = stored[cohort]['paired_district_bootstrap'][name][baseline]['interval_95_percentile']
                for key in actual_ci:
                    np.testing.assert_allclose(actual_ci[key], saved_ci[key], atol=1e-10, rtol=1e-10)
                intervals[cohort][name][baseline] = actual_ci
        if cohort == 'primary_observed_origin':
            for district in sorted(frame.district_id.unique()):
                part = frame.loc[frame.district_id.ne(district)]
                for name in NAMES:
                    influence.append({'excluded_district':district, 'model':name, **metrics(part,name),
                                      'purpose':'Sensitivity only; all original cases retained in reported evaluation.'})
    csv('pooled_metrics.csv', pd.DataFrame(pooled))
    csv('error_distributions.csv', pd.DataFrame(distributions))
    csv('group_metrics.csv', pd.DataFrame(groups))
    csv('primary_leave_one_district_out.csv', pd.DataFrame(influence))
    write('validation_reproduction.json', {'cohorts':cohorts, 'bootstrap_intervals':intervals,
        'saved_pooled_metrics_and_bootstrap_intervals_reproduced':True,
        'training_executed':False, 'model_selection_changed':False})
    freshness()


def freshness():
    feature = pd.read_csv(ROOT / 'data/processed/features_matrix.csv', parse_dates=['date'])
    wide = pd.read_csv(ROOT / 'data/processed/preprocessed_wide.csv', parse_dates=['date'])
    observed = feature.is_observed.astype(str).str.lower().isin(['true','1']) & np.isfinite(feature.GWL_current)
    imputed = feature.is_imputed.astype(str).str.lower().isin(['true','1'])
    last = feature.loc[observed].sort_values('date').groupby('district_id').tail(1).set_index('district_id')
    cross = pd.read_csv(ROOT / 'data_ingestion/district_crosswalk.csv', dtype=str)
    district = cross.drop_duplicates('canonical_district_id').set_index('canonical_district_id')
    district = district[['canonical_name','canonical_state']].reindex(sorted(feature.district_id.unique()))
    district.index.name = 'district_id'
    district['last_source_backed_observation_month'] = last.date
    district['depth_m_bgl_repository_convention'] = last.GWL_current
    district['source_backed_month_count'] = feature.loc[observed].groupby('district_id').size()
    district['source_backed_month_count'] = district.source_backed_month_count.fillna(0).astype(int)
    district['feature_grid_end'] = feature.date.max()
    district['certified_fresh_acquisition_at'] = None
    district['provider_first_publication_at'] = None
    raw = pd.read_csv(ROOT/'data/raw/cgwb_combined.csv', usecols=['district_code','date','currentlevel'], dtype=str)
    raw['date'] = pd.to_datetime(raw.date, errors='coerce')
    raw['value'] = pd.to_numeric(raw.currentlevel, errors='coerce')
    mapping = cross.set_index('legacy_district_id').canonical_district_id.to_dict()
    raw['district_id'] = raw.district_code.str.strip().map(mapping)
    valid = raw.loc[raw.date.notna() & np.isfinite(raw.value) & raw.district_id.notna()]
    district['legacy_latest_reported_date'] = valid.groupby('district_id').date.max()
    update = pd.read_csv(ROOT/'reports/candidates/groundwater_updates/20261013/canonical_district_month_candidates.csv')
    update = update.set_index('district_id')
    district['january_2026_latest_source_reported_date'] = update.last_observation_date
    district['date_qualification'] = 'Reported source date, not independently certified acquisition; publication/revision unknown.'
    csv('district_observation_freshness.csv', district.reset_index())
    tables = {}
    for name in ['imd_rainfall_district_monthly', 'era5_district_monthly']:
        table = pd.read_csv(ROOT/f'data/processed/{name}.csv')
        dates = pd.to_datetime(dict(year=table.year, month=table.month, day=1))
        numeric = ['rainfall_mm'] if name.startswith('imd') else ['temperature','evapotranspiration']
        tables[name] = {'rows':len(table), 'district_state_pairs':len(table[['district','st_nm']].drop_duplicates()),
            'start_month':str(dates.min().date()), 'last_month':str(dates.max().date()),
            'duplicate_district_months':int(table.duplicated(['district','st_nm','year','month']).sum()),
            'missing_values':table[numeric].isna().sum().astype(int).to_dict(),
            'first_publication_at':None, 'historical_revision_vintages':None}
    write('data_inventory.json', {'feature':{'rows':len(feature),'districts':feature.district_id.nunique(),
        'grid_start':str(feature.date.min().date()),'grid_end':str(feature.date.max().date()),
        'source_backed_groundwater_months':int(observed.sum()), 'imputed_flag_rows':int(imputed.sum()),
        'finite_unobserved_groundwater_months':int((~observed & np.isfinite(feature.GWL_current)).sum()),
        'missing_groundwater_months':int(feature.GWL_current.isna().sum()),
        'duplicate_district_months':int(feature.duplicated(['district_id','date']).sum()),
        'missing_per_column':feature.isna().sum().astype(int).to_dict(),
        'latest_observation_month_counts':district.last_source_backed_observation_month.fillna('NONE').astype(str).value_counts().to_dict(),
        'latest_reported_date_status':'See per-district CSV; not certified fresh acquisition.',
        'observations_by_year':{str(k):int(v) for k,v in feature.loc[observed].date.dt.year.value_counts().sort_index().items()}},
        'wide':{'rows':len(wide),'missing_per_column':wide.isna().sum().astype(int).to_dict()},
        'legacy_cgwb':{'rows':len(raw), 'mapped_finite_dated_rows':len(valid),
            'start_reported_date':str(valid.date.min()),'last_reported_date':str(valid.date.max()),
            'districts':valid.district_id.nunique(), 'invalid_or_unmapped_rows':len(raw)-len(valid),
            'duplicate_district_date_value_rows_not_proven_duplicate_wells':int(valid.duplicated(['district_id','date','value']).sum())},
        'weather':tables, 'units':read(ROOT/'data/processed/feature_manifest.json')['units']})


def verify():
    before = read(HERE / 'baseline_inventory.json')['protected_files']
    missing, changed = [], []
    for name, expected in before.items():
        path = ROOT / name
        if not path.is_file():
            missing.append(name)
        elif sha(path) != expected['sha256']:
            changed.append(name)
    assert not missing and not changed, {'missing':missing, 'changed':changed}
    if not CHECK_ONLY:
        write('preservation_verified.json', {'protected_files_checked':len(before), 'changed':changed,
            'missing':missing,'database_accessed':False,'models_fitted':False,
            'no_existing_file_changes':True,'git_status':git('status','--short','--untracked-files=all')})
    print(f'Preserved {len(before)} existing files; no fitting or database access.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['snapshot','analyze','verify'])
    parser.add_argument('--check-only', action='store_true', help='Verify existing audit outputs without writing.')
    args = parser.parse_args()
    CHECK_ONLY = args.check_only
    if CHECK_ONLY and args.action == 'snapshot':
        parser.error('snapshot is create-only; use verify --check-only')
    globals()[args.action]()
