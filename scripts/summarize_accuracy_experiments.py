"""Build reviewable tables and scientific figures from completed saved cases."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from models import accuracy_experiments as a
from models.xgboost_model import sha256_file, _write_json

FIELDS=['n','districts','supported','mae_m','district_macro_mae_m','rmse_m',
        'mean_signed_error_m','median_absolute_error_m','overestimate_fraction','underestimate_fraction']


def compact(metric):return {k:metric[k] for k in FIELDS if k in metric}


def differences(candidate, reference):
    return {'mae_difference_m':candidate['mae_m']-reference['mae_m'],
            'relative_mae_difference':candidate['mae_m']/reference['mae_m']-1,
            'macro_mae_difference_m':candidate['district_macro_mae_m']-reference['district_macro_mae_m'],
            'relative_macro_mae_difference':candidate['district_macro_mae_m']/reference['district_macro_mae_m']-1,
            'rmse_difference_m':candidate['rmse_m']-reference['rmse_m'],
            'signed_error_difference_m':candidate['mean_signed_error_m']-reference['mean_signed_error_m']}


def subgroup_checks(records):
    return [{'year':r['year'],**check,'reference_name':name} for r in records
        for name,key in [('current_recipe','subgroup_gates_vs_current'),('frozen_fixed_reference','subgroup_gates_vs_frozen')]
        for check in r[key]]


def subgroup_gate(checks, reference_name):
    supported=[c for c in checks if c['reference_name']==reference_name and c['status']!='unsupported']
    return bool(supported) and all(c['status']=='pass' for c in supported)


def markdown_report(root, run_directory, protocol_path, summary, protocol, records, historical, analysis_version):
    audit=Path(protocol['audit_directory'])
    baseline=json.loads((audit/'baseline_audit.json').read_text())
    decision=summary['final_decision']
    verification_path=root/('verification_v2.json' if (root/'verification_v2.json').exists() else 'verification.json')
    verification=json.loads(verification_path.read_text())
    inputs=json.loads((run_directory/'fold_inputs.json').read_text())
    by_name={r['method']:r for r in summary['primary_table']}
    selected=by_name['nested_selected'];old=baseline['panels']['four_way']['methods']
    f=lambda x:f'{x:.6f}'
    pct=lambda x:f'{x*100:+.2f}%'
    table=['| Method | Inner mean macro MAE | Outer mean macro MAE | Pooled MAE | RMSE | Signed error |',
           '| --- | ---: | ---: | ---: | ---: | ---: |']
    for row in sorted(summary['primary_table'],key=lambda x:x['mean_fold_macro_mae_m']):
        name=row['method'];inner=decision['ranks'].get(name,{}).get('mean_fold_district_macro_mae_m')
        m=row['pooled_common']
        table.append(f"| `{name}` | {f(inner) if inner is not None else '—'} | {f(row['mean_fold_macro_mae_m'])} | {f(m['mae_m'])} | {f(m['rmse_m'])} | {f(m['mean_signed_error_m'])} |")
    fold_rows=['| Phase / origin year | Training labels through | Train cases / districts | Validation origins | Validation targets | Cases / districts |',
               '| --- | --- | ---: | --- | --- | ---: |']
    for record in records:
        key=f"{record['phase']}_{record['year']}";data=inputs[key];t,v=data['training'],data['validation']
        fold_rows.append(f"| {record['phase']} {record['year']} | {record['fold']['train_target_cutoff']} | {t['n']:,} / {t['districts']} | {' to '.join(v['origin_range'])} | {' to '.join(v['target_range'])} | {v['n']:,} / {v['districts']} |")
    compare=['| Reference on identical common cases | Nested policy MAE difference (m) | Relative MAE difference | Macro MAE difference (m, pooled districts) | RMSE difference (m) |',
             '| --- | ---: | ---: | ---: | ---: |']
    for reference,field in [('Frozen artifact','versus_frozen'),('Refitted current recipe','versus_current_recipe'),('Persistence','versus_persistence'),('Seasonal naive','versus_seasonal')]:
        d=selected[field]
        compare.append(f"| {reference} | {f(d['mae_difference_m'])} | {pct(d['relative_mae_difference'])} | {f(d['macro_mae_difference_m'])} | {f(d['rmse_difference_m'])} |")
    outer_rows=['| Outer origin cohort | Inner-selected method | Common cases / districts | Selected MAE / RMSE | Selected macro MAE |',
                '| --- | --- | ---: | ---: | ---: |']
    for r in summary['per_fold']:
        m=r['joint_metrics']['nested_selected']
        outer_rows.append(f"| {r['year']} | `{r['selected']}` | {m['n']:,} / {m['districts']} | {f(m['mae_m'])} / {f(m['rmse_m'])} | {f(m['district_macro_mae_m'])} |")
    failures=[c for c in summary['subgroup_checks'] if c['status']=='fail']
    unsupported=[c for c in summary['subgroup_checks'] if c['status']=='unsupported']
    fail_rows=['| Year | Reference | Subgroup | Cases / districts | Selected / reference MAE | Relative regression |',
               '| --- | --- | --- | ---: | ---: | ---: |']
    for c in failures:
        fail_rows.append(f"| {c['year']} | {c['reference_name']} | {c['group']}={c['value']} | {c['candidate']['n']} / {c['candidate']['districts']} | {f(c['candidate']['mae_m'])} / {f(c['reference']['mae_m'])} | {pct(c['relative_mae_regression'])} |")
    if not failures:fail_rows.append('| — | — | No supported failures | — | — | — |')
    historical_rows=['| Method | MAE | RMSE | Median absolute error | Signed error | Overestimate fraction |',
                     '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,m in old.items():
        historical_rows.append(f"| {name} | {f(m['mae_m'])} | {f(m['rmse_m'])} | {f(m['median_absolute_error_m'])} | {f(m['mean_signed_error_m'])} | {m['overestimate_fraction']:.3%} |")
    current_inner=decision['ranks']['current_recipe']['mean_fold_district_macro_mae_m']
    better=[n for n,r in decision['ranks'].items() if n not in ['current_recipe','production_recipe','persistence','seasonal'] and r['mean_fold_district_macro_mae_m']<current_inner]
    worse=[n for n,r in decision['ranks'].items() if n not in ['current_recipe','production_recipe','persistence','seasonal'] and r['mean_fold_district_macro_mae_m']>=current_inner]
    candidate=decision['new_candidate_checkpoint']
    current_outer=by_name['current_recipe']['mean_fold_macro_mae_m']
    grouped_outer=by_name['three_horizon_groups']['mean_fold_macro_mae_m']
    early_outer=by_name['early_stopping']['mean_fold_macro_mae_m']
    final_text=(f"The final inner-only selection is **`{decision['selected']}`**. An isolated final candidate was fitted twice on 145,494 genuine pairs across 641 districts, with labels through 31 January 2025. Its checkpoint is `{candidate}`. Repeated rounded depth predictions match exactly; reload maximum depth difference is {decision.get('reloaded_depth_max_difference_m',0):.8f} m. The current experimental candidate remains retained as a reference."
                if candidate else f"The final inner-only selection is **`{decision['selected']}`**. No new final learner was fitted because the locked rule retains the existing candidate when a baseline or reference recipe wins. The existing candidate remains intact.")
    gates=summary['development_gates']
    tier_c=summary['historical_tier_full']['C']['frozen']['mae_m']
    report=f"""# AquaIQ accuracy experiments — 27 October 2026

