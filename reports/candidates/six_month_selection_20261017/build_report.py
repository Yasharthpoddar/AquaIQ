"""Render saved, frozen results without fitting models or modifying inputs.

Run after validation and test. Refuses to replace any existing report output.
"""
from pathlib import Path
import json
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from models import six_month_selection as run

LABELS = {'persistence': 'Persistence', 'seasonal_naive': 'Seasonal naive',
          'ridge': 'Ridge', 'random_forest': 'Random Forest',
          'xgboost': 'XGBoost', 'hist_gradient_boosting': 'HistGradientBoosting'}
NAMES = [*run.BASELINES, *run.FAMILIES]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |',
                      *['| ' + ' | '.join(map(str, row)) + ' |' for row in rows]])


def fmt(value):
    return 'undefined' if value is None else f'{value:.4f}'


def compare_original(original, reproduced):
    differences = []
    def walk(a, b, path):
        if isinstance(a, dict):
            assert a.keys() == b.keys(), path
            for key in a:
                walk(a[key], b[key], path + '/' + key)
        elif isinstance(a, (int, float)) and not isinstance(a, bool):
            assert np.isclose(a, b, rtol=0, atol=1e-12), (path, a, b)
            differences.append(abs(a-b))
        else:
            assert a == b, (path, a, b)
    for split in ('validation', 'test'):
        # Old district R² could be numerically undefined; reproduce meaningful
        # pooled metrics and case coverage rather than preserve that known bug.
        for field in ('n', 'districts', 'models', 'coverage', 'seasonal_paired_comparison'):
            walk(original['direct_six_month'][split][field],
                 reproduced['direct_six_month'][split][field], split + '/' + field)
    return {'metrics_and_cases_reproduced': True, 'absolute_tolerance': 1e-12,
            'max_numeric_difference': max(differences),
            'note': 'Pooled metrics and case coverage; Random Forest thread accumulation can differ by rounding. Near-constant district R² is now undefined.'}


