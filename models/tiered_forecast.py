"""Complete district outputs around the existing verified XGBoost forecaster.

No observation or environmental predictor is manufactured. The reference path
fits district-balanced empirical seasonal medians to past observations only.
Its target district is always excluded from donors, including pseudo-cold starts.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from models import climate_forecast_12m as climate
from models.monthly_projection import fit_projection, MIN_OBSERVATIONS, MIN_SPAN_MONTHS
from models.ensemble import _as_of, _completed_feature_month
from models.xgboost_model import observed_mask
from models.interval_evidence import attach_error_bands, load_validation_evidence, validate_disclosure

VERSION = '1.0-tiered-12m'
REFERENCE_VERSION = '1.0-reference-12m'
CALIBRATION_PATH = Path(__file__).resolve().parents[1] / 'models/artifacts/tiered_calibration.json'
TIERS = {'A': 'data_supported_xgboost', 'B': 'limited_history_estimate',
         'C': 'zero_history_reference', 'D': 'missing_environment_estimate'}
WEATHER = ['rainfall_current', 'temperature', 'evapotranspiration']


def observations(frame, cutoff):
    """Counts are genuine district-month aggregates, not numbers of wells."""
    values = pd.to_numeric(frame.gwl_current, errors='coerce')
    valid = observed_mask(frame) & np.isfinite(values) & values.ge(0) & frame.date.le(_completed_feature_month(cutoff))
    if 'is_imputed' in frame:
        valid &= frame.is_imputed.astype('string').str.lower().isin(['false', '0'])
    return frame.loc[valid].sort_values('date').copy()


def readiness(frame, cutoff):
    hist = observations(frame, cutoff)
    end = _completed_feature_month(cutoff)
    start = hist.date.min() if len(hist) else None
    span = (hist.date.max().year-start.year)*12+hist.date.max().month-start.month if start is not None else 0
    elapsed = (end.year-start.year)*12+end.month-start.month+1 if start is not None else 0
    expected = max(1, int(np.ceil(elapsed/3)))
    age = (cutoff.year-hist.date.max().year)*12+cutoff.month-hist.date.max().month if len(hist) else None
    return {'observed_months': len(hist), 'observation_count_unit': 'source_marked_district_months',
            'monitoring_start': start.date().isoformat() if start is not None else None,
            'expected_monitoring_rounds': expected if len(hist) else 0,
            'readiness_score': round(min(100., 100*len(hist)/expected), 1),
            'observation_interval_months': 3, 'span_months': span, 'data_age_months': age,
            'anchor_count_satisfied': len(hist) >= MIN_OBSERVATIONS,
            'anchor_span_satisfied': span >= MIN_SPAN_MONTHS,
            'eligible': len(hist) >= MIN_OBSERVATIONS and span >= MIN_SPAN_MONTHS,
            'policy': 'Monitoring coverage is descriptive; XGBoost requires a successful 24-observation/36-month anchor fit and origin-available weather.'}


class RegionalReference:
    """Fit on a trailing ten-year donor window; weight districts equally.

    Two donors are needed for a regional distribution. Single-donor/no-donor
    states use the global reference. This is a reference estimate, not inferred
    local geology or a nearest-neighbor assignment.
    """
    def __init__(self, frame, cutoff):
        self.cutoff = _as_of(cutoff)
        obs = observations(frame, self.cutoff)
        obs = obs.loc[obs.date >= _completed_feature_month(self.cutoff)-pd.DateOffset(years=10)]
        if obs.empty:
            raise ValueError('No genuine past observations for a national reference; publication must fail.')
        self.obs = obs[['district_id', 'date', 'gwl_current']].copy()
        self.obs['month'] = self.obs.date.dt.month
        self.monthly = self.obs.groupby(['district_id', 'month']).gwl_current.median().unstack('month')
        self.annual = self.obs.groupby('district_id').gwl_current.median()
        self.latest = self.obs.groupby('district_id').date.max()
        self._cache = {}

    def distribution(self, district_id, month, *, global_only=False):
        key = (district_id, month, global_only)
        if key in self._cache:
            return self._cache[key]
        pool = self.annual.index[self.annual.index != district_id]
        regional = pool[pool.str.startswith(district_id[:3])]
        scope = 'state' if len(regional) >= 2 and not global_only else 'global'
        ids = regional if scope == 'state' else pool
        if len(ids) == 0:
            raise ValueError('Reference cannot use target history or an empty donor panel.')
        values = self.monthly.reindex(ids).get(month, pd.Series(np.nan, index=ids))
        phase_missing = values.isna()
        # Missing seasonal phases use that donor's observed-window median as an
        # estimate, never as a new observation or a monthly training label.
        values = values.fillna(self.annual.reindex(ids))
        result = values.to_numpy(float), {'scope': scope, 'donor_districts': len(ids),
            'donor_ids_sha256': hashlib.sha256('|'.join(sorted(ids)).encode()).hexdigest(),
            'donors_without_target_phase': int(phase_missing.sum()),
            'latest_donor_observation': self.latest.reindex(ids).max().date().isoformat(),
            'target_district_excluded': True, 'window_years': 10}
        self._cache[key] = result
        return result

    def predict(self, district_id, months, history, *, method='reference'):
        vals, metadata = [], []
        for month in pd.DatetimeIndex(months).month:
            dist, meta = self.distribution(district_id, month)
            vals.append(float(np.median(dist))); metadata.append(meta)
        if len(history):
            last = history.iloc[-1]
            anchor_dist, _ = self.distribution(district_id, last.date.month)
            anchored = np.maximum(0., float(last.gwl_current)+np.asarray(vals)-np.median(anchor_dist))
            if method == 'persistence':
                vals = [float(last.gwl_current)]*len(months)
            else:
                vals = anchored.tolist()
        return np.asarray(vals), metadata


def load_calibration(cutoff, *, path=None, generation=None, bundle=None):
    calibration_path = Path(path) if path is not None else CALIBRATION_PATH
    if not calibration_path.exists():
        return None
    card = json.loads(calibration_path.read_text(encoding='utf-8'))
    if card.get('pipeline_version') != VERSION or pd.Timestamp(card['max_calibration_target']) > _completed_feature_month(cutoff):
        return None
    from models.climate_forecast_12m import load_bundle
    from models.ensemble import feature_generation
    expected_generation = generation if generation is not None else feature_generation()
    verified_bundle = bundle if bundle is not None else load_bundle(expected_generation=card['feature_generation_id'])
    if (card.get('feature_generation_id') != expected_generation
            or card.get('xgboost_sha256') != verified_bundle[1]['model_sha256']
            or verified_bundle[1].get('feature_generation_id') != expected_generation):
        raise ValueError('Calibration identity is incompatible with feature/model inputs.')
    return card


def forecast_district(district_id, frame, cutoff, generation, bundle, reference, *, calibration=None):
    cutoff = _as_of(cutoff); origin = cutoff.to_period('M').to_timestamp()
    # Per-source manifests can be large. Pandas propagates/deep-copies attrs on
    # each column operation; provenance is already passed explicitly below.
    # Drop only local metadata, preserving the caller's immutable snapshot.
    frame = frame.copy(deep=False)
    frame.attrs = {}
    frame = frame.loc[frame.date.le(_completed_feature_month(cutoff))].copy()
    hist = observations(frame, cutoff)
    ready = readiness(frame, cutoff)
    fit = fit_projection(hist, cutoff)
    reason = 'No locally mapped genuine groundwater observations.' if hist.empty else 'Insufficient observations or temporal span for the XGBoost anchor fit.'
    result = None
    if fit is not None:
        evidence = dict(district_id=district_id, as_of=cutoff, generation=generation,
            frame=frame, history=hist, estimate_type='district_level', zone=None,
            reason=None, readiness=ready, origin=hist.date.max())
        # Bundle incompatibility is a generation failure, never disguised as low evidence.
        if cutoff < pd.Timestamp(bundle[1]['train_target_cutoff']):
            raise ValueError('XGBoost artifact was trained after requested forecast origin.')
        result = climate.forecast_from_evidence(evidence, _verified_bundle=bundle)
        if result['status'] == 'model_unavailable':
            raise RuntimeError('Verified XGBoost artifact unavailable during generation.')
        reason = result.get('message')
    if result is not None and result['status'] == 'forecast':
        tier, method = 'A', 'climate_conditioned_xgboost_12m'
    else:
        tier = 'C' if hist.empty else 'D' if fit is not None else 'B'
        # Persistence is the deliberately conservative sparse-history policy.
        # Regional seasonal transfer is evaluated alongside it, not selected on test.
        method = 'regional_seasonal_reference' if tier == 'C' else 'local_persistence'
        months = pd.date_range(origin+pd.offsets.MonthBegin(1), periods=12, freq='MS')
        predicted, donors = reference.predict(district_id, months, hist, method='persistence' if len(hist) else 'reference')
        anchor = float(hist.iloc[-1].gwl_current) if len(hist) else float(reference.predict(district_id, [origin], hist)[0][0])
        result = dict(product=climate.PRODUCT_NAME, model_version=REFERENCE_VERSION,
            district_id=district_id, status='forecast', forecast_origin=origin.date().isoformat(),
            as_of=cutoff.date().isoformat(), timezone='Asia/Kolkata', horizon_months=12,
            forecast_start=months[0].strftime('%Y-%m'), forecast_end=months[-1].strftime('%Y-%m'),
            units='m_bgl', estimated_current_gwl=round(anchor, 4),
            current_depth_basis='last_local_observation' if len(hist) else 'regional_reference',
            last_observed_date=hist.iloc[-1].date.date().isoformat() if len(hist) else None,
            last_observed_gwl=anchor if len(hist) else None, data_age_months=ready['data_age_months'],
            estimate_type='district_level' if len(hist) else 'regional_reference',
            feature_generation=generation, projection_method=method,
            computed_at=datetime.now(timezone.utc).isoformat(),
            weather_basis={'method': 'not_used', 'description': 'This reference method does not consume environmental predictors.'},
            forecast=[dict(horizon=h, date=m.date().isoformat(), month=m.strftime('%Y-%m'),
                predicted_gwl=round(float(p), 4), delta_from_current_m=round(float(p-anchor), 4),
                weather={k: None for k in ['rainfall_mm','temperature_c','evapotranspiration_mm']},
                reference_basis=donors[h-1] if not len(hist) else None)
                for h,(m,p) in enumerate(zip(months,predicted),1)],
            limitations=['Low-evidence reference estimate; target-specific forecast skill is not established.',
                'State membership is a coarse reference group, not an aquifer or spatial similarity claim.',
                'Monthly source flags do not establish provider publication time or stable well panels.'])
    result.update(forecast_origin=origin.date().isoformat(), pipeline_version=VERSION,
        evidence_tier=tier, evidence_status=TIERS[tier], forecast_method=method,
        observation_count=len(hist), data_readiness=ready, fallback_reason=reason if tier!='A' else None,
        warning=('Current-period XGBoost skill after the observation gap is unverified.' if tier=='A' else
                 'No local groundwater observations: regional/global reference only.' if tier=='C' else
                 'Limited evidence: last genuine local depth held constant; seasonal change is not resolved.'),
        input_completeness={k: int(np.isfinite(pd.to_numeric(frame[k], errors='coerce')).sum()) for k in WEATHER},
        input_missingness={k: bool(frame.empty or not np.isfinite(pd.to_numeric(frame[k], errors='coerce')).any()) for k in WEATHER},
        environmental_history={k: {'latest_usable_date': (frame.loc[np.isfinite(pd.to_numeric(frame[k],errors='coerce')), 'date'].max().date().isoformat()
            if np.isfinite(pd.to_numeric(frame[k],errors='coerce')).any() else None),
            'available_fraction': float(np.isfinite(pd.to_numeric(frame[k],errors='coerce')).mean()) if len(frame) else 0.} for k in WEATHER},
        uncertainty={'status': 'unavailable', 'reason': 'No independent pre-origin calibration for this method/horizon.'})
    return attach_error_bands(result, calibration, cutoff,
        evidence=load_validation_evidence() if calibration else None)


def validate_complete_generation(identity, districts, states=None, summary=None):
    expected = set(identity['districts'])
    if set(districts) != expected or len(districts) != len(expected):
        raise ValueError('Generation district IDs differ from canonical registry.')
    origin = pd.Timestamp(identity['forecast_origin'])
    months = pd.date_range(origin+pd.offsets.MonthBegin(1),periods=12,freq='MS')
    for did,res in districts.items():
        validate_disclosure(res)
        if (res.get('status')!='forecast' or res.get('district_id')!=did or res.get('units')!='m_bgl'
                or res.get('evidence_tier') not in TIERS or len(res.get('forecast',[]))!=12
                or res.get('as_of') != str(identity['as_of']) or res.get('forecast_origin') != origin.date().isoformat()
                or res.get('generation_id') != identity['generation_id']):
            raise ValueError(f'Incomplete or invalid district output: {did}')
        tier=res['evidence_tier']
        method='climate_conditioned_xgboost_12m' if tier=='A' else 'regional_seasonal_reference' if tier=='C' else 'local_persistence'
        if res.get('forecast_method')!=method or (tier=='C') != (res.get('observation_count')==0):
            raise ValueError('Invalid method/evidence contract.')
        count=res.get('observation_count')
        if isinstance(count,bool) or not isinstance(count,int) or count<0:
            raise ValueError('Invalid genuine observation count.')
        if (tier=='C' and (res.get('last_observed_date') is not None or res.get('last_observed_gwl') is not None)
                or tier!='C' and (not res.get('last_observed_date') or pd.Timestamp(res['last_observed_date'])>_completed_feature_month(pd.Timestamp(identity['as_of'])))):
            raise ValueError('Invalid local observation provenance.')
        if tier!='A' and res.get('model_version')!=REFERENCE_VERSION:
            raise ValueError('Reference model identity mismatch.')
        if tier=='A' and (res.get('model_sha256')!=identity['model_sha256'] or res.get('model_version')!=climate.MODEL_VERSION):
            raise ValueError('XGBoost model identity mismatch.')
        for h,(row,month) in enumerate(zip(res['forecast'],months),1):
            depth=row.get('predicted_gwl'); delta=row.get('delta_from_current_m'); anchor=res.get('estimated_current_gwl')
            if (row.get('horizon')!=h or row.get('date')!=month.date().isoformat() or row.get('month')!=month.strftime('%Y-%m')
                    or isinstance(depth,bool) or not isinstance(depth,(int,float)) or not np.isfinite(depth) or depth<0
                    or not isinstance(delta,(int,float)) or not np.isfinite(delta)
                    or not isinstance(anchor,(int,float)) or not np.isfinite(anchor) or anchor<0
                    or abs(delta-(depth-anchor))>.001):
                raise ValueError(f'Invalid calendar/depth: {did} M+{h}')
            if 'lower_gwl' in row and not (np.isfinite(row['lower_gwl']) and np.isfinite(row['upper_gwl']) and 0<=row['lower_gwl']<=depth<=row['upper_gwl']):
                raise ValueError('Invalid uncertainty interval.')
            weather=row.get('weather',{})
            vals=[weather.get(k) for k in ['rainfall_mm','temperature_c','evapotranspiration_mm']]
            if tier=='A':
                if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not np.isfinite(v) for v in vals):
                    raise ValueError('XGBoost requires finite environmental features.')
            elif any(v is not None for v in vals):
                raise ValueError('Reference methods must not invent environmental features.')
    if states is not None:
        from models.state_mapping import STATES_REGISTRY
        if set(states)!=set(STATES_REGISTRY):
            raise ValueError('Incomplete state generation.')
        for sid,res in states.items():
            ids=sorted(d for d in expected if d.startswith(sid+'-'))
            counts=dict(Counter(districts[d]['evidence_tier'] for d in ids))
            if (res.get('districts')!=ids or res.get('contributing_district_ids')!=ids or res.get('evidence_tier_counts')!=counts
                    or res.get('generation_id')!=identity['generation_id'] or len(res.get('forecast',[]))!=12
                    or res.get('status')!='forecast' or res.get('units')!='m_bgl' or res.get('as_of')!=str(identity['as_of'])
                    or res.get('forecast_origin')!=origin.date().isoformat() or res.get('horizon_months')!=12
                    or res.get('aggregation_method')!='equal_weight_all_registered_districts'
                    or res.get('total_districts_in_state')!=len(ids) or res.get('contributing_districts_count')!=len(ids)):
                raise ValueError('Invalid state panel or evidence counts.')
            expected_anchor=np.mean([districts[d]['estimated_current_gwl'] for d in ids])
            if abs(res['estimated_current_gwl_m_bgl']-expected_anchor)>.0002:
                raise ValueError('Invalid state anchor.')
            for h,row in enumerate(res['forecast']):
                mean=np.mean([districts[d]['forecast'][h]['predicted_gwl'] for d in ids])
                if (not np.isfinite(row['predicted_gwl']) or abs(row['predicted_gwl']-mean)>.0002
                        or row['target_date']!=months[h].date().isoformat() or row.get('horizon')!=h+1
                        or not np.isfinite(row['delta_from_current_m'])
                        or abs(row['delta_from_current_m']-(mean-expected_anchor))>.0002):
                    raise ValueError('State aggregation mismatch.')
    if summary is not None and (summary.get('generation_id')!=identity['generation_id']
            or summary.get('districts_total')!=len(expected) or summary.get('districts_forecast')!=len(expected)
            or summary.get('evidence_tier_counts')!=dict(Counter(r['evidence_tier'] for r in districts.values()))):
        raise ValueError('Invalid nationwide summary.')
    if summary is not None and states is not None:
        rows=summary.get('states',[])
        if len(rows)!=len(states) or {r['state_id'] for r in rows}!=set(states):
            raise ValueError('Incomplete summary states.')
        for row in rows:
            state=states[row['state_id']]
            if row.get('evidence_tier_counts')!=state['evidence_tier_counts'] or row.get('forecast_12m_gwl_m_bgl')!=state['forecast'][-1]['predicted_gwl']:
                raise ValueError('State summary differs from state output.')
    return {'districts':len(districts),'horizons':12*len(districts),'tier_counts':dict(Counter(r['evidence_tier'] for r in districts.values()))}