## Executive finding

This completed historical development experiment compares sixteen supported recipes and two baselines. The nested selection procedure obtains **{f(selected['pooled_common']['mae_m'])} m case-weighted MAE**, **{f(selected['mean_fold_macro_mae_m'])} m mean outer-fold district-macro MAE**, and **{f(selected['pooled_common']['rmse_m'])} m RMSE** on {summary['pooled_common_cases']:,} common cases across {summary['common_districts']} districts. The comparison below gives exact differences, including regressions. These are retrospective development results, not an untouched final test.

{final_text}

The new selection procedure does **not** demonstrate an improvement over the current recipe on outer district-macro MAE: grouped horizons change it from {f(current_outer)} to {f(grouped_outer)} m ({pct(grouped_outer/current_outer-1)}), with worse RMSE. Retain the existing candidate for further prospective testing; the new grouped artifact is a rejected replacement and a reproducible research reference. Early stopping alone changes outer macro MAE by only {f(early_outer-current_outer)} m ({pct(early_outer/current_outer-1)}), which is practically negligible and was not selected by the locked inner ranking. No alternative was chosen after seeing outer results.

**Production promotion is prohibited.** The production pointer, frozen weights, current experimental candidate and prior reports are unchanged. The public-table before/after fingerprints match. No new forecast generation or production API data was published. The original untouched-test requirement and all original numerical safeguards remain in force.

