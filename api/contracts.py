"""Shared route validation and strict serialization."""
from datetime import date
import re
from flask import jsonify, request
from db.connection import finite_json

def response(value,status=200):
    return jsonify(finite_json(value)),status

def parse_as_of_value(value):
    """Validate the same calendar-date contract for query strings and JSON bodies."""
    if value in (None,'today','last_observed'):
        return date.today()
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        raise ValueError('as_of must be today, last_observed, or YYYY-MM-DD.')
    try:
        parsed=date.fromisoformat(value)
    except (ValueError,TypeError):
        raise ValueError('as_of must be today, last_observed, or YYYY-MM-DD.')
    if parsed>date.today():
        raise ValueError('as_of cannot be in the future.')
    return parsed

def parse_as_of():
    return parse_as_of_value(request.args.get('as_of'))

def parse_forecast_as_of():
    cutoff = parse_as_of()
    if 'as_of' not in request.args:
        from models.forecast_storage import latest_published_as_of
        return latest_published_as_of(cutoff) or cutoff
    return cutoff

def failure(error):
    if isinstance(error,LookupError):
        return response({'status':'not_found','error':str(error)},404)
    if isinstance(error,ValueError):
        return response({'status':'invalid_request','error':str(error)},400)
    return response({'status':'unavailable','error':'Data or model service is unavailable.'},503)
