"""Honest disclosure of historical error bands, separate from point forecasts.

The radii are never fitted or widened here. A minimum calibration-district
tail-resolution rule withholds unsupported bands. Matching retrospective
evaluation describes observed case fractions, never local coverage guarantees.
"""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT/'models/artifacts/interval_reliability.json'
POLICY_VERSION = '2.0-empirical-error-band-disclosure'
MIN_CALIBRATION_DISTRICTS = 10
INTERVAL_STATUSES = {'unavailable', 'historical_reference_only', 'empirical_undercovered'}


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def calibration_support(calibration, tier, horizon):
    """A reporting guard, not a conformal bound or proof of calibration.

    Ten distinct districts at a 90th-percentile calibration quantile provide
    only one expected tail case. Fewer cannot support even that resolution.
    Districts/cases may still be dependent; passing this guard gives no coverage
    guarantee. The fixed rule uses calibration counts, never final residuals.
    """
    counts = calibration.get('sample_counts', {}).get(tier, {}).get(str(horizon), {})
    n, districts = counts.get('n'), counts.get('districts')
    if not _integer(n) or not _integer(districts) or n < districts:
        return False, {'n': 0, 'districts': 0}, 'Missing or inconsistent calibration sample counts.'
    supported = districts >= MIN_CALIBRATION_DISTRICTS
    reason = None if supported else f'Fewer than {MIN_CALIBRATION_DISTRICTS} distinct calibration districts; tail support is insufficient.'
    return supported, {'n': n, 'districts': districts}, reason