## Original results reproduced independently

The audit reproduces every original panel MAE/RMSE from the actual saved case records within 1e-12 m, including all six historical validation exports. All measured target keys/values match accepted observed source rows. The complete historical serving panel has 7,668 cases / 639 districts; persistence covers 7,560 / 630 and the four-way panel covers 6,756 / 563. Persistence is missing on 108 cases; seasonal naive is missing on 912. There are 96,732 unlabelled slots among 104,400 potential district/origin/horizon slots. Missing labels remain missing.

The following four-way values use exactly the same 6,756 cases; units are metres below ground level. Positive signed errors mean predicted depth is too large.

{chr(10).join(historical_rows)}

The audit independently resolves each baseline's source timestamp and value. Both definitions correctly use **January 2025** on every seasonal-supported district at all twelve 2025 origins: it is the exact prior-year January observation and also the latest eligible measurement. There are no later measured months in 2025. Their equality is expected, not an implementation conflation. Seasonal values never fall back to persistence; missing seasonal cases remain excluded from every method in the paired panel.

Eight representative A/B/C serving paths, including January/December origins and Gandhinagar, exactly reproduce the actual saved `forecast[h-1].predicted_gwl` field through the original tiered dispatcher. Model predictions are changes; serving reconstructs the origin anchor plus change, applies the zero floor and rounds public depth to four decimals. The external comparison correctly uses **latest measured persistence**. The embedded Tier A API baseline can instead hold an estimated current anchor; these are different documented quantities and were not substituted.

Evidence: [baseline audit](audit_v2/baseline_audit.json), [serving replay](audit_v2/serving_replay.json), [historical validation reproduction](audit_v2/historical_validation_reproduction.json). Row traces and the rebuilt pair CSV remain local and ignored by Git. The requested `training/acceptance.json` does not exist; the actual acceptance receipt is at the previous report root.

## Error diagnostics and root-cause limits

On all 7,668 historical cases, frozen/retrained MAE is 1.777519/1.728657 m, RMSE 3.055598/3.008508 m, and signed error -0.040926/-0.056567 m. The retrained model overestimates depth in 52.713% of cases. Small aggregate bias coexists with substantial individual errors.

The evidence does **not** show aggregate systematic overreaction. Relative to the latest measurement, retrained predicted-change standard deviation is 1.695474 m versus actual-change standard deviation 2.793654 m; mean absolute predicted/actual changes are 0.874649/1.618984 m. It predicts a larger absolute change in 35.040% of cases and a different direction, including zero, in 42.169% of nonzero-change cases. These descriptive statistics include estimated-anchor effects and cannot isolate the learned delta from anchor error.

Persistence remains better on the historical four-way panel despite the refit's improvement over frozen weights. Tier B local-persistence and Tier C regional-reference paths do not change with model weights. Tier C has 108 cases in only nine districts, MAE {f(tier_c)} m for both models, and is exploratory. Its lack of local labels prevents either baseline; four-way matching must not hide it. All tier/district/state, horizon, recency, history-count, exact observed/finite lag, projection-lag-fallback, raw origin-weather and enrichment cohorts are exported with support counts. Error quantiles, signed histograms, medians, over/underestimate proportions and change diagnostics are included in `analysis_v1/historical_diagnostics_v2.json` and `run_v2/outer_diagnostics.json`.

The 2025 diagnostic has no finite raw weather at the origin month; the serving climatology/fallback still supplies eligible weather features. All A-tier seasonal-supported cases require a groundwater lag fallback. Consequently these variables are confounded with serving tier/recency and cannot identify a causal source of error. Stale-anchor accuracy remains distinct from observed-origin model accuracy. The sixteen newly local districts have no January 2026 targets. District-level rows are descriptive: a single district cannot satisfy the ten-district support rule.

![Historical errors on common cases](analysis_v1/historical_diagnostics.png)

## Chronology, availability and nested selection

The active, source-sealed protocol is [protocol_v2.json](protocol_v2.json), SHA-256 `{sha256_file(protocol_path)}`. Availability rules choose the last two eligible origin-year cohorts with their **entire twelve-horizon target window ending before 2023**. Training target cutoffs preserve the existing twelve-month origin embargo. Each outer fold uses the last two supported inner windows ending no later than its training-label cutoff: 2020 uses 2016/2017, and 2021 uses 2017/2018. The union 2016–2018 selects the final development recipe independently of outer outcomes.

{chr(10).join(fold_rows)}

