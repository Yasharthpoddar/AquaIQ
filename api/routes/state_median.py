"""Versioned primary States APIs; legacy /api state and district routes stay intact."""
from datetime import date, datetime, timezone
import re

from flask import Blueprint, request

from api.contracts import response, failure, parse_as_of_value
from models.district_registry import get_registry
from models.state_mapping import STATES_REGISTRY, resolve_state_id
from models import state_median_release_storage as releases
from models.state_median_storage import (MODEL_NAME, MODEL_VERSION, PRODUCT_NAME,
    TIERED_MODEL_NAME, TIERED_MODEL_VERSION, POLICY_VERSION)

state_median_bp = Blueprint('state_median', __name__)


def _query():
    allowed = {'as_of','generation_id','horizon','model'}
    if set(request.args)-allowed or any(len(request.args.getlist(key)) != 1 for key in request.args):
        raise ValueError('Unsupported or repeated state forecast query parameter.')
    try:
        horizon = int(request.args.get('horizon', '12'))
    except (ValueError, TypeError):
        raise ValueError('horizon must be an integer equal to 12.') from None
    if horizon != 12:
        raise ValueError('Only horizon=12 is supported.')
    if request.args.get('model') not in (None,'median_xgboost','median_tiered'):
        raise ValueError('The v2 States API supports median_tiered and pinned legacy median_xgboost releases.')
    as_of = request.args.get('as_of')
    if as_of is not None:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', as_of):
            raise ValueError('as_of must be YYYY-MM-DD.')
        as_of = parse_as_of_value(as_of)
    generation_id = request.args.get('generation_id')
    if generation_id is not None:
        generation_id = releases._uuid(generation_id)
    return as_of, generation_id


def _requested_model(value):
    requested = request.args.get('model')
    expected = {'median_xgboost':MODEL_NAME,'median_tiered':TIERED_MODEL_NAME}.get(requested)
    if value is not None and expected is not None and value.get('model_name') != expected:
        raise ValueError('Requested model does not match this published generation; choose an exact compatible generation UUID.')


def _missing_state(code, as_of=None, generation_id=None, storage_failure=False):
    cutoff = as_of or date.today()
    total = sum(row['state_id']==code for row in get_registry())
    return dict(product=PRODUCT_NAME,model_name=TIERED_MODEL_NAME,model_version=TIERED_MODEL_VERSION,
        policy_version=POLICY_VERSION,policy_sha256=None,forecast_method=None,
        genuine_observed_months=None,genuine_observation_count=None,
        latest_observation_date=None,observation_age_months=None,reference_age_months=None,
        reference_observation=None,reference_training_eligible=None,fallback_reason=None,
        promotion_status='experimental',publication_status='unavailable',artifact_release=None,
        generation_id=generation_id,release_id=generation_id,state_id=code,
        state_name=STATES_REGISTRY[code]['name'],as_of=cutoff.isoformat(),
        forecast_origin=cutoff.replace(day=1).isoformat(),computed_at=datetime.now(timezone.utc).isoformat(),
        training_cutoff=None,model_sha256=None,status='model_unavailable',horizon_months=12,units='m_bgl',
        total_districts_in_state=total,contributing_districts_count=0,district_coverage_pct=0.,history=[],forecast=[],
        historical_reference_date=None,last_observed_gwl_m_bgl=None,
        unavailable_reason='median_release_storage_unavailable' if storage_failure else 'median_publication_missing',
        message='No published median States release is available for the requested vintage. '
                'A verified complete release must be staged and published before serving.',
        evaluation=dict(status='not_evaluated',n=0,mae_m=None,rmse_m=None,period_start=None,period_end=None,
                        description='No release-specific held-out evaluation is available.'))


@state_median_bp.route('/v2/states')
def states_registry():
    """Navigation remains available even before the first median publication."""
    try:
        as_of, generation_id = _query()
        try:
            summary = releases.get_published_summary(as_of,generation_id)
        except Exception:
            summary = None
        _requested_model(summary)
        registry = get_registry()
        states = [dict(state_id=code,state_name=meta['name'],state_type=meta['type'],st_code=meta['st_code'],
                       total_districts=sum(row['state_id']==code for row in registry),
                       districts=[row['district_id'] for row in registry if row['state_id']==code])
                  for code,meta in sorted(STATES_REGISTRY.items(),key=lambda pair:pair[1]['name'])]
        return response(dict(total=len(states),states=states,horizon_months=12,
            model_name=summary['model_name'] if summary else TIERED_MODEL_NAME,
            model_version=summary['model_version'] if summary else TIERED_MODEL_VERSION,
            as_of=summary['as_of'] if summary else None,
            generation_id=summary['generation_id'] if summary else None,
            artifact_release=summary['artifact_release'] if summary else None,
            publication_status='published' if summary else 'unavailable'))
    except Exception as error:
        return failure(error)


@state_median_bp.route('/v2/states/summary')
def states_summary():
    try:
        as_of, generation_id = _query()
        try:
            summary = releases.get_published_summary_statistics(as_of,generation_id)
        except Exception:
            summary = None
        _requested_model(summary)
        if summary is None:
            return response(dict(product=releases.SUMMARY_PRODUCT,status='model_unavailable',
                model_name=TIERED_MODEL_NAME,model_version=TIERED_MODEL_VERSION,promotion_status='experimental',
                horizon_months=12,as_of=as_of.isoformat() if as_of else None,generation_id=generation_id,
                states=[],message='No published median States release is available for this vintage.'),503)
        return response(summary)
    except Exception as error:
        return failure(error)


@state_median_bp.route('/v2/history/state/<state_id>')
def state_history(state_id):
    """Supplement the saved forecast window using its exact verified source."""
    try:
        as_of,generation_id = _query()
        code = resolve_state_id(state_id)
        try:
            context = releases.get_published_state_context(code,as_of,generation_id)
        except Exception:
            context = None
        if context is None:
            return response(dict(product='state_median_groundwater_history',status='model_unavailable',
                state_id=code,requested_state_id=state_id,resolved_state_id=code,
                generation_id=generation_id,as_of=as_of.isoformat() if as_of else None,history=[],
                unavailable_reason='median_publication_missing',
                message='No published state median release is available for this historical request.'),503)
        forecast,manifest = context['forecast'],context['manifest']
        _requested_model(forecast)
        try:
            from models.state_median_history import get_full_state_history
            payload = get_full_state_history(code,forecast,manifest)
        except Exception:
            return response(dict(product='state_median_groundwater_history',status='model_unavailable',
                state_id=code,requested_state_id=state_id,resolved_state_id=code,
                generation_id=forecast['generation_id'],as_of=forecast['as_of'],history=[],
                unavailable_reason='historical_source_unavailable',
                message='Full observed state history is unavailable for the selected published source. '
                        'The forecast retains its separately labelled saved historical window.'),503)
        payload.update(requested_state_id=state_id,resolved_state_id=code)
        return response(payload)
    except Exception as error:
        return failure(error)


@state_median_bp.route('/v2/predict/state/<state_id>')
def state_prediction(state_id):
    try:
        as_of, generation_id = _query()
        code = resolve_state_id(state_id)
        storage_failure = False
        try:
            payload = releases.get_published_state_forecast(code,as_of,generation_id)
        except Exception:
            payload = None
            storage_failure = True
        if payload is None:
            payload = _missing_state(code,as_of,generation_id,storage_failure)
        else:
            _requested_model(payload)
        payload.update(requested_state_id=state_id,resolved_state_id=code)
        return response(payload,503 if payload['status']=='model_unavailable' else 200)
    except Exception as error:
        return failure(error)
