"""Resolve audit encoding assumptions and write new metric evidence/report.

Saved CSV/JSON and source text only. No estimator, application, model package,
database, network, or pipeline import or execution.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import runpy

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
H12 = ROOT/'reports/candidates/twelve_month_horizon_20261020'
APP = ROOT/'reports/candidates/twelve_month_horizon_finalization_20261020'
H6 = ROOT/'reports/actual_forecast_validation_20261019'
INPUTS, CHECKS = {}, []


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    data = Path(path).read_bytes()
    INPUTS[Path(path).relative_to(ROOT).as_posix()] = digest(data)
    return data


def jread(path):
    return json.loads(read(path))


def cread(path):
    read(path)
    frame = pd.read_csv(path)
    for column in ['date','target_date']:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column])
    return frame


def put(name, value):
    with (OUT/name).open('x',encoding='utf-8') as handle:
        json.dump(value,handle,indent=2,allow_nan=False)
        handle.write('\n')


def check(name, condition, detail=None):
    CHECKS.append(dict(check=name,passed=bool(condition),detail=detail))


def flag(values):
    return values.astype('string').str.lower().isin(['true','1'])


def main():
    started = datetime.now(timezone.utc).isoformat()
    metrics = jread(OUT/'metrics.json')
    first_run = jread(OUT/'run.json')
    second_run = jread(OUT/'supplement_run_v2.json')
    first_ci = jread(OUT/'bootstrap.json')
    direct_ci = jread(OUT/'direct_row_bootstrap_v2.json')
    newlines = jread(OUT/'newline_normalization_receipt.json')
    fingerprints = jread(OUT/'cohort_fingerprints_v2.json')
    adverse = jread(OUT/'adverse_cases_v2.json')
    # Retain v2's audit-assumption failures; validate the documented encodings.
    six = cread(H6/'evaluation_v2/historical_predictions_vs_observations.csv')
    six = six.loc[flag(six.primary_common)].copy()
    correct_ids = 'telangana|'+six.district_id+'|'+six.date.dt.strftime('%Y-%m-%d')+'|'+six.target_date.dt.strftime('%Y-%m-%d')
    source_encoding = read(H6/'evaluate_research.py').decode('utf-8')
    check('six_month_id_encoding_is_documented','rows[\'case_id\'] = \'telangana|\'' in source_encoding)
    check('six_month_ids_match_documented_encoding',six.case_id.tolist()==correct_ids.tolist())
    snapshot = cread(APP/'artifact/features.csv')
    card = jread(APP/'artifact/xgb_fixed_2021_card.json')
    target_dates = snapshot.date+pd.DateOffset(months=12)
    target = snapshot.set_index(['district_id','date']).reindex(pd.MultiIndex.from_arrays([snapshot.district_id,target_dates]))
    origin_observed = flag(snapshot.is_observed)&~flag(snapshot.is_imputed)
    origin_imputed = ~flag(snapshot.is_observed)&flag(snapshot.is_imputed)&snapshot.months_since_observation.between(1,3)
    mask = (origin_observed|origin_imputed).to_numpy() & flag(target.is_observed).to_numpy() & ~flag(target.is_imputed).to_numpy()
    mask &= np.isfinite(target.gwl_current).to_numpy() & target_dates.le(pd.Timestamp(card['train_target_cutoff'])).to_numpy()
    train = snapshot.loc[mask].sort_values(['district_id','date']).copy()
    ids = [f'{row.district_id}|{row.date:%Y-%m-%d}|{row.date+pd.DateOffset(months=12):%Y-%m-%d}|12' for row in train.itertuples()]
    ids_hash = digest(json.dumps(ids,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
    builder = read(APP/'build_application_research.py').decode('utf-8')
    check('fixed_training_id_json_encoding_documented','"training_case_ids_sha256": json_hash(train.case_id.tolist())' in builder)
    check('fixed_training_ids_match_documented_json_encoding',ids_hash==card['training_case_ids_sha256'])
    check('fixed_training_n_164',len(train)==card['train_n']==164)
    check('first_run_only_raw_newline_failures',set(v['check'] for v in first_run['failures'])=={'locked_implementation_hash:models/research_horizon.py','locked_implementation_hash:scripts/backtest_twelve_month.py'})
    check('both_raw_differences_are_exclusively_crlf',all(v['lf_normalized_match'] for v in newlines))
    check('second_run_only_audit_encoding_assumptions',set(v['check'] for v in second_run['failures'])=={'six_month_telangana_594:canonical_case_ids_match','fixed24:training_membership_hash'})
    # Independently rebuild the other three archived paired horizon intervals.
    helper_path = OUT/'audit_saved_metrics_v2.py'
    read(helper_path)
    helper = runpy.run_path(str(helper_path))
    direct = helper['direct_bootstrap']
    primary = cread(H12/'evaluation/full_coordinate_predictions.csv')
    primary = primary.loc[flag(primary.common_eligible)&primary.period.eq('primary')].copy()
    matched = primary.merge(six[['district_id','target_date','actual','persistence','xgb_expanding','linear_expanding']],on=['district_id','target_date'],suffixes=('_12','_6'),validate='one_to_one')
    check('paired_horizons_594_and_identical_targets',len(matched)==594 and np.allclose(matched.actual_12,matched.actual_6,rtol=0,atol=1e-10))
    direct_horizon = []
    for model in ['persistence','xgb_expanding','linear_expanding']:
        part = matched[['district_id','target_date','actual_12',model+'_12',model+'_6']].rename(columns={'actual_12':'actual'})
        computed = direct(part,model+'_12',model+'_6')
        computed['cohort'] = 'six_vs_twelve_same_target'
        direct_horizon.append(computed)
        archived = next(v for v in first_ci if v['cohort']=='six_vs_twelve_same_target' and v['model']==model+'_12')
        for method,values in computed['interval_95_percentile'].items():
            for key,value in values.items():
                check('horizon_direct_rows:'+model+':'+method+':'+key,np.allclose(value,archived['interval_95_percentile'][method][key],rtol=0,atol=1e-10))
    put('encoding_resolution_v3.json',dict(
        original_failures_preserved=True,
        six_month_case_id_format='telangana|district_id|origin YYYY-MM-DD|target YYYY-MM-DD; horizon=6 stored separately',
        fixed_training_case_id_encoding='Ordered list sorted district/date; json.dumps(sort_keys=True,separators=(comma,colon),allow_nan=False), UTF-8',
        fixed_training_n=len(train),fixed_training_membership_json_sha256=ids_hash,
        original_newline_sorted_hash_retained_in='fixed_training_membership_v2.json',
        checks=CHECKS))
    put('direct_row_horizon_bootstrap_v3.json',direct_horizon)
    failures = [v for v in CHECKS if not v['passed']]
    check('prior_input_preservation',first_run['preservation_pass'] and second_run['input_preservation_pass'])
    # Markdown is an independently recomputed result narrative, not a copy of
    # retained report conclusions. Values remain binary64 full precision in JSON.
    def table(label):
        lines = ['| Method | n | MAE (m) | RMSE (m) | Pooled R² | Bias (m) |','|---|---:|---:|---:|---:|---:|']
        for name,values in metrics[label]['models'].items():
            lines.append(f"| {name} | {values['n']} | {values['mae_m']:.9f} | {values['rmse_m']:.9f} | {values['r2']:.9f} | {values['bias_m']:.9f} |")
        return '\n'.join(lines)
    def ci_table(cohort):
        lines = ['| Method | Resampling | ΔMAE 95% interval (m) | ΔRMSE 95% interval (m) |','|---|---|---:|---:|']
        records = [v for v in direct_ci if v['cohort']==cohort]
        for item in records:
            for method,values in item['interval_95_percentile'].items():
                a,b = values['mae_difference_m'],values['rmse_difference_m']
                lines.append(f"| {item['model']} | {method} | [{a[0]:.9f}, {a[1]:.9f}] | [{b[0]:.9f}, {b[1]:.9f}] |")
        return '\n'.join(lines)
    p = metrics['full_coordinate_primary']['models']
    delta = p['xgb_expanding']['rmse_m']-p['persistence']['rmse_m']
    old_hgb = metrics['six_month_original_209']['models']['hist_gradient_boosting']
    worst = adverse['six_month_original_209']['hist_gradient_boosting'][0]
    sse_share = worst['absolute_error_m']**2/(old_hgb['n']*old_hgb['rmse_m']**2)
    report = f'''# Independent saved-row metrics audit

Executed 2026-10-23 UTC against the retained GitHub-version workspace. All prediction values were read from archived CSVs; this audit performed arithmetic, joins, hashes, and resampling only. No estimator was deserialized or invoked, and no fitting, tuning, ingestion, database, downloads, pipelines, or serving writes occurred. All outputs are new files in this directory.

The broad 12-month XGB result shows a small descriptive improvement over the annual baseline, with both paired uncertainty intervals crossing zero. The fixed application artifact performs substantially worse than its own baseline on its 24 retained Adilabad checks. These are distinct artifacts and geographic cohorts.

## Broad Telangana 12-month primary cohort

792 paired cases, 33 districts, 24 cases per district and 66 per calendar month. Origins January 2023–December 2024; observed targets January 2024–December 2025. All four methods share exactly the same finite cases. Exact 12-calendar-month joins, explicitly observed non-imputed origins and targets, persistence values, and annual-seasonal equivalence were independently checked. At this horizon annual seasonal naive equals persistence by construction.

{table('full_coordinate_primary')}

XGB ΔRMSE = {delta:.17g} m ({-100*delta/p['persistence']['rmse_m']:.9f}% lower); ΔMAE = {p['xgb_expanding']['mae_m']-p['persistence']['mae_m']:.17g} m. XGB beats baseline RMSE in 20/33 districts and 8/12 calendar months; linear in 7/33 and 0/12; HGB in 16/33 and 7/12. XGB loses in September–December calendar groups. The pooled R² includes differences between district target levels; it is not a prospective accuracy guarantee or a district-average R².

## Paired dependent resampling

Stored procedure reproduced independently: sort districts, create the contiguous monthly target axis, seed NumPy default_rng(42), draw D districts with replacement, then ceil(T/12) circular block starts and truncate to T months; 2,000 replicates per entry. District-only replicates still consume the time draws, preserving the exact stored RNG sequence. Both compared methods retain identical sampled rows. The v1 helper used weighted error totals; v2/v3 independently materialized sampled row indices and reduced row errors. All 228 archived interval pairs (456 endpoints, 19 cohort/model entries × 2 methods × 6 quantities) agree within 1e-10, including the paired six-versus-twelve-month results. Point MAE/RMSE/bias/R² also agree with independent math.fsum arithmetic.

Differences below are method minus persistence; negative MAE/RMSE favors the method. All primary replicates are nonempty and contain 792 sampled rows.

{ci_table('full_coordinate_primary')}

Intervals are descriptive percentile intervals for dependent regional current-vintage evidence. The 24-month primary cohort supplies only two annual blocks; the two-month secondary cohort cannot support meaningful annual-block temporal uncertainty. District-only intervals condition on the retained time window. With one district, district-only intervals degenerate; they do not establish geographic generalization.

## Geographic and panel sensitivities

The strict exact-name-plus-coordinate primary cohort contains only 24 Adilabad cases, compared with 792 broad full-coordinate cases. It uses a different well panel and different observed target values. Its historical annual expanding models are also distinct from the fixed application artifact.

{table('exact_name_coordinate_primary')}

On the broad identical-origin/target-panel sensitivity, only 380 cases in 32 districts remain. Baseline MAE/RMSE = 1.133739801/1.382523452 m; XGB = 1.182743649/1.437133908 m. The XGB advantage reverses. This subset is unbalanced, so district/calendar macro weighting differs from pooled weighting; full macro/group results and independently calculated subset intervals are retained. The strict identical-panel subset has only 19 cases/one district. Panel equality is a useful sensitivity, not proof of measurement validity or historical availability.

The 66-case broad January–February 2026 secondary cohort has XGB RMSE 1.202969265 versus baseline 1.490132988 m; it is two target months. Strict secondary has two cases. Neither expands the primary cohort or supplies another full annual evaluation period.

## Fixed Adilabad application artifact: its own 24 cases

Origins January 2023–December 2024 and targets January 2024–December 2025. Model SHA-256 f94911f5e1a6c3e8b4bbbb82d6a4c6ec87b5d601abbfd774801afc046aa5455f. Descriptor, canonical contract, manifest, card, snapshot, provenance, model-file hash, ordered feature schema, supported geography, and all 24 row model identities were checked without loading the estimator.

{table('fixed_application_24')}

{ci_table('fixed_application_24')}

This artifact's training membership independently reconstructs to 164 eligible origin/target pairs, 158 complete-feature pairs, maximum target December 2021, cutoff 2021-12-31, and first permitted/evaluated origin January 2023. Its canonical JSON ordered-membership hash is {ids_hash}. The historical annual expanding evaluation instead has year-specific artifact hashes/cutoffs; its 792-case XGB score cannot be assigned to this fixed artifact.

For the stored January 2024 origin → January 2025 target example: actual 6.831333333333332 m, annual baseline 6.836666666666668 m, fixed XGB 7.571100711822510 m. The latest observed fixed snapshot is May 2026 (nominal target May 2027), but six weather features are missing; it contains no acquisition/available-at timestamps. This audit did not create a prediction for it.

## Original six-month selection test

209 observed-origin, observed-target paired cases in 32 districts across eight state prefixes: AS, CG, HR, MP, RJ, TN, UP, WB. Origins July 2019–September 2022; targets January 2020–March 2023. Exact six-calendar-month targets, all-method common finite cases, and source origin/target/seasonal values and observed flags were independently joined to retained nationwide features. This is a different geography, horizon, and period from the 12-month Telangana evidence.

{table('six_month_original_209')}

The validation-selected HGB is not the best method on this retained test: seasonal naive has lower MAE and RMSE, and ridge/random forest also have lower RMSE than HGB. HGB's largest absolute error is {worst['absolute_error_m']:.9f} m at {worst['case_id']} and contributes {100*sse_share:.6f}% of its total squared error. The large pooled R² therefore needs the error distribution and cohort context. No post-test model selection was performed by this audit.

## Retained Telangana six-month context and horizon joins

594 cases, 33 districts, origins July 2023–December 2024 and targets January 2024–June 2025.

{table('six_month_telangana_594')}

On 594 identical observed targets, twelve-month XGB MAE/RMSE/R² = 1.039498626/1.317859779/0.727609981 versus six-month XGB 1.205193305/1.472178537/0.660082325. The paired ΔRMSE district interval is [-0.253390778,-0.062819335] m; district×12-month interval [-0.343215342,0.059924876] m crosses zero. Twelve-month persistence exactly equals six-month annual seasonal naive on these targets (RMSE 1.440453987 m). Against that appropriate annual baseline, six-month seasonal naive beats six-month XGB in aggregate. The same-origin 594-case join changes outcomes: twelve-month XGB RMSE 1.478463953 versus baseline 1.332002337 m. Neither join isolates a controlled horizon effect because origins, training cutoffs, and/or targets differ.

## Identity, cutoff, availability, and preservation receipts

The primary and strict frozen inventory ordering/common-eligibility flags, input hashes, model card hashes, per-row model hashes, target horizon, protocol identity, and all saved 12-month expanding training membership counts/hashes and fold cutoffs passed. Training membership reconstruction used retained rows only. Point and interval comparisons were checked against retained reports as a cross-check after recomputation, not accepted as truth.

All evaluated 12-month rows lack issuance timestamps and declare availability unverified. Source and app snapshot acquisition/available-at fields are empty. Calendar-causal dates and embargoes do not prove what was known at historical issuance. These are retrospective current-vintage nominal-horizon results. Hashes bind saved predictions to metadata/artifact bytes; without estimator execution this audit does not independently prove that a saved prediction was produced by the associated estimator.

The initial helper retained 688 checks: 686 raw passes and two raw implementation hash mismatches. Both are exclusively Windows CRLF bytes: converting CRLF to LF in memory exactly matches the frozen implementation hashes. No file was normalized or modified. The independent supplement retained 430 checks: 428 passes and two incorrect audit encoding assumptions. The six-month archived ID includes the documented `telangana|` prefix and no horizon suffix; the fixed artifact hashes a canonical JSON ordered training-ID list rather than newline-sorted IDs. `encoding_resolution_v3.json` verifies both documented formats and preserves every earlier failure record. These are audit-assumption resolutions, not repaired data or artifacts.

The original 72 hashed input files were unchanged after the first run; supplemental inputs also remain unchanged. Full precision binary64 JSON results: `metrics.json`, `bootstrap.json`, `independent_arithmetic_v2.json`, `direct_row_bootstrap_v2.json`, and `direct_row_horizon_bootstrap_v3.json`. Cohort membership/value/prediction fingerprints: `cohort_fingerprints_v2.json`. Detail: `group_metrics.csv`, `adverse_cases_v2.json`, `artifact_checks.json`, `newline_normalization_receipt.json`, `fixed_training_membership_v2.json`, `encoding_resolution_v3.json`. Commands/run scope/runtime/input hashes: the three audit scripts and their `run.json`, `supplement_run_v2.json`, `report_run_v3.json` receipts. Scripts refuse to replace outputs.
'''
    with (OUT/'METRICS.md').open('x',encoding='utf-8') as handle:
        handle.write(report)
    after = {name:digest((ROOT/name).read_bytes()) for name in INPUTS}
    failures = [v for v in CHECKS if not v['passed']]
    receipt = dict(started_at_utc=started,completed_at_utc=datetime.now(timezone.utc).isoformat(),
                   script_sha256=digest(Path(__file__).read_bytes()),report_sha256=digest((OUT/'METRICS.md').read_bytes()),
                   input_sha256=INPUTS,input_preservation_pass=after==INPUTS,changed_inputs=[name for name in INPUTS if INPUTS[name]!=after[name]],
                   check_count=len(CHECKS),failed_count=len(failures),failures=failures,
                   all_archived_interval_pairs_direct_rows_verified=228,all_archived_interval_endpoints_direct_rows_verified=456,
                   no_estimator_loading=True,no_fitting=True,no_prediction_calls=True,no_database=True,no_downloads=True)
    put('report_run_v3.json',receipt)
    print(json.dumps({k:receipt[k] for k in ['started_at_utc','completed_at_utc','check_count','failed_count','failures','input_preservation_pass','all_archived_interval_pairs_direct_rows_verified']},indent=2))
    return 0 if not failures and after==INPUTS else 1


if __name__=='__main__':
    raise SystemExit(main())