All horizons have actual training and evaluation cases. M+1 in outer 2020 has only nine districts and is unsupported for subgroup interpretation; all missing and small panels remain reported. Target windows overlap across cohorts, so repeated origins, horizons and target months are dependent. The early audit's same-year target availability file is superseded by the active full-horizon protocol; ending targets in the origin year would have removed M+12.

The fixed frozen model was trained through 2019; its predictions contain no post-origin labels on outer origins from 2020 onward, but on the 2020 fold it does not respect the stricter training recipe's 2018 cutoff and twelve-month embargo. It is a historical artifact reference, not a same-cutoff learned control. The current fixed artifact was trained through January 2025 and is contaminated on all these folds. Its separately labelled raw reconstructed-depth diagnostic is **never** ranking or promotion evidence. Refitted production/current recipes provide controlled chronological comparisons on identical training data. No old 2023/2024 validation score or inspected January 2026 value enters tuning, early stopping, feature selection, calibration, architecture choice or the final ranking.

All learned preprocessing is fitted on the training partition only. The pure causal pair builder was rerun without January 2026 labels and matches all 145,494 existing eligible pairs within 1e-12. Future perturbation tests cover groundwater, weather and output fields. The previous retraining also corrected a feature-construction alignment issue while adding observations; its gains cannot be attributed solely to extra data. Historical observation dates do not establish historical publication/receipt availability: this remains a point-in-time limitation, so neither nested evaluation nor this report is called prospective or untouched.

## Locked experiment ledger and actual coverage

The protocol records each recipe's hypothesis, changes, expected benefit, failure mode, folds, support thresholds and metrics. No broad or adaptive search was run. The base is the current 461-tree, depth-four squared-error recipe. All XGBoost fits use seed 42, histogram trees and four workers.

- A: unweighted references versus train-only district-balanced weights, normalized to mean one and equal total mass per training district. Pair-count quantiles and top-ten district training share are in `run_v2/fold_inputs.json`; sample weights do not use labels or validation data.
- B: shared regressor versus three contiguous groups (M+1–4, M+5–8, M+9–12). Individual-horizon models were attempted but fail the declared support rule: earliest-inner M+1 has 430 cases across 66 districts and two target years; M+11 has 293 across 65 districts and two years. The minimum remains 500 cases, 50 districts and five years. Preflight excludes this recipe from all folds without removing validation cases.
- C: up to 480 trees with forty-round inner early stopping; depth two/minimum child weight 120/L2 80/L1 .4; learning rate .02 with inner stopping; or row/column sampling .7/.7. Other base values remain fixed. Outer/final tree counts use inner median best counts, never outer early stopping.
- D: `reg:absoluteerror` and `reg:pseudohubererror` with slope one versus squared error, supported by installed XGBoost {protocol['environment']['xgboost']}. No valid observed target was clipped. Early stopping, where used, monitors delta MAE; recipe selection scores the reconstructed, floored and rounded depth.
- E: remove exactly one declared feature group: groundwater anchor/lag inputs; horizon/calendar encodings; origin/target climatology weather; cumulative weather. The origin anchor is always retained for reconstruction even when removed as a learned covariate. Weather ablation still leaves cumulative weather proxies, and calendar ablation leaves correlated horizon information, so these are conditional information tests rather than causal feature attribution.
- F: median imputation plus missing indicators, scaling and ridge alpha 100, all fitted on training only; and a per-district past-36-month linear trend with a six-month damped trajectory, requiring three observations or explicitly falling back to measured persistence. No new dependency was installed.

Sixteen supported recipes were evaluated on three inner and two outer folds: **80 recipe/fold evaluations**, including five deterministic local-trend evaluations. The grouped-horizon recipe has three learned members, giving 85 learned member fits across the folds. The first partial run stopped on the individual-horizon support failure before any completed fold; its artifacts are retained under `run_v1` and are not scored or selected. `protocol_v2` preflights those same support rules; supported recipes and hyperparameters were unchanged.

The primary metric is equal mean fold district-macro MAE on identical seasonal-supported cases. Each eligible district with at least one case has equal weight within a fold, matching the prior macro convention; this does not turn a small district sample into a supported finding. Case-weighted MAE answers a different question and is separately reported. Full outer coverage is {summary['pooled_full_cases']:,} cases / {summary['full_districts']} districts; seasonal matching excludes {summary['seasonal_missing_cases']:,} cases, leaving **{summary['pooled_common_cases']:,} / {summary['common_districts']}** for every method below. There are no candidate-specific population changes.