def main():
    output = HERE / 'experiment_v2'
    lock = read(output/'selection_lock.json')
    final = read(output/'test_results.json')
    plan = read(output/'protocol.json')
    initial = HERE/'experiment'
    if (initial/'selection_lock.json').exists():
        initial_lock = read(initial/'selection_lock.json')
        assert initial_lock['selected_ml'] == lock['selected_ml']
        matching = []
        for item in plan['candidates']:
            name = item['candidate_id']
            old = read(initial/'validation'/f'{name}.json')
            new = read(output/'validation'/f'{name}.json')
            assert old['case_csv_sha256'] == new['case_csv_sha256'], name
            matching.append(name)
        run.write_once(HERE/'metric_fix_validation_invariance.json',
                       {'prediction_csv_hashes_identical':True, 'configurations':len(matching),
                        'selected_ml_identical':True, 'note':'Fresh fits; only undefined district R²/NSE reporting changed.'})
    frames = []
    for family, settings in lock['selected_by_family'].items():
        data = pd.read_csv(output/'validation'/f'{settings["candidate_id"]}.csv')
        frames.append((family, data))
    combined = frames[0][1].drop(columns=['prediction']).copy()
    for family, data in frames:
        assert combined.case_id.tolist() == data.case_id.tolist()
        assert combined.actual.tolist() == data.actual.tolist()
        combined[family] = data.prediction.to_numpy()
    validation = run.summarize_cases(combined, NAMES)
    validation['by_fold'] = {key: run.summarize_cases(part, NAMES)
                             for key, part in combined.groupby('fold', sort=True)}
    validation['paired_district_bootstrap'] = {
        family: {baseline: run.paired_bootstrap(combined, family, baseline)
                 for baseline in run.BASELINES} for family in run.FAMILIES}
    run.write_once(output/'validation_summary.json', validation)
    reproduction = compare_original(read(ROOT/'reports/audit-2026-10-17/model_evaluation.json'),
                                    read(HERE/'reproduction/model_evaluation.json'))
    run.write_once(HERE/'reproduction_check.json', reproduction)
    before = read(output/'protected_inputs.json')
    current = run.protected_snapshot(HERE)
    assert before == current, 'An input or previous report changed across stages'
    run.write_once(HERE/'integrity_check.json', {'unchanged_across_entire_run': True,
                   'protected_files': len(before), 'database_access': False,
                   'models_promoted': False, 'commit_or_push_performed': False})
    cohorts = {'validation': validation, **final['cohorts']}
    rows, districts, periods, horizons, folds = [], [], [], [], []
    for cohort, summary in cohorts.items():
        for name in NAMES:
            values = summary['models'][name]
            baselines = {f'{baseline}_rmse_difference_m': values['rmse_m']-summary['models'][baseline]['rmse_m']
                         for baseline in run.BASELINES}
            rows.append({'cohort': cohort, 'model': name, **values,
                         **summary['district_macro'][name], **baselines})
        for district, item in summary['by_district'].items():
            for name in NAMES:
                districts.append({'cohort': cohort, 'district_id': district, 'model': name, **item['models'][name]})
        for year, item in summary['by_target_year'].items():
            for name in NAMES:
                periods.append({'cohort': cohort, 'target_year': year, 'model': name, **item['models'][name]})
        for horizon, item in summary['by_horizon_months'].items():
            for name in NAMES:
                horizons.append({'cohort': cohort, 'horizon_months': horizon, 'model': name, **item['models'][name]})
    for fold, item in validation['by_fold'].items():
        for name in NAMES:
            folds.append({'fold': fold, 'model': name, **item['models'][name]})
    # Preserve pooled MAE/RMSE separately from equally weighted district metrics.
    for row in rows:
        item = cohorts[row['cohort']]
        row.update({f'district_macro_{metric}': item['district_macro'][row['model']][metric]
                    for metric in ('mae_m', 'rmse_m')})
        row.update(item['models'][row['model']])
    for name, data in [('comparison', rows), ('district_metrics', districts),
                       ('period_metrics', periods), ('horizon_metrics', horizons), ('fold_metrics', folds)]:
        run.csv_once(HERE/f'{name}.csv', pd.DataFrame(data))
    case_frames = {'validation': combined, **{
        key: pd.read_csv(output/f'{key}_predictions.csv') for key in final['cohorts']}}
    calendar_rows = []
    for cohort, data in case_frames.items():
        for month, part in data.groupby(pd.to_datetime(data.target_date).dt.month):
            for name in NAMES:
                calendar_rows.append({'cohort':cohort, 'target_calendar_month':int(month),
                                      'model':name, **run.source.metrics(part.actual, part[name])})
    run.csv_once(HERE/'calendar_metrics.csv',pd.DataFrame(calendar_rows))
    compact = {'selection': lock, 'cohort_sizes': {key: {field: val[field] for field in
               ('n', 'districts', 'origin_start', 'origin_end', 'target_start', 'target_end')}
               for key, val in cohorts.items()}, 'comparison': rows}
    run.write_once(HERE/'comparison_summary.json', compact)
    winner = lock['selected_ml']['family']
    primary = final['cohorts']['primary_observed_origin']
    primary_delta = primary['models'][winner]['rmse_m']-primary['models']['persistence']['rmse_m']
    text = [
        '# AquaIQ six-month model selection — 17 October 2026',
        '',
        f'Validation selected **{LABELS[winner]}** (`{lock["selected_ml"]["candidate_id"]}`) by pooled out-of-fold RMSE. '
        f'Its chronological test RMSE is **{primary["models"][winner]["rmse_m"]:.4f} m**, '
        f'versus persistence **{primary["models"]["persistence"]["rmse_m"]:.4f} m** '
        f'(model minus baseline {primary_delta:+.4f} m).',
        '',
        '**Decision: no confirmed overall ML winner.** Seasonal naive has the lowest primary-test RMSE and MAE '
        'of all six candidates. The validation-selected HistGradientBoosting has a lower primary-test RMSE point estimate '
        'than persistence, but higher MAE, and its paired 95% RMSE-difference interval spans zero '
        '[-1.2343, +0.0377] m. Its superiority over persistence is therefore not established on the primary cohort. '
        'Do not promote it from these results.',
        '',
        'Ridge and Random Forest show exploratory primary-test RMSE improvements over persistence with district-bootstrap '
        'intervals below zero (Ridge [-2.6472, -0.0428] m; RF [-2.3981, -0.0322] m), but higher pooled MAE and no established '
        'MAE advantage. They were not the validation-selected winner; selecting either now would use the final test for '
        'model selection. All ML families lose to seasonal naive on primary RMSE/MAE. Thus the evidence does not support '
        'a blanket claim that every ML model fails to improve any metric, nor does it confirm an ML model as best overall.',
        '',
        'The selected model does improve both errors over persistence in the secondary causal-origin cohort '
        '(RMSE 2.7988 vs 3.4125 m; MAE 1.8367 vs 2.2941 m), with both paired intervals below zero. Seasonal naive still '
        'has lower errors there. It also improves both errors over both baselines in the separate 74-case source benchmark '
        '(RMSE 5.3036 vs persistence 6.1573 m; MAE 2.9535 vs 4.7796 m), with paired intervals below zero. '
        'These are conditional findings, not independent confirmation of general operational superiority.',
        '',
        '**Concentration check.** One Faridabad case supplies 71.5% of persistence squared error and 72.2% of the '
        'selected model’s net squared-error reduction; Faridabad plus Cuddalore supply 91.3% of that reduction. '
        'The Faridabad origin is 65.66 m, target 20.445 m, and HGB prediction 57.7744 m. Its station composition '
        'may differ, but no erroneous observation was established and the case was retained. HGB has worse '
        'absolute error on 147 of 209 cases, while improving 21 of 32 district means; 22 districts contain only '
        'one case. Cuddalore, Tiruppur, Sivaganga and Deoria supply 119 of 209 cases (56.9%) and all 2022–2023 '
        'cases. These competing weighting effects explain why pooled MAE, pooled RMSE and district-macro errors '
        'can point in different directions.',
        '',
        '**This is a retrospective, newly locked selection run.** Final-period labels were excluded from fitting and '
        'hyperparameter selection here, but historical periods were inspected by earlier project audits/training. '
        'The 209-case holdout is untouched within this run, not a pristine prospective blinded trial. '
        'The separate unused-source benchmark has unresolved vertical datum, well composition and publication-lag limitations. '
        'No active model was replaced or promoted.',
        '',
        '**Reproduction before changes.** Saved XGBoost, persistence, seasonal naive, Ridge and Random Forest metrics '
        f'reproduced at absolute tolerance 1e-12; maximum numeric difference {reproduction["max_numeric_difference"]:.3g}. '
        'The old validation contained 108 cases (seasonal 97); its final test contained 10 cases in 4 districts. '
        'Nine of the 10 final targets exactly equal both baseline predictions, so that test cannot establish broad forecasting skill.',
        '',
        '**Common-case comparison.** MAE/RMSE are metres; lower is better. R² is a pooled coefficient of determination, '
        'not prediction accuracy. Within each cohort every model and baseline uses exactly the same district/origin/target cases. '
        'ML rows use the best validation settings for their family; only the validation-selected family is the confirmatory ML candidate.',
        '',
        table(['Model', 'Validation MAE', 'Validation RMSE', 'Validation R²', 'Test MAE', 'Test RMSE', 'Test R²'],
              [[LABELS[name], *[fmt(validation['models'][name][m]) for m in ('mae_m','rmse_m','r2')],
                *[fmt(primary['models'][name][m]) for m in ('mae_m','rmse_m','r2')]] for name in NAMES]),
        '',
        '**Sample sizes and actual date ranges.** Both the primary origins and labels are genuinely observed; '
        'the exact observed seasonal reference is required for every paired evaluation. Training does not require a seasonal reference.',
        '',
        table(['Cohort', 'Cases', 'Districts', 'Origins', 'Target labels'],
              [[key, val['n'], val['districts'], f'{val["origin_start"]} to {val["origin_end"]}',
                f'{val["target_start"]} to {val["target_end"]}'] for key, val in cohorts.items()]),
        '',
        f'Final refit uses {final["training_n"]:,} observed-origin training pairs with labels through '
        f'{final["max_training_target"]}. All horizons are exactly six calendar months. '
        'No intermediate 1–5 month skill is implied; `horizon_metrics.csv` explicitly records horizon 6.',
        '',
        table(['Validation fold', 'Training label cutoff', 'First allowed origin', 'Cases', 'Actual targets'],
              [[spec['fold'], spec['train_target_cutoff'], spec['evaluation_origin_start'],
                validation['by_fold'][spec['fold']]['n'],
                validation['by_fold'][spec['fold']]['target_start']+' to '+validation['by_fold'][spec['fold']]['target_end']]
               for spec in plan['validation_folds']]),
        '',
        '**Protocol.** Four expanding training windows use evaluation target years 2010, 2013, 2016, 2018. '
        'Six full calendar months separate the training label cutoff from the first allowed evaluation origin. '
        'Final training labels stop 2018-12-31; final origins begin 2019-07-01 and targets begin 2020-01-01. '
        'The final period was fixed by label coverage before tuning, and validation physically removes all post-2018 rows '
        'before constructing labels. Per-family hyperparameters and absolute-depth versus depth-change targets were selected '
        'from 24 fixed configurations (96 fold fits), using pooled validation RMSE. The immutable selection lock was saved '
        'before any final predictions. There is no test-driven retuning.',
        '',
        'Ridge uses training-only median imputation, missing indicators and scaling; Random Forest uses training-only '
        'median imputation and indicators. XGBoost and HistGradientBoosting handle missing features natively. '
        'HistGradientBoosting is justified by installed scikit-learn and this tabular dataset; no dependency was added. '
        'Its internal random early-stopping split is disabled. All families share the same inputs and training cases. '
        'Origin-month sine/cosine is deterministic at issuance; no target-month weather is supplied. '
        'Canonical rainfall normals use previous years only; lags use exact calendar joins; targets are never filled. '
        'All ML predictions are truncated at 0 under the policy frozen before validation.',
        '',
        '**Locked ML settings.**',
        '',
        table(['Family', 'Candidate', 'Target form', 'Parameters'],
              [[LABELS[family], item['candidate_id'], item['target_form'], '`'+json.dumps(item['parameters'],sort_keys=True)+'`']
               for family,item in lock['selected_by_family'].items()]),
        '',
        '**Primary test by target year.** All six models are also available in `period_metrics.csv`.',
        '',
        table(['Year', 'Cases', 'Selected ML MAE', 'Selected ML RMSE', 'Persistence RMSE', 'Seasonal RMSE'],
              [[year, item['n'], fmt(item['models'][winner]['mae_m']), fmt(item['models'][winner]['rmse_m']),
                fmt(item['models']['persistence']['rmse_m']), fmt(item['models']['seasonal_naive']['rmse_m'])]
               for year,item in primary['by_target_year'].items()]),
        '',
        '**District performance.** `district_metrics.csv` and the saved JSON give every district/model/cohort, '
        'including sample size, MAE, RMSE and R². R² is null for one-case or constant-target groups. '
        'Equally weighted district metrics reduce domination by districts with more measurements; they do not establish spatial independence.',
        '',
        table(['Model', 'Primary district macro MAE', 'Primary district macro RMSE'],
              [[LABELS[name], fmt(primary['district_macro'][name]['mae_m']),
                fmt(primary['district_macro'][name]['rmse_m'])] for name in NAMES]),
        '',
        '**Paired uncertainty for the selected ML model.** Negative differences favor ML. '
        'Intervals use 2000 paired district-block bootstrap resamples, seed 42, retaining complete district histories. '
        'They are descriptive and do not resolve spatial dependence, few time periods, prior historical exposure or source changes.',
        '',
        table(['Cohort', 'Baseline', '95% MAE difference interval (m)', '95% RMSE difference interval (m)'],
              [[key, LABELS[baseline],
                ', '.join(fmt(x) for x in val['paired_district_bootstrap'][winner][baseline]['interval_95_percentile']['mae_difference_m']),
                ', '.join(fmt(x) for x in val['paired_district_bootstrap'][winner][baseline]['interval_95_percentile']['rmse_difference_m'])]
               for key,val in final['cohorts'].items() for baseline in run.BASELINES]),
        '',
        '**Additional cohorts.** The secondary cohort permits only causal groundwater fills of up to 3 months '
        'at the forecast origin, still requiring observed targets and exact observed seasonal references. '
        'It is a sensitivity analysis, not extra independent evidence: the primary cases are a subset. '
        'The same observed-origin training pairs and frozen models are used.',
        '',
        table(['Model', 'Secondary MAE', 'Secondary RMSE', 'Secondary R²', 'Conditional source MAE', 'Conditional source RMSE', 'Conditional source R²'],
              [[LABELS[name], *[fmt(final['cohorts']['secondary_causal_origin']['models'][name][m]) for m in ('mae_m','rmse_m','r2')],
                *[fmt(final['cohorts']['external_source_conditional']['models'][name][m]) for m in ('mae_m','rmse_m','r2')]] for name in NAMES]),
        '',
        'The separate Gujarat source contributes 74 previously unused target district-months across 34 districts '
        '(6 in May 2022, 34 in November 2022, 34 in May 2023). None was used for fitting or selection. '
        'Source dates were parsed explicitly day-first and rows spatially audited: 6244 accepted, 460 excluded. '
        'Its header establishes metres but does not explicitly establish below-ground datum; no original transport manifest '
        'or successful current byte verification is available. Of 26 overlapping active observed months, 25 have different '
        'means, consistent with differing station composition. It therefore stays separate from active district means and '
        'cannot certify a general m_bgl improvement. All 74 origin/target pairs share at least one station-location proxy; '
        'stable well identifiers are absent. See `coverage/source_manual_optional_audit.json` for exclusions and source hashes. '
        'The [official NWDP resource](https://nwdp.nwic.gov.in/dataset/gwl-manual-quarterly-central-ground-water-board-department/resource/ef17ded9-be74-48e6-9359-f3a19daeea4a) '
        'is linked for provenance; the local CSV actually ends August 2023 despite its 2021–2025 filename.',
        '',
        '**Why the old test has 10 cases.** There are only 11 active observed labels in 2023, of which one lacks '
        'a finite groundwater origin six months earlier. The 639 January 2026 observations lack usable July 2025 groundwater '
        'origins; 2024–2025 have no active observed labels. The unadopted January 2025 candidate likewise lacks '
        'July 2024 origins. Filling targets or extending groundwater carries would fabricate evaluation coverage. '
        'Moving the new final cutoff earlier expands legitimate historical evidence to 209 strict cases and 962 causal-origin cases, '
        'but cannot create a fresh prospective test. Label coverage was inspected without scoring the new test.',
        '',
        '**Changes and protections.** Added `models/six_month_selection.py`, '
        '`tests/test_six_month_selection.py`, this candidate directory and scoped `.gitignore` patterns for large artifacts. '
        'Fixed the confirmed ambiguous native `Data Acquisition Time` parser in `scripts/audit_data_quality.py` '
        'and added its regression in `tests/test_audit_data_quality.py`. '
        'Fixed `models/xgboost_model.py` to return undefined R²/NSE for targets constant within floating-point resolution, '
        'with `tests/test_forecast_metric_precision.py`. This prevents misleading enormous negative district scores; MAE/RMSE are unchanged. '
        'The initial validation-only run is preserved in `experiment/`; the corrected protocol was rerun from scratch '
        'in `experiment_v2/` before any test scoring. These changes affect audit date/metric interpretation; '
        'they do not regenerate active features or previous reports. No other feature bug was confirmed in the verified causal generation. '
        f'Checksums confirm all {len(before)} protected processed/checkpoint/config/source/report files stayed unchanged '
        'through both stages. No database access, active checkpoint replacement, promotion, commit or push occurred.',
        '',
        '**Remaining limits.** The test covers 32 districts and sparse measurement months, with only 10 cases in 2023 '
        'and none later. Validation spans 514 districts; the final geographic/seasonal distribution differs substantially. '
        f'{int(combined.target_date.pipe(pd.to_datetime).dt.month.isin([5,11]).sum())} of {len(combined)} validation '
        'cases target May or November. `calendar_metrics.csv` reports every calendar month separately; sparse other months '
        'cannot establish general year-round skill. '
        'District aggregates can change because the set of measured wells changes. There are no operational '
        'publication/revision timestamps proving every origin feature was available in real time. '
        'A prospective test on new observed labels and stable well panels is needed before deployment claims. '
        'A high pooled R² can reflect between-district depth differences even when persistence is stronger.',
        '',
        '**Reproduce.** Run the PowerShell commands in `REPRODUCE.ps1` from the repository root. '
        'They create a new sibling candidate directory and refuse to reuse the saved result paths. '
        'Validation and test are separate commands. Coverage helpers operate on local copies; the optional '
        'network byte verification can remain unavailable without changing source features. '
        'The report renderer itself reads only saved predictions/metrics and does not fit or retune models.',
        '',
    ]
    xml = HERE/'pytest-final-results.xml'
    if xml.exists():
        suites = ET.parse(xml).getroot()
        children = list(suites) if suites.tag == 'testsuites' else [suites]
        totals = {key: sum(int(child.get(key,0)) for child in children)
                  for key in ('tests','failures','errors','skipped')}
        totals['passed'] = totals['tests']-totals['failures']-totals['errors']-totals['skipped']
        text += [f'**Tests.** Full local suite without database integration: {totals["passed"]} passed, '
                 f'{totals["skipped"]} skipped, {totals["failures"]} failed, {totals["errors"]} errors. '
                 'See `pytest-final-results.xml`. Targeted selection regressions cover exact calendar labels, '
                 'observed provenance, causal-origin separation, embargo, future-row invariance, training-only '
                 'preprocessing, deterministic paired identities, finite predictions, undefined R² and protected output paths.', '']
    with (HERE/'REPORT.md').open('x',encoding='utf-8') as handle:
        handle.write('\n'.join(text))
    print(json.dumps(compact,indent=2,allow_nan=False))


if __name__ == '__main__':
    main()
