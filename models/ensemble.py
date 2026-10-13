"""Causal scoring from observed district or explicit zone evidence.

Missing evidence is unavailable. A trained six-month endpoint is never
expanded into unvalidated monthly or calendar-year curves.
"""
import json
import hashlib
import math
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd
import yaml
from threading import local
from db.connection import get_connection, read_frame, finite_json
from models.tiers import score_to_tier

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / 'config.yaml').read_text(encoding='utf-8'))
NUMERIC_FEATURES = ['gwl_current','gwl_lag_3mo','gwl_lag_6mo','rainfall_current',
    'rainfall_3mo_avg','monsoon_deficit_pct','temperature','evapotranspiration','water_balance_proxy']
_BUNDLE_CACHE = {}
_FUZZY_CONTEXT = local()


def _as_of(value=None):
    cutoff = pd.Timestamp(value or date.today()).normalize()
    if cutoff > pd.Timestamp(date.today()):
        raise ValueError('as_of cannot be in the future.')
    return cutoff


def _completed_feature_month(cutoff):
    """Monthly aggregates are available only after their calendar month ends."""
    month = cutoff.to_period('M')
    return month.to_timestamp() if cutoff >= month.end_time.normalize() else (month-1).to_timestamp()


def feature_generation():
    manifest = json.loads((ROOT / 'data/processed/feature_manifest.json').read_text(encoding='utf-8'))
    generation = manifest.get('generation_id')
    if not generation or not generation.startswith('physical-v3-causal-monthly-'):
        raise RuntimeError('Physical feature generation has not been rebuilt.')
    return generation


def _load_bundle():
    from models.xgboost_model import load_model_bundle
    checkpoint = ROOT / CONFIG['paths']['xgboost_checkpoint']
    generation = feature_generation()
    try:
        stat = checkpoint.stat()
        manifest = json.loads(checkpoint.read_text(encoding='utf-8'))
        assets = []
        for name in ('model_path','card_path'):
            asset = (checkpoint.parent / manifest[name]).resolve()
            if not asset.is_relative_to(checkpoint.parent.resolve()):
                raise ValueError('Model asset path escapes checkpoint directory.')
            asset_stat = asset.stat()
            assets.append((str(asset),asset_stat.st_mtime_ns,asset_stat.st_size))
        key = (str(checkpoint), stat.st_mtime_ns, stat.st_size, generation, tuple(assets))
    except (OSError,KeyError,ValueError) as error:
        raise RuntimeError('Model bundle is unavailable or incompatible.') from error
    if key not in _BUNDLE_CACHE:
        _BUNDLE_CACHE.clear()
        try:
            _BUNDLE_CACHE[key] = load_model_bundle(checkpoint, expected_generation=generation)
        except ValueError as error:
            raise RuntimeError('Model bundle is unavailable or incompatible.') from error
    return _BUNDLE_CACHE[key]


def _load_xgb_model():
    return _load_bundle()[0]


def _safe_float(value, default=np.nan):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (ValueError, TypeError):
        return default


def _build_feature_row(row, season=None):
    season = season or row.get('crop_season_flag')
    if season not in ('Kharif','Rabi','Zaid'):
        raise ValueError('Feature crop season is missing or invalid.')
    return [_safe_float(row.get(column)) for column in NUMERIC_FEATURES] + [float(season == s) for s in ('Kharif','Rabi','Zaid')]


def depth_to_score(depth):
    """Project-defined depth risk scale; depth is metres below ground level."""
    depth = _safe_float(depth)
    if not np.isfinite(depth):
        return None
    if depth <= 5:
        return max(0., depth * 6.)
    if depth <= 10:
        return 30. + (depth - 5.) * 6.
    if depth <= 20:
        return 60. + (depth - 10.) * 2.
    return min(100., 80. + depth - 20.)