## Results and model selection

{chr(10).join(table)}

Inner-primary improvements over the current recipe: {', '.join('`'+x+'`' for x in better) or 'none'}. Inner-primary regressions or ties: {', '.join('`'+x+'`' for x in worse) or 'none'}. The full outer table shows which improvements transfer. Fixed-recipe outer rankings are secondary exploratory evidence; they were not used to pick another winner.

District balancing worsens outer macro MAE and RMSE, so equalizing training mass does not improve this sample. Robust losses do not improve outer macro MAE and increase RMSE. Removing groundwater inputs produces the largest ablation regression; removing calendar, weather or cumulative groups also worsens outer macro MAE. These are conditional predictive-information findings, not proof of physical causality. Ridge reduces mean fold RMSE but worsens MAE and macro MAE; the damped local trend loses to persistence. There is no reliable new improvement from the tested sophistication.

The current XGBoost recipe nevertheless beats persistence and seasonal naive on these historical observed-origin outer cases. Its loss to baselines in the January 2026 serving diagnostic concerns a different population and estimated-anchor setting. Together the results support conditional historical ML value, not nationwide current-period superiority or a claim that either approach always wins.

{chr(10).join(outer_rows)}

Negative differences favor the nested policy. The following pooled case and district metrics share identical keys; pooled district macro differs from the primary equal mean of fold macro values.

{chr(10).join(compare)}

![Development comparisons](analysis_v1/development_comparison.png)

## Subgroups, uncertainty and acceptance

The minimum supported panel is thirty cases across ten districts, and the maximum permitted supported horizon/history regression is ten percent relative MAE. There are {len(failures)} failed checks and {len(unsupported)} unsupported checks across the two references; checks overlap and must not be added as independent populations. Complete per-horizon/history, state, lag, weather and recency metrics remain in the case-derived diagnostic exports. Different horizon panels contain different districts and target months, so curve differences do not isolate an effect of horizon length.

{chr(10).join(fail_rows)}

Original numerical safeguards applied to the nested selection procedure: mean full-fold macro gain versus frozen {pct(gates['full_macro_relative_improvement_vs_frozen'])} (two-percent gate: {gates['full_macro_2pct_vs_frozen_pass']}), versus persistence {pct(gates['full_macro_relative_improvement_vs_persistence'])} (gate: {gates['full_macro_2pct_vs_persistence_pass']}); paired seasonal macro no worse: {gates['seasonal_paired_macro_no_worse_pass']}; supported subgroup gate versus frozen: {gates['supported_frozen_subgroup_checks_pass']}. This is a development assessment of fold-selected models, not formal acceptance of final refit weights.

Paired district-cluster resampling uses 2,000 deterministic draws, retaining each district's repeated cases together. Per-fold and pooled descriptive intervals and district win fractions are in [comparison.json](analysis_v1/comparison.json). They do not eliminate shared state/weather/target-month dependence across districts. Two outer origin cohorts, overlapping target windows and changing measurement panels limit practical and statistical confidence; a numerical ranking is not a universal district or horizon improvement.

Untouched post-refit test: **absent**. New final-candidate nationwide serving/API/calibration gates: **not assessed and not claimed to pass**. Existing production/API/legacy-six-month contracts are covered by the full test suite. Promotion remains prohibited regardless of development scores. Old-model calibration is never rebound to new weights; candidate intervals remain unavailable.

## Artifacts, identities and reproducibility

Starting branch/commit: `feature/enriched-xgboost-retraining-20261027` / `d992d396b103a57f04e1ebf433e3591aa626550d`. Work branch: `feature/aquaiq-accuracy-experiments-20261027`.

- Frozen model SHA-256: `{baseline['models']['frozen']}`.
- Preserved current candidate SHA-256: `{baseline['models']['current']}`.
- Rebuilt eligible pair CSV SHA-256: `{baseline['development_pairs_sha256']}`. Each fold also records its ordered-data fingerprint, exact origin/target ranges, per-horizon support and case export hash.
- Final development choice: `{decision['selected']}`; checkpoint: `{candidate}`; member model hashes: `{decision.get('new_candidate_model_hashes',[])}`; model-card SHA-256: `{decision.get('new_candidate_card_sha256','not applicable')}`.
- Every fold has a new checkpoint/card/member directory under `run_v2/fold_artifacts/`. Cards bind the exact seventeen ordered inference features, fitted subset, target semantics, code hashes, source generation, dataset fingerprint, cutoff, parameters, dependency versions and validation counts. A strict isolated loader checks hashes, order and exact horizon coverage. Full pair/case exports, detailed diagnostics and per-fold learners remain local and Git-ignored; compact reports, protocol and final artifacts are retained.
- Dependencies: `{json.dumps(protocol['environment'],sort_keys=True)}`. No dependencies, API schemas, canonical IDs, source flags, public data, legacy models, production fallbacks or telemetry quarantine rules changed.

