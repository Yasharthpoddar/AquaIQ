"""Paired retrospective evaluation of the experimental state median model.

The baseline reuses the unchanged complete district serving path and production
equal-district mean. Targets are qualified, observed state medians, never model
outputs or the baseline's historical mean. This module never trains or writes
district models, calibrations, forecasts or database records.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from db.connection import finite_json
from models import climate_forecast_12m as climate
from models import state_median_forecast as median
from models.district_registry import get_registry
from models.ensemble import _completed_feature_month
from models.state_mapping import STATES_REGISTRY
from models.tiered_forecast import RegionalReference, forecast_district


DEFAULT_ORIGINS = ('2020-12-01',) + tuple(f'{year}-{month}-01' for year in range(2021, 2026) for month in ('01', '07'))
METHODS = ('baseline', 'candidate', 'persistence')
COVERAGE_BINS = (
    ('under_50_percent', 0., .5),
    ('50_to_75_percent', .5, .75),
    ('75_to_90_percent', .75, .9),
    ('90_to_100_percent', .9, 1.),
)
LIMITATIONS = [
    'Experimental retrospective comparison on previously inspected source data; no blind or prospective validation or automatic promotion.',
    'Qualified targets are medians across reporting districts, whose composition varies by month; these are not independent complete state measurements.',
    'Post-2021 high-coverage observations are sparse. Multiple origins and horizons can reuse the same target; forecast-case counts are not independent observation counts.',
    'Source month labels do not establish provider publication or acquisition times. Historical availability is assumed at completed month end.',
    'The baseline is the production equal mean of every registered tiered district forecast, while the candidate targets the reporting-district median; the target change is deliberate.',
    'District models and point predictions are unchanged. No test label is used to fit a candidate, baseline, persistence reference or climate assumption.',
    'The paired comparison excludes failures from both methods and separately discloses unpaired availability and target coverage.',
    'December 2020 was added after auditing target availability, before inspecting model errors, to reach the January 2021 observation round. Its month-end cutoff is exactly twelve months after frozen district training labels. This diagnostic does not establish skill across all twelve horizons or calendar months.',
    'These errors belong to the evaluated frozen artifact and its declared training cutoff. A later refit may cite them only as historical methodology evidence, never as held-out validation of its newer weights.',
]


def error_metrics(rows, column):
    """Strict finite-pair errors; direction excludes unchanged actual targets."""
    if not len(rows):
        return dict(n=0, states=0, valid_state_month_observations=0, mae_m=None,
                    rmse_m=None, bias_m=None, directional_accuracy=None, directional_n=0,
                    period_start=None, period_end=None, mean_target_coverage_ratio=None,
                    mean_origin_reference_coverage_ratio=None, target_calendar_months=0,
                    evaluated_origins=0, horizons=[], target_months_of_year=[])
    part = rows.loc[np.isfinite(pd.to_numeric(rows[column], errors='coerce')) &
                    np.isfinite(pd.to_numeric(rows.actual, errors='coerce'))].copy()
    if not len(part):
        return error_metrics(part, column)
    errors = part[column].to_numpy(float) - part.actual.to_numpy(float)
    direction = None
    directional_n = 0
    if 'persistence' in part:
        anchors = pd.to_numeric(part.persistence, errors='coerce').to_numpy(float)
        actual_delta = part.actual.to_numpy(float) - anchors
        predicted_delta = part[column].to_numpy(float) - anchors
        directional = np.isfinite(anchors) & ~np.isclose(actual_delta, 0., atol=1e-8, rtol=0.)
        directional_n = int(directional.sum())
        if directional_n:
            direction = float((np.sign(actual_delta[directional]) == np.sign(predicted_delta[directional])).mean())
    return dict(n=len(part), states=int(part.state_id.nunique()),
                valid_state_month_observations=len(part[['state_id', 'target_date']].drop_duplicates()),
                mae_m=float(np.abs(errors).mean()), rmse_m=float(np.sqrt(np.mean(errors ** 2))),
                bias_m=float(errors.mean()), directional_accuracy=direction, directional_n=directional_n,
                period_start=str(part.target_date.min()), period_end=str(part.target_date.max()),
                mean_target_coverage_ratio=float(part.target_coverage_ratio.mean()) if 'target_coverage_ratio' in part else None,
                mean_origin_reference_coverage_ratio=float(part.origin_reference_coverage_ratio.mean()) if 'origin_reference_coverage_ratio' in part else None,
                target_calendar_months=int(part.target_date.nunique()),
                evaluated_origins=int(part.origin_date.nunique()) if 'origin_date' in part else 0,
                horizons=sorted(int(h) for h in part.horizon.unique()) if 'horizon' in part else [],
                target_months_of_year=sorted(int(m) for m in pd.to_datetime(part.target_date).dt.month.unique()))


def metric_changes(baseline, candidate):
    result = {}
    for metric in ('mae_m', 'rmse_m'):
        a, b = baseline.get(metric), candidate.get(metric)
        result[metric] = dict(absolute_change_m=b-a if a is not None and b is not None else None,
                             relative_change_pct=100*(b-a)/a if a is not None and b is not None and a > 0 else None)
    return result


def summarize_cases(cases):
    """Expose all available panels and the exact common panel side by side."""
    eligible = cases.loc[cases.target_eligible.astype(bool)]
    paired = eligible.dropna(subset=list(METHODS))
    raw = {name: error_metrics(eligible, name) for name in METHODS}
    matched = {name: error_metrics(paired, name) for name in METHODS}
    return dict(eligible_target_cases=len(eligible),
                attempted_horizon_cases=len(cases),
                eligible_states=int(eligible.state_id.nunique()),
                valid_state_month_observations=len(eligible[['state_id', 'target_date']].drop_duplicates()),
                target_calendar_months=int(eligible.target_date.nunique()),
                baseline=raw['baseline'], candidate=raw['candidate'], persistence=raw['persistence'],
                paired=matched, changes=metric_changes(matched['baseline'], matched['candidate']),
                candidate_vs_persistence=metric_changes(matched['persistence'], matched['candidate']),
                availability={name: dict(available_cases=raw[name]['n'], unavailable_cases=len(eligible)-raw[name]['n'],
                                        evaluated_states=raw[name]['states']) for name in METHODS},
                failure_reasons=dict(Counter(str(x) for x in eligible.candidate_reason.dropna())))


def coverage_summaries(cases):
    """Fixed, disclosed target-coverage bins; missing targets remain separate."""
    ratio = pd.to_numeric(cases.target_coverage_ratio, errors='coerce')
    observed = (cases.target_observed.astype(bool) if 'target_observed' in cases else
                np.isfinite(pd.to_numeric(cases.actual, errors='coerce')))
    available = observed & ratio.notna()
    result = {}
    for label, lower, upper in COVERAGE_BINS:
        included = available & ratio.ge(lower) & (ratio.le(upper) if upper == 1. else ratio.lt(upper))
        result[label] = dict(lower_inclusive=lower, upper=upper, upper_inclusive=upper == 1.,
                             **summarize_cases(cases.loc[included]))
    result['missing_observed_target'] = summarize_cases(cases.loc[~available])
    return result


def target_reuse_summary(cases):
    """Counts expose repeated state-months without implying independence."""
    eligible = cases.loc[cases.target_eligible.astype(bool)]
    paired = eligible.dropna(subset=list(METHODS))
    def counts(part):
        repeats = part.groupby(['state_id', 'target_date']).size()
        return dict(forecast_cases=len(part), unique_state_month_targets=len(repeats),
                    target_calendar_months=int(part.target_date.nunique()),
                    target_months_of_year=sorted(int(m) for m in pd.to_datetime(part.target_date).dt.month.unique()),
                    repeated_forecast_cases=len(part)-len(repeats),
                    maximum_forecasts_per_target=int(repeats.max()) if len(repeats) else 0)
    return dict(eligible=counts(eligible), paired=counts(paired),
        interpretation='Forecast cases sharing a state-month target are repeated evaluations of the same observation. Unique state-month counts also do not establish independence across nearby states.')


def horizon_support(cases):
    """Every supported horizon is present even when it has no usable target."""
    by_horizon = {str(h): summarize_cases(cases.loc[cases.horizon.eq(h)]) for h in range(1, 13)}
    supported = [h for h in range(1, 13) if by_horizon[str(h)]['paired']['candidate']['n']]
    return by_horizon, dict(requested_horizons=list(range(1, 13)), horizons_with_paired_evidence=supported,
        all_horizons_have_paired_evidence=len(supported) == 12,
        all_horizons_validated=False,
        status='limited_historical_evidence' if supported else 'no_paired_evidence',
        by_horizon={str(h): dict(status='limited_historical_evidence' if h in supported else 'no_paired_evidence',
            **by_horizon[str(h)]['paired']['candidate']) for h in range(1, 13)})


def case_summaries(cases):
    by_horizon, support = horizon_support(cases)
    return dict(comparison=summarize_cases(cases),
        by_state={code: summarize_cases(part) for code, part in cases.groupby('state_id', sort=True)},
        by_horizon=by_horizon, horizon_support=support,
        by_target_coverage=coverage_summaries(cases), target_reuse=target_reuse_summary(cases),
        by_origin={str(o): summarize_cases(part) for o, part in cases.groupby('origin_date', sort=True)})


def canonical_cases(cases):
    """Stable schema when one origin contains only missing target/prediction values."""
    cases = cases.copy()
    for column in ('actual', 'observed_target_median_m_bgl', 'target_coverage_ratio',
                   'candidate', 'baseline', 'persistence', 'origin_reference_coverage_ratio',
                   'origin_qualified_month_ratio'):
        if column in cases:
            cases[column] = pd.to_numeric(cases[column], errors='raise').astype(float)
    for column in ('state_id', 'origin_date', 'as_of', 'target_date', 'target_reason',
                   'origin_reference_date', 'candidate_reason', 'baseline_reason'):
        if column in cases:
            cases[column] = cases[column].astype('string')
    return cases.sort_values(['origin_date', 'state_id', 'horizon'], kind='stable').reset_index(drop=True)


def merge_origin_evaluations(results, expected_origins):
    """Merge independent origin replays after verifying provenance and coverage."""
    if not results:
        raise ValueError('No completed origin evaluations to merge.')
    variable = {'origins', 'attempted_state_origins', 'attempted_horizon_cases', *case_summaries(results[0][1])}
    metadata = {key: value for key, value in results[0][0].items() if key not in variable}
    for report, _ in results[1:]:
        if metadata != {key: value for key, value in report.items() if key not in variable}:
            raise ValueError('Parallel origin evaluations have mismatched model, source or protocol identities.')
    cases = pd.concat([part for _, part in results], ignore_index=True)
    if cases.duplicated(['state_id', 'origin_date', 'horizon']).any():
        raise ValueError('Parallel origin evaluations overlap.')
    expected = sorted({pd.Timestamp(value).to_period('M').to_timestamp().date().isoformat() for value in expected_origins})
    if sorted(cases.origin_date.unique()) != expected:
        raise ValueError('Parallel origin evaluations omit or add requested origins.')
    cases = canonical_cases(cases)
    report = dict(metadata, origins=expected,
                  attempted_state_origins=len(cases[['state_id', 'origin_date']].drop_duplicates()),
                  attempted_horizon_cases=len(cases), **case_summaries(cases))
    return finite_json(report), cases


def _training_cutoff(card):
    cutoff = card.get('train_target_cutoff') or card.get('training_cutoff')
    if not cutoff:
        raise ValueError('Model card requires a training-label cutoff for leakage-safe comparison.')
    cutoff = pd.Timestamp(cutoff)
    if card.get('max_train_target_date') and pd.Timestamp(card['max_train_target_date']) > cutoff:
        raise ValueError('Model training targets exceed the declared training cutoff.')
    return cutoff


def validate_origins(origins, candidate_card, baseline_card):
    values = sorted({pd.Timestamp(value).to_period('M').to_timestamp() for value in origins})
    if not values:
        raise ValueError('At least one evaluation origin is required.')
    cutoff = max(_training_cutoff(candidate_card), _training_cutoff(baseline_card))
    # Origins are evaluated at month end. December 2020 means as_of Dec 31,
    # exactly twelve months after a Dec 31, 2019 training-label cutoff.
    first = (cutoff.to_period('M') + 12).to_timestamp()
    if values[0] < first:
        raise ValueError(f'Evaluation origins must begin on or after {first.date()} at month end for the twelve-month training-label embargo.')
    return values


def baseline_state_forecast(code, available, registry, bundle, reference, cutoff, generation):
    """Exactly the production mean, without changing or persisting district paths."""
    districts = sorted(row['district_id'] for row in registry if row['state_id'] == code)
    if not districts:
        return None, 'no_registered_districts'
    groups = {key: group for key, group in available.loc[available.district_id.isin(districts)].groupby('district_id')}
    panel = []
    origin = pd.Timestamp(cutoff).to_period('M').to_timestamp()
    dates = pd.date_range(origin + pd.offsets.MonthBegin(1), periods=12, freq='MS')
    for district_id in districts:
        value = forecast_district(district_id, groups.get(district_id, available.iloc[:0]), cutoff,
                                  generation, bundle, reference, calibration=None)
        rows = value.get('forecast', [])
        if value.get('status') != 'forecast' or value.get('district_id') != district_id or len(rows) != 12:
            raise ValueError('Production baseline returned an incomplete registered district forecast.')
        depths = []
        for h, (row, date) in enumerate(zip(rows, dates), 1):
            actual_date = row.get('date') or row.get('target_date')
            depth = row.get('predicted_gwl')
            if (row.get('horizon') != h or pd.Timestamp(actual_date) != date or isinstance(depth, bool)
                    or not isinstance(depth, (float, int)) or not np.isfinite(depth) or depth < 0):
                raise ValueError('Production baseline returned an invalid district horizon.')
            depths.append(float(depth))
        panel.append(depths)
    return np.round(np.mean(np.asarray(panel, float), axis=0), 4), None


def run_evaluation(frame, history, models, card, origins=DEFAULT_ORIGINS, registry=None, bundle=None):
    """Return report and auditable cases; all predictors see origin-limited data."""
    registry = get_registry() if registry is None else registry
    generation = frame.attrs.get('feature_generation_id')
    bundle = climate.load_bundle(expected_generation=generation) if bundle is None else bundle
    if card.get('feature_generation_id') and card['feature_generation_id'] != generation:
        raise ValueError('Candidate artifact and evaluation data have different feature generations.')
    origins = validate_origins(origins, card, bundle[1])
    if history.duplicated(['state_id', 'date']).any():
        raise ValueError('Ambiguous state-month evaluation labels.')
    labels = history.set_index(['state_id', 'date'])
    records = []
    for origin in origins:
        first_record = len(records)
        cutoff = origin + pd.offsets.MonthEnd(0)
        completed = _completed_feature_month(cutoff)
        available = frame.loc[frame.date.le(completed)].copy()
        available.attrs = {}
        known = history.loc[history.date.le(completed)].copy()
        reference = RegionalReference(available, cutoff)
        for code in STATES_REGISTRY:
            targets = []
            for h in range(1, 13):
                date = origin + pd.DateOffset(months=h)
                key = (code, date)
                target = labels.loc[key] if key in labels.index else None
                qualified = target is not None and bool(target.training_eligible) and np.isfinite(target.gwl_m_bgl)
                targets.append((h, date, target, qualified))
            # Still record all state/origin/horizon eligibility, but avoid
            # expensive inference where no observed test target can be scored.
            candidate, baseline, baseline_reason = None, None, None
            candidate_reason = 'no_qualified_test_targets'
            past = known.loc[(known.state_id == code) & known.training_eligible.astype(bool) &
                             np.isfinite(known.gwl_m_bgl)].sort_values('date')
            persistence = float(past.iloc[-1].gwl_m_bgl) if len(past) else None
            reference_coverage = float(past.iloc[-1].coverage_ratio) if len(past) else None
            reference_date = past.iloc[-1].date.date().isoformat() if len(past) else None
            state_calendar = known.loc[known.state_id == code]
            calendar_months = ((completed.year-state_calendar.date.min().year)*12 +
                               completed.month-state_calendar.date.min().month+1) if len(state_calendar) else 0
            if any(item[3] for item in targets):
                value = median.forecast_state(code, known, models, card, cutoff)
                candidate_reason = None if value.get('status') == 'forecast' else value.get('message') or value.get('status')
                if value.get('status') == 'forecast':
                    rows = value.get('forecast', [])
                    if len(rows) != 12 or any(row.get('horizon') != h or
                        row.get('target_date') != (origin+pd.DateOffset(months=h)).date().isoformat()
                        for h, row in enumerate(rows, 1)):
                        raise ValueError('Candidate returned an invalid forecast calendar.')
                    candidate = {int(row['horizon']): float(row['predicted_gwl']) for row in rows}
                    if set(candidate) != set(range(1, 13)) or not all(np.isfinite(x) and x >= 0 for x in candidate.values()):
                        raise ValueError('Candidate returned an incomplete or nonfinite forecast path.')
                baseline, baseline_reason = baseline_state_forecast(code, available, registry, bundle, reference, cutoff, generation)
            for horizon, target_date, target, qualified in targets:
                records.append(dict(state_id=code, origin_date=origin.date().isoformat(),
                    as_of=cutoff.date().isoformat(), target_date=target_date.date().isoformat(), horizon=horizon,
                    target_eligible=qualified,
                    target_observed=target is not None and bool(np.isfinite(target.gwl_m_bgl)),
                    target_reason=None if qualified else 'missing_or_low_coverage_observed_target',
                    actual=float(target.gwl_m_bgl) if qualified else None,
                    observed_target_median_m_bgl=float(target.gwl_m_bgl) if target is not None and np.isfinite(target.gwl_m_bgl) else None,
                    target_coverage_ratio=float(target.coverage_ratio) if target is not None else None,
                    contributing_districts=int(target.contributing_districts_count) if target is not None else 0,
                    registered_districts=int(target.total_districts_in_state) if target is not None else 0,
                    candidate=candidate.get(horizon) if candidate else None,
                    baseline=float(baseline[horizon-1]) if baseline is not None else None,
                    persistence=persistence,
                    origin_reference_coverage_ratio=reference_coverage, origin_reference_date=reference_date,
                    origin_qualified_state_months=len(past), origin_calendar_months=calendar_months,
                    origin_qualified_month_ratio=len(past)/calendar_months if calendar_months else None,
                    candidate_reason=candidate_reason, baseline_reason=baseline_reason))
        print(f'Evaluated origin {origin:%Y-%m}: {sum(r["target_eligible"] for r in records[first_record:])} qualified cases', flush=True)
    cases = canonical_cases(pd.DataFrame(records))
    report = dict(product='state_median_xgboost_comparison', status='experimental', promotion_recommended=False,
        recommendation='Keep the candidate experimental: sparse, seasonally selected, reused historical observations cannot establish reliable nationwide monthly performance.',
        protocol='Fixed separate state XGBoost artifacts; unchanged complete registered-district tiered baseline; paired qualified held-out state median targets; twelve-month embargo measured at each origin month end.',
        candidate_model_version=card.get('model_version', card.get('version')),
        candidate_training_cutoff=_training_cutoff(card).date().isoformat(),
        evidence_role='frozen_artifact_retrospective_diagnostic',
        validates_later_refit_weights=False,
        baseline_model_version=bundle[1].get('version'), baseline_model_sha256=bundle[1].get('model_sha256'),
        baseline_training_cutoff=_training_cutoff(bundle[1]).date().isoformat(),
        candidate_training_states={code: {key: value for key, value in entry.items() if key in
            ('status', 'observed_months', 'span_months', 'training_rows', 'training_target_months', 'reason')}
            for code, entry in card.get('states', {}).items()},
        feature_generation_id=generation, data_sha256=frame.attrs.get('data_sha256'),
        feature_data_sha256=frame.attrs.get('feature_manifest', {}).get('feature_csv_sha256'),
        origins=[o.date().isoformat() for o in origins], attempted_state_origins=len(origins)*len(STATES_REGISTRY),
        attempted_horizon_cases=len(cases), target_coverage_rule=card.get('policy', card.get('config', {'min_coverage': card.get('min_coverage', .5)})),
        direction_policy='Sign of predicted change from the latest qualified observed state median; actual changes within 1e-8 m of zero are excluded.',
        origin_reference_policy='Origin reference coverage and persistence use the latest qualified median available at month end. The candidate retains its stricter pre-origin-calendar-month feature convention; the unchanged district baseline retains its own serving availability policy.',
        **case_summaries(cases),
        limitations=LIMITATIONS,
        source_sha256={str(path.relative_to(Path(__file__).resolve().parents[1])).replace('\\', '/'):
                       hashlib.sha256(path.read_bytes()).hexdigest() for path in
                       (Path(__file__), Path(median.__file__), Path(__file__).with_name('tiered_forecast.py'))})
    return finite_json(report), cases


def write_report(output, report, cases):
    """Create a fresh evidence directory; never overwrite an earlier report."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cases.to_csv(output / 'cases.csv', index=False)
    report = dict(report, cases_sha256=hashlib.sha256((output / 'cases.csv').read_bytes()).hexdigest())
    (output / 'evaluation.json').write_text(json.dumps(finite_json(report), indent=2, allow_nan=False), encoding='utf-8')
    comparison = report['comparison']
    lines = ['# Experimental state median XGBoost comparison', '', report['recommendation'], '',
             f'Evaluated frozen training cutoff: {report["candidate_training_cutoff"]}. These errors do not validate the weights of a later production refit.', '',
             f'Eligible target cases: {comparison["eligible_target_cases"]}; states: {comparison["eligible_states"]}; unique observed state-month targets: {comparison["valid_state_month_observations"]}.', '',
             '## Identical paired cases', '',
             '| Method | Cases | States | MAE (m) | RMSE (m) |', '|---|---:|---:|---:|---:|']
    for name in METHODS:
        metrics = comparison['paired'][name]
        mae = f'{metrics["mae_m"]:.4f}' if metrics['mae_m'] is not None else 'unavailable'
        rmse = f'{metrics["rmse_m"]:.4f}' if metrics['rmse_m'] is not None else 'unavailable'
        lines.append(f'| {name} | {metrics["n"]} | {metrics["states"]} | {mae} | {rmse} |')
    lines += ['', 'Metrics above use the identical paired target cases. A zero case count means no model comparison can be established.', '',
              '## Available cases before matching', '',
              'The following panels may differ and cannot establish model improvement.', '',
              '| Method | Available cases | Missing cases | MAE (m) | RMSE (m) |', '|---|---:|---:|---:|---:|']
    for name in METHODS:
        metrics = comparison[name]
        mae = f'{metrics["mae_m"]:.4f}' if metrics['mae_m'] is not None else 'unavailable'
        rmse = f'{metrics["rmse_m"]:.4f}' if metrics['rmse_m'] is not None else 'unavailable'
        lines.append(f'| {name} | {metrics["n"]} | {comparison["availability"][name]["unavailable_cases"]} | {mae} | {rmse} |')
    lines += ['', '## Forecast horizon evidence', '',
              '| Horizon | Eligible cases | Paired cases | Target dates | Baseline MAE (m) | Candidate MAE (m) | Candidate RMSE (m) |',
              '|---|---:|---:|---:|---:|---:|---:|']
    def formatted(value):
        return f'{value:.4f}' if value is not None else 'unavailable'
    for horizon in range(1, 13):
        group = report['by_horizon'][str(horizon)]
        candidate = group['paired']['candidate']
        baseline = group['paired']['baseline']
        lines.append(f'| {horizon} | {group["eligible_target_cases"]} | {candidate["n"]} | {candidate["target_calendar_months"]} | {formatted(baseline["mae_m"])} | {formatted(candidate["mae_m"])} | {formatted(candidate["rmse_m"])} |')
    lines += ['', '## Observed target coverage', '',
              '| District coverage | Eligible cases | Paired cases | Candidate MAE (m) | Candidate RMSE (m) |',
              '|---|---:|---:|---:|---:|']
    for label, group in report['by_target_coverage'].items():
        candidate = group['paired']['candidate']
        lines.append(f'| {label.replace("_", " ")} | {group["eligible_target_cases"]} | {candidate["n"]} | {formatted(candidate["mae_m"])} | {formatted(candidate["rmse_m"])} |')
    reuse = report['target_reuse']
    lines += ['', f'Eligible cases reuse {reuse["eligible"]["unique_state_month_targets"]} distinct state-month targets across {reuse["eligible"]["target_calendar_months"]} observation dates. The paired panel contains {reuse["paired"]["unique_state_month_targets"]} distinct state-month targets across {reuse["paired"]["target_calendar_months"]} observation dates. Repeated forecasts of one target are not independent observations.', '',
              'Full availability, unique state-month counts, coverage, per-state/horizon errors and failure cases are in evaluation.json and cases.csv.', '',
              'Changes below are candidate minus baseline; negative values indicate lower error.', '',
              '```json', json.dumps(comparison['changes'], indent=2), '```', '',
              *['- '+item for item in report['limitations']], '']
    (output / 'comparison.md').write_text('\n'.join(lines), encoding='utf-8')
    return report