def _load_ensemble_weights():
    settings = yaml.safe_load((ROOT / 'config.yaml').read_text(encoding='utf-8'))['model_hyperparameters']['ensemble']
    # A historical proxy fit is not a calibration of this serving pipeline.
    raw = settings.get('validated_weights') or settings['initial_weights']
    keys = ('linear_regression_trend','xgboost_risk','drought_frequency','fuzzy_logic')
    weights = {key: float(raw.get(key,0.)) for key in keys}
    total = sum(weights.values())
    if total <= 0 or any(not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError('Ensemble weights must be finite, nonnegative, and have positive total.')
    return {key:value/total for key,value in weights.items()}


def scoring_signature():
    settings = yaml.safe_load((ROOT/'config.yaml').read_text(encoding='utf-8'))
    digest = hashlib.sha256(json.dumps({'weights':_load_ensemble_weights(),
        'crisis_score':settings['crisis_score']},sort_keys=True).encode())
    for name in ('ensemble.py','fuzzy_logic.py','tiers.py'):
        digest.update((ROOT/'models'/name).read_bytes())
    return digest.hexdigest()


def _gwl_series(history):
    if isinstance(history, pd.DataFrame):
        values = pd.to_numeric(history.gwl_current, errors='coerce')
        index = pd.to_datetime(history.date)
        series = pd.Series(values.to_numpy(), index=index)
    else:
        series = pd.to_numeric(history,errors='coerce').copy()
    return series[np.isfinite(series)].sort_index()


def lr_trend_score(history):
    series = _gwl_series(history)
    if len(series) < 6:
        return None
    if isinstance(series.index,pd.DatetimeIndex):
        x = np.array([d.year*12+d.month for d in series.index],dtype=float)
    else:
        x = np.arange(len(series),dtype=float)
    slope = np.polyfit(x-x.min(), series.to_numpy(),1)[0]
    return float(np.clip(50. + slope*12.*50., 0.,100.))


def compute_drought_frequency(district_id, history):
    series = _gwl_series(history)
    if len(series) < 24:
        return None
    baseline = series.iloc[:min(len(series),216)]
    threshold = baseline.quantile(.8)
    recent = series.tail(min(len(series),36))
    return float((recent > threshold).mean()*100.)


def compute_fuzzy_score(rainfall_deficit, depletion_rate):
    if not all(np.isfinite(_safe_float(v)) for v in (rainfall_deficit,depletion_rate)):
        return None
    from models.fuzzy_logic import build_fuzzy_system, compute_crisis_score as fis_score
    if not hasattr(_FUZZY_CONTEXT,'simulation'):
        _FUZZY_CONTEXT.simulation = build_fuzzy_system()[0]
    simulation = _FUZZY_CONTEXT.simulation
    value, _ = fis_score(simulation, float(np.clip(rainfall_deficit,0,100)),float(np.clip(depletion_rate,0,15)))
    if not np.isfinite(value):
        raise ValueError('Fuzzy inference produced a non-finite result.')
    return float(value)


def components_from_history(history, predicted_depth=None):
    if isinstance(history,pd.DataFrame) and 'is_observed' in history:
        from models.xgboost_model import observed_mask
        history = history.loc[observed_mask(history)].copy()
    series = _gwl_series(history)
    if series.empty:
        return {key:None for key in ('lr_trend','xgb_risk','drought_frequency','fuzzy_logic')}
    current = float(series.iloc[-1])
    xgb = depth_to_score(.6*current + .4*predicted_depth) if predicted_depth is not None and np.isfinite(predicted_depth) else None
    fuzzy = None
    if isinstance(history,pd.DataFrame) and isinstance(series.index,pd.DatetimeIndex):
        last = series.index[-1]
        prior = last - pd.DateOffset(months=12)
        deficit_rows = history[pd.to_datetime(history.date) == last]
        anomaly = _safe_float(deficit_rows.iloc[-1].get('monsoon_deficit_pct')) if len(deficit_rows) else np.nan
        if prior in series.index and np.isfinite(anomaly):
            fuzzy = compute_fuzzy_score(max(0.,-anomaly),max(0.,(current-float(series.loc[prior]))*100.))
    return {'lr_trend':lr_trend_score(series),'xgb_risk':xgb,
        'drought_frequency':compute_drought_frequency('',series),'fuzzy_logic':fuzzy}


def blend_components(components, weights=None):
    weights = weights or _load_ensemble_weights()
    mapping = {'linear_regression_trend':'lr_trend','xgboost_risk':'xgb_risk','drought_frequency':'drought_frequency','fuzzy_logic':'fuzzy_logic'}
    active = {key:weight for key,weight in weights.items() if components.get(mapping[key]) is not None and weight > 0}
    if not active:
        return None, {}
    total = sum(active.values())
    normalized = {key:weight/total for key,weight in active.items()}
    value = sum(components[mapping[key]]*weight for key,weight in normalized.items())
    return round(float(np.clip(value,0,100))), normalized


def _readiness(frame, cutoff):
    observed = frame[frame.is_observed.fillna(False) & np.isfinite(pd.to_numeric(frame.gwl_current,errors='coerce'))]
    start = pd.Timestamp(CONFIG['date_range']['start'])
    end = min(cutoff,pd.Timestamp(CONFIG['date_range']['end']))
    interval = CONFIG.get('crisis_score',{}).get('observation_interval_months',3)
    months = max(1,(end.year-start.year)*12+end.month-start.month+1)
    expected = math.ceil(months/interval)
    count = observed.date.nunique()
    pct = min(100.,100.*count/expected)
    minimum = CONFIG['crisis_score']['fallback_strategy']['min_months_required']
    return {'observed_months':count,'expected_monitoring_rounds':expected,'observation_interval_months':interval,
        'readiness_score':round(pct,1),'eligible':count>=minimum and pct>=CONFIG['crisis_score']['data_readiness_min_pct']}


def select_evidence(district_id, as_of=None, conn=None, zone_cache=None):
    cutoff = _as_of(as_of)
    available_month = _completed_feature_month(cutoff)
    generation = feature_generation()
    own = conn is None
    conn = conn or get_connection()
    try:
        meta = read_frame('SELECT district_id,district_name,state,agro_climatic_zone FROM districts WHERE district_id=%s',conn,(district_id,))
        if meta.empty:
            raise LookupError('Unknown canonical district ID.')
        frame = read_frame('SELECT * FROM features WHERE district_id=%s AND date<=%s AND feature_generation=%s ORDER BY date',conn,(district_id,available_month.date(),generation))
        if not frame.empty:
            frame['date'] = pd.to_datetime(frame.date)
        else:
            frame = pd.DataFrame(columns=['date','is_observed','gwl_current'])
        readiness = _readiness(frame,cutoff)
        zone = meta.iloc[0].agro_climatic_zone
        estimate = 'district_level'
        reason = None
        if not readiness['eligible']:
            estimate = 'zone_fallback'
            reason = f"District has {readiness['observed_months']} observed months and {readiness['readiness_score']}% monitoring-round coverage."
            if zone:
                expressions = ','.join(f"AVG(f.{column}) {'FILTER(WHERE f.is_observed)' if column=='gwl_current' else ''} AS {column}" for column in NUMERIC_FEATURES)
                cache_key=(zone,cutoff.isoformat(),generation)
                frame = zone_cache.get(cache_key) if zone_cache is not None else None
                if frame is None:
                    frame = read_frame(f'''SELECT f.date,{expressions},
                    BOOL_OR(f.is_observed) AS is_observed, BOOL_AND(f.is_imputed) AS is_imputed,
                    COUNT(DISTINCT f.district_id) FILTER(WHERE f.is_observed) AS reporting_districts
                    FROM features f JOIN districts d ON d.district_id=f.district_id
                    WHERE d.agro_climatic_zone=%s AND f.date<=%s AND f.feature_generation=%s
                    GROUP BY f.date ORDER BY f.date''',conn,(zone,available_month.date(),generation))
                    if zone_cache is not None:
                        zone_cache[cache_key]=frame
                frame=frame.copy()
                frame['date'] = pd.to_datetime(frame.date)
                original_gwl = pd.to_numeric(frame.gwl_current,errors='coerce')
                frame['gwl_current'] = original_gwl.ffill(limit=3)
                frame['is_imputed'] = original_gwl.isna() & frame.gwl_current.notna()
                for lag in (3,6):
                    frame[f'gwl_lag_{lag}mo'] = frame.gwl_current.shift(lag)
                frame['crop_season_flag'] = frame.date.dt.month.map(lambda m:'Kharif' if 6<=m<=10 else 'Rabi' if m in (11,12,1,2,3) else 'Zaid')
            zone_ready = _readiness(frame,cutoff)
            readiness['zone_readiness'] = zone_ready
            if not zone or not zone_ready['eligible']:
                estimate = 'insufficient_data'
                reason += ' The zone also lacks enough observed history.'
        observed = frame[frame.is_observed.fillna(False) & np.isfinite(pd.to_numeric(frame.gwl_current,errors='coerce'))].copy()
        origin = pd.Timestamp(observed.date.max()) if len(observed) else None
        return {'district_id':district_id,'as_of':cutoff,'generation':generation,'frame':frame,
            'history':observed,'origin':origin,'estimate_type':estimate,'zone':zone if estimate=='zone_fallback' else None,
            'reason':reason,'readiness':readiness}
    finally:
        if own:
            conn.close()


def forecast_from_evidence(evidence, feature_override=None):
    origin = evidence['origin']
    result = {'district_id':evidence['district_id'],'status':'insufficient_data','forecast':[],
        'estimate_type':evidence['estimate_type'],'zone_fallback_reason':evidence['reason'],
        'source_zone':evidence['zone'],'as_of':evidence['as_of'].date().isoformat(),
        'last_observed_date':origin.date().isoformat() if origin is not None else None,
        'forecast_origin':origin.date().isoformat() if origin is not None else None,
        'observation_month_completed_on':(origin+pd.offsets.MonthEnd(0)).date().isoformat() if origin is not None else None,
        'feature_generation':evidence['generation'],'projection_method':'direct_xgboost_6_month_endpoint',
        'horizon_months':6,'data_age_months':None,'model_version':None}
    if evidence['estimate_type']=='insufficient_data' or origin is None:
        return result
    model, card = _load_bundle()
    result['model_version'] = card['version']
    result['model_sha256'] = card.get('model_sha256')
    result['model_validation'] = card.get('validation_assessment',{'status':'unassessed'})
    trained_through = pd.Timestamp(card['train_target_cutoff'])
    if origin < trained_through:
        result.update(status='unavailable',message='This checkpoint was trained after the requested observation origin; causal forecast unavailable.')
        return result
    row = evidence['frame'][evidence['frame'].date==origin].iloc[-1].copy()
    if feature_override:
        for key,value in feature_override.items():
            row[key] = value
    values = pd.DataFrame([_build_feature_row(row)],columns=card['features'],dtype=float)
    predicted = float(model.predict(values)[0])
    if not np.isfinite(predicted) or predicted < 0:
        raise RuntimeError('Model produced an invalid groundwater depth.')
    target = origin + pd.DateOffset(months=6)
    age = (evidence['as_of'].year-origin.year)*12+evidence['as_of'].month-origin.month
    result.update(status='historical_forecast' if target < evidence['as_of'] else 'success',data_age_months=age,
        feature_cutoff=origin.date().isoformat(),forecast_start=target.strftime('%Y-%m'),
        forecast_horizon='6-month ahead endpoint',forecast=[{'month':target.strftime('%Y-%m'),'predicted_gwl':round(predicted,4)}])
    return result


def score_evidence(evidence, forecast=None):
    forecast = forecast or forecast_from_evidence(evidence)
    result = dict(forecast)
    result.update(crisis_score=None,tier=None,components={},ensemble_weights={},data_readiness=evidence['readiness'])
    if not forecast['forecast']:
        return result
    components = components_from_history(evidence['history'],forecast['forecast'][0]['predicted_gwl'])
    score, weights = blend_components(components)
    result.update(crisis_score=score,tier=score_to_tier(score) if score is not None else None,
        components=components,ensemble_weights=weights,weights_status='validated' if CONFIG['model_hyperparameters']['ensemble'].get('validated_weights') else 'initial_uncalibrated')
    return finite_json(result)


def compute_crisis_score(district_id, as_of=None, conn=None, zone_cache=None):
    evidence = select_evidence(district_id,as_of,conn,zone_cache)
    return score_evidence(evidence)


def forecast_result(district_id, as_of=None, conn=None):
    return compute_crisis_score(district_id,as_of,conn)


def get_model_components(district_id, as_of=None):
    return compute_crisis_score(district_id,as_of)['components']


def xgb_risk_score(district_id,conn=None,as_of=None):
    return compute_crisis_score(district_id,as_of,conn)['components'].get('xgb_risk')


def xgb_forecast_6mo(district_id,conn=None,target_year=None,start_month=None,n_months=6,as_of=None):
    if target_year or start_month or n_months!=6:
        raise ValueError('Only the validated six-month endpoint from available observed data is supported.')
    return forecast_result(district_id,None if as_of in (None,'today','last_observed') else as_of,conn)['forecast']


def main(argv=None):
    from models.score_all import main as batch_main
    batch_main(argv)


if __name__=='__main__':
    main()