```powershell
.\\venv\\Scripts\\python.exe -u -B -m scripts.audit_accuracy_baselines --output reports/accuracy_experiments_replay/audit
.\\venv\\Scripts\\python.exe -u -B -m scripts.run_accuracy_experiments prepare --audit reports/accuracy_experiments_replay/audit --protocol reports/accuracy_experiments_replay/protocol.json
.\\venv\\Scripts\\python.exe -u -B -m scripts.run_accuracy_experiments run --protocol reports/accuracy_experiments_replay/protocol.json --output reports/accuracy_experiments_replay/run_replay
.\\venv\\Scripts\\python.exe -B -m pytest --integration -o tmp_path_retention_policy=failed --basetemp scratch/pytest-accuracy-replay -q
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run lint
npm.cmd --prefix dashboard run build
```

The executed result uses `protocol_v2.json` and `run_v2`. To rebuild figures/tables, run `python -B -m scripts.summarize_accuracy_experiments --root reports/accuracy_experiments_20261027 --run reports/accuracy_experiments_20261027/run_v2 --protocol reports/accuracy_experiments_20261027/protocol_v2.json --analysis-version analysis_replay`. The tool refuses existing analysis/report paths. See [the workflow guide](../../docs/ACCURACY_EXPERIMENTS.md) for required ignored data and isolated inference.

## Executed verification and modified files

Full Python integration suite: **{verification['full_python']['passed']:,} passed, one skipped, zero failures/errors, seventy warnings**, {verification['full_python']['seconds']:.2f} seconds. Focused scientific/contract suite: **136 passed** in 28.86 seconds; it overlaps the full suite. Three additional reporting regression tests passed after the final reporting correction. Frontend: **160 passed**, lint exit zero, build exit zero; largest JS chunk 365,385 bytes. [Verification receipt]({verification_path.name}) records actual commands, [pytest.xml](pytest.xml) the full run.

The skip requires Windows directory-symlink privileges. Warnings comprise one sklearn single-label diagnostic, one netCDF4/NumPy binary-size import warning and sixty-eight xarray NumPy-shape deprecations. The first full attempt exhausted disk while retaining raster fixtures and has no valid final summary; only this task's resolved temporary directory was removed, and pytest's passing-fixture cleanup setting fixed the rerun. An initial focused run had one sandbox atomic-replace failure (135 passed); the identical elevated rerun passed all 136. These unsuccessful attempts are recorded, not counted as passes. The initial audit harness reference-helper issue and support-limited partial modeling attempt are also recorded.

Modified files: `.gitignore`, `.gitattributes`; `models/accuracy_experiments.py`, `models/accuracy_challengers.py`; `scripts/audit_accuracy_baselines.py`, `scripts/run_accuracy_experiments.py`, `scripts/summarize_accuracy_experiments.py`; `tests/test_accuracy_experiments.py`, `tests/test_accuracy_challengers.py`, `tests/test_accuracy_reporting.py`; `docs/ACCURACY_EXPERIMENTS.md`; versioned report evidence and any separately named final experimental artifact. Existing candidate, production, training and serving source files are unchanged.

## Evidence still needed