def load_validation_evidence(path=None):
    path = Path(path or EVIDENCE_PATH)
    if not path.exists():
        return None
    evidence = json.loads(path.read_text(encoding='utf-8'))
    if evidence.get('schema_version') != 1 or evidence.get('policy_version') != POLICY_VERSION:
        raise ValueError('Unrecognized interval reliability evidence version.')
    if not isinstance(evidence.get('tiers'), dict) or not evidence.get('report_date'):
        raise ValueError('Interval evidence is missing its date and tier panels.')
    evidence = deepcopy(evidence)
    evidence['artifact_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return evidence


def _matching_validation(calibration, cutoff, evidence):
    if evidence is None:
        return None
    cutoff = date.fromisoformat(str(cutoff)[:10])
    if date.fromisoformat(evidence['report_date']) > cutoff:
        return None
    identity = ('feature_generation_id', 'xgboost_sha256', 'calibration_id')
    if any(evidence.get(key) != calibration.get(key) for key in identity):
        return None
    if date.fromisoformat(evidence['max_evaluation_target']) > cutoff:
        return None
    return evidence


def attach_error_bands(result, calibration, cutoff, *, evidence=None):
    """Attach supported unchanged radii and explicit per-horizon statuses.

    This never changes a point, an observation flag or an eligibility decision.
    Old partially emitted bounds are removed first so unavailable metadata
    cannot coexist with a precise-looking numerical band.
    """
    for row in result['forecast']:
        row.pop('lower_gwl', None)
        row.pop('upper_gwl', None)
        row.update(interval_status='unavailable', interval_reason='No matching pre-origin calibration for this horizon.')
    result['uncertainty'] = {'status': 'unavailable', 'policy_version': POLICY_VERSION,
        'interval_kind': 'historical_absolute_error_band', 'local_coverage_guarantee': False,
        'reason': 'No matching pre-origin calibration with adequate sample support.',
        'available_horizons': [], 'unavailable_horizons': [r['horizon'] for r in result['forecast']]}
    if calibration is None:
        return result
    cutoff_date = date.fromisoformat(str(cutoff)[:10])
    completed_month = (cutoff_date.replace(day=1)-timedelta(days=1)).replace(day=1)
    if date.fromisoformat(calibration['max_calibration_target']) > completed_month:
        return result
    quantile = calibration.get('nominal_coverage', .9)
    if isinstance(quantile, bool) or not isinstance(quantile, (int,float)) or quantile != .9:
        raise ValueError('Historical error-band disclosure requires the inspected 90th-percentile calibration.')
    validation = _matching_validation(calibration, cutoff, evidence)
    tier = result['evidence_tier']
    tier_validation = validation.get('tiers', {}).get(tier) if validation else None
    status = ('empirical_undercovered' if tier_validation and tier_validation.get('case_fraction_covered') is not None
              and tier_validation['case_fraction_covered'] < quantile else 'historical_reference_only')
    available, unavailable, counts_by_horizon = [], [], {}
    for row in result['forecast']:
        horizon = row['horizon']
        radius = calibration.get('radii_m', {}).get(tier, {}).get(str(horizon))
        supported, counts, reason = calibration_support(calibration,tier,horizon)
        counts_by_horizon[str(horizon)] = counts
        if radius is not None and (isinstance(radius,bool) or not isinstance(radius,(int,float)) or not math.isfinite(radius) or radius < 0):
            raise ValueError('Historical calibration contains an invalid radius.')
        if radius is None or not supported:
            unavailable.append(horizon)
            row['interval_reason'] = reason or 'No calibration radius for this horizon.'
            continue
        prediction = row['predicted_gwl']
        horizon_validation = tier_validation.get('by_horizon', {}).get(str(horizon)) if tier_validation else None
        horizon_status = ('empirical_undercovered' if horizon_validation and horizon_validation.get('case_fraction_covered') is not None
            and horizon_validation['case_fraction_covered'] < quantile else 'historical_reference_only')
        row.update(lower_gwl=max(0.,round(prediction-radius,4)), upper_gwl=round(prediction+radius,4),
            interval_status=horizon_status, interval_reason='Historical residual band; no calibrated local probability is established.')
        if horizon_validation:
            row['interval_validation_cases'] = horizon_validation['band_cases']
            row['interval_validation_districts'] = horizon_validation.get('band_districts',0)
        available.append(horizon)
    result['uncertainty'].update(status=status if available else 'unavailable',
        reason=('Historical evaluation showed undercoverage; these are descriptive error bands, not calibrated 90% prediction intervals.'
            if status=='empirical_undercovered' and available else
            'These unchanged historical residual bands have no matching validated coverage for this input generation.' if available else
            'Calibration support is insufficient for every horizon; point estimates remain available.'),
        calibration_quantile=quantile, minimum_distinct_calibration_districts=MIN_CALIBRATION_DISTRICTS,
        calibration_id=calibration['calibration_id'], max_calibration_target=calibration['max_calibration_target'],
        sample_counts_by_horizon=counts_by_horizon, available_horizons=available, unavailable_horizons=unavailable,
        scope='Pooled historical district-month residuals; no district-specific coverage estimate.',
        limitations='Spatial/temporal dependence, changing station panels and observation age prevent a present-period coverage guarantee.')
    if tier_validation:
        result['uncertainty']['historical_validation'] = {**deepcopy({k:v for k,v in tier_validation.items() if k!='by_horizon'}),
            'scope': 'Descriptive pooled historical cases, not the probability for this district.',
            'report_date': validation['report_date'], 'artifact_sha256':validation.get('artifact_sha256')}
    return result


def validate_disclosure(result):
    """Publication must not retain numerical bounds marked unavailable."""
    metadata=result.get('uncertainty',{})
    if metadata.get('policy_version') != POLICY_VERSION:
        return  # Prior immutable publications retain their recorded schema.
    if metadata.get('status') not in INTERVAL_STATUSES or metadata.get('local_coverage_guarantee') is not False:
        raise ValueError('Invalid empirical uncertainty disclosure.')
    for row in result['forecast']:
        status=row.get('interval_status')
        has_lower,has_upper='lower_gwl' in row,'upper_gwl' in row
        if (status not in INTERVAL_STATUSES or has_lower != has_upper
                or (status=='unavailable') != (not has_lower)
                or metadata['status']=='unavailable' and status!='unavailable'):
            raise ValueError('Interval status contradicts published numerical bounds.')
