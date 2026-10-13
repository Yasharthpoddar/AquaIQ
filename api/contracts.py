"""Shared route validation and strict serialization."""
from datetime import date
from flask import jsonify, request
from db.connection import finite_json

def response(value,status=200):
    return jsonify(finite_json(value)),status

def parse_as_of():
    value=request.args.get('as_of')
    if value in (None,'today','last_observed'):
        return date.today()
    try:
        parsed=date.fromisoformat(value)
    except (ValueError,TypeError):
        raise ValueError('as_of must be today, last_observed, or YYYY-MM-DD.')
    if parsed>date.today():
        raise ValueError('as_of cannot be in the future.')
    return parsed

def failure(error):
    if isinstance(error,LookupError):
        return response({'status':'not_found','error':str(error)},404)
    if isinstance(error,ValueError):
        return response({'status':'invalid_request','error':str(error)},400)
    return response({'status':'unavailable','error':'Data or model service is unavailable.'},503)