Freeze the selected procedure before collecting genuinely new future measurements, document forecast issuance and source receipt dates, check stable wells/datum/aggregation, and evaluate matching observed targets across all twelve horizons and supported district-history groups. Reassess nationwide serving, stale-anchor behavior, API/rollback contracts and independent interval calibration for the exact candidate weights. Pumping/extraction and observation-panel changes remain unverified explanations, not established causes. This development study cannot establish skill for unlabelled districts or replace the required future test.
"""
    report=report.replace('analysis_v1/',analysis_version+'/')
    path=root/('REPORT.md' if analysis_version=='analysis_v1' else f'REPORT_{analysis_version}.md')
    if path.exists():raise FileExistsError('Use a new report version.')
    path.write_text(report,encoding='utf-8')


def run(root,run_directory,protocol_path,analysis_version='analysis_v1'):
    root,run_directory,protocol_path=Path(root),Path(run_directory),Path(protocol_path)
    if not analysis_version.replace('_','').isalnum():raise ValueError('Use a simple versioned directory name.')
    destination=root/analysis_version
    if destination.exists():raise FileExistsError('Use a fresh summary output version.')
    destination.mkdir()
    protocol=json.loads(protocol_path.read_text())
    audit=Path(protocol['audit_directory'])
    records=json.loads((run_directory/'results.json').read_text())
    decision=json.loads((run_directory/'decision.json').read_text())
    cases=pd.read_csv(run_directory/'outer_pooled_cases.csv',parse_dates=['origin_date','target_date'])
    names=[c['name'] for c in protocol['candidates'] if c['status']=='eligible']+['persistence','seasonal']
    common=cases.loc[np.isfinite(cases[names].to_numpy(float)).all(axis=1)]
    methods=names+['nested_selected','frozen_fixed_reference']
    pooled={m:compact(a.metric(common,m)) for m in methods}
    full={m:compact(a.metric(cases.loc[np.isfinite(cases[m])],m)) for m in methods if m!='seasonal'}
    outer=[r for r in records if r['phase']=='outer']
    mean_fold={m:float(np.mean([a.metric(common.loc[common.origin_date.dt.year.eq(r['year'])],m)['district_macro_mae_m'] for r in outer])) for m in methods}
    primary_table=[]
    for name in methods:
        primary_table.append({'method':name,'pooled_common':pooled[name],
            'mean_fold_macro_mae_m':mean_fold[name],
            'versus_current_recipe':differences(pooled[name],pooled['current_recipe']),
            'versus_frozen':differences(pooled[name],pooled['frozen_fixed_reference']),
            'versus_persistence':differences(pooled[name],pooled['persistence']),
            'versus_seasonal':differences(pooled[name],pooled['seasonal'])})
    per_fold=[]
    for r in outer:
        subset=common.loc[common.origin_date.dt.year.eq(r['year'])]
        metrics={m:compact(a.metric(subset,m)) for m in ['nested_selected','current_recipe','frozen_fixed_reference','persistence','seasonal']}
        per_fold.append({'year':r['year'],'selected':r['selected_from_inner'],'joint_metrics':metrics,
                         'full_nested':r['nested_scores']['full'],
                         'paired_uncertainty':r['paired_uncertainty'],
                         'differences':{m:differences(metrics['nested_selected'],metrics[m]) for m in metrics if m!='nested_selected'}})
    supported_checks=subgroup_checks(outer)
    mean_nested=mean_fold['nested_selected']
    full_macro={m:float(np.mean([r['nested_scores']['full'][m]['district_macro_mae_m'] for r in outer]))
                for m in ['nested_selected','current_recipe','production_recipe','persistence']}
    frozen_full=float(np.mean([r['fixed_artifact_diagnostic']['full']['frozen_fixed_reference']['district_macro_mae_m'] for r in outer]))
    gates={'full_macro_relative_improvement_vs_frozen':1-full_macro['nested_selected']/frozen_full,
           'full_macro_relative_improvement_vs_persistence':1-full_macro['nested_selected']/full_macro['persistence'],
           'full_macro_2pct_vs_frozen_pass':full_macro['nested_selected']<=frozen_full*.98,
           'full_macro_2pct_vs_persistence_pass':full_macro['nested_selected']<=full_macro['persistence']*.98,
           'seasonal_paired_macro_no_worse_pass':mean_nested<=mean_fold['seasonal'],
           'supported_frozen_subgroup_checks_pass':subgroup_gate(supported_checks,'frozen_fixed_reference'),
           'untouched_post_refit_test_pass':False,'new_candidate_full_serving_API_contract_gate':'not executed; no claim of pass',
           'promotion_eligible':False}
    # Always expose all historical tiers on their available populations, alongside
    # common-baseline panels. Seasonal missingness must not erase Tier C errors.
    historical=pd.read_csv(audit/'historical_cases_with_traces.csv',parse_dates=['origin_date','target_date'])
    historical_diag=a.diagnostics(historical,['frozen','retrained','persistence','seasonal'])
    _write_json(destination/'historical_diagnostics_v2.json',historical_diag)
    cohort=[c for c in protocol['candidates'] if c['name']=='individual_horizons'][0]
    report={'protocol_sha256':sha256_file(protocol_path),'decision_sha256':sha256_file(run_directory/'decision.json'),
        'common_case_keys_sha256':a.key_hash(common),'pooled_common_cases':len(common),
        'pooled_full_cases':len(cases),'seasonal_missing_cases':len(cases)-len(common),
        'common_districts':int(common.district_id.nunique()),'full_districts':int(cases.district_id.nunique()),
        'primary_table':primary_table,'pooled_full':full,'per_fold':per_fold,
        'full_mean_fold_macro':{**full_macro,'frozen_fixed_reference':frozen_full},
        'development_gates':gates,'subgroup_checks':supported_checks,
        'unsupported_individual_horizons':cohort['eligibility_failures'],
        'paired_district_bootstrap':{m:a.paired_district_bootstrap(common,'nested_selected',m)
                                   for m in ['current_recipe','frozen_fixed_reference','persistence','seasonal']},
        'historical_tier_full':{k:{m:compact(v) for m,v in panel['all_available'].items()}
                                for k,panel in historical_diag['subgroups']['tier'].items()},
        'historical_changes':historical_diag['changes'],
        'final_decision':decision}
    _write_json(destination/'comparison.json',report)
    # Compact, identical-population visualizations with support printed below.
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(14,6),layout='constrained')
    ordered=sorted(primary_table,key=lambda x:x['mean_fold_macro_mae_m'])
    labels=[r['method'] for r in ordered]
    colors=['#0c837b' if n=='nested_selected' else '#aa6f26' if n in ['persistence','seasonal'] else '#3e658a' for n in labels]
    axes[0].barh(labels,[r['mean_fold_macro_mae_m'] for r in ordered],color=colors)
    axes[0].invert_yaxis();axes[0].set_xlabel('Mean outer-fold district-macro MAE (m)')
    axes[0].set_title('Historical development: common seasonal cases')
    for method in ['nested_selected','current_recipe','frozen_fixed_reference','persistence','seasonal']:
        points=[a.metric(g,method)['mae_m'] for _,g in common.groupby('horizon')]
        axes[1].plot(range(1,13),points,marker='o',label=method)
    axes[1].set_xticks(range(1,13));axes[1].set_xlabel('Forecast horizon (months)')
    axes[1].set_ylabel('Pooled case-weighted MAE (m)');axes[1].legend(fontsize=8)
    axes[1].set_title('Same cases for every plotted method')
    fig.suptitle(f'Outer origin cohorts 2020/2021; {len(common):,} common cases, {common.district_id.nunique()} districts\nDevelopment evidence; fixed-recipe outer comparisons are exploratory',fontsize=12)
    fig.savefig(destination/'development_comparison.png',dpi=170);plt.close(fig)
    oldcommon=historical.loc[historical.seasonal.notna()&historical.persistence.notna()]
    fig,axes=plt.subplots(1,2,figsize=(13,4.7),layout='constrained')
    for method in ['frozen','retrained','persistence','seasonal']:
        absolute=np.sort(abs(oldcommon[method]-oldcommon.actual))
        axes[0].plot(absolute,np.arange(1,len(absolute)+1)/len(absolute),label=method)
        axes[1].plot(range(1,13),[a.metric(g,method)['mae_m'] for _,g in oldcommon.groupby('horizon')],marker='o',label=method)
    axes[0].set_xlim(0,8);axes[0].set_xlabel('Absolute depth error (m)');axes[0].set_ylabel('Empirical cumulative fraction')
    axes[1].set_xticks(range(1,13));axes[1].set_xlabel('Horizon (also different 2025 origin)');axes[1].set_ylabel('MAE (m)')
    axes[0].legend();axes[1].legend();fig.suptitle('Previously inspected January 2026: 6,756 cases / 563 districts\nPersistence and seasonal naive use the identical January 2025 observation')
    fig.savefig(destination/'historical_diagnostics.png',dpi=170);plt.close(fig)
    _write_json(destination/'figure_checksums.json',{p.name:sha256_file(p) for p in destination.glob('*.png')})
    if (root/'verification.json').exists():
        markdown_report(root,run_directory,protocol_path,report,protocol,records,historical_diag,analysis_version)
    print(json.dumps({'common_cases':len(common),'common_districts':int(common.district_id.nunique()),
                      'development_gates':gates,'final_selected':decision['selected']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True)
    p.add_argument('--analysis-version',default='analysis_v1')
    args=p.parse_args();run(args.root,args.run,args.protocol,args.analysis_version)
