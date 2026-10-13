"""Historical physical values, retaining observation/imputation provenance."""
from datetime import date
import pandas as pd
from flask import Blueprint, request
from db.connection import get_connection, read_frame
from api.district_resolver import resolve_district_id
from api.contracts import response, failure
from models.ensemble import feature_generation

history_bp=Blueprint('history',__name__)

def _month(value):
    if len(value)==7:
        return date.fromisoformat(value+'-01')
    return date.fromisoformat(value)

@history_bp.route('/history/<district_id>')
def get_history(district_id):
    connection=None
    try:
        start=_month(request.args.get('start','2002-01'))
        end=_month(request.args.get('end',date.today().strftime('%Y-%m')))
        if start>end:
            raise ValueError('start must precede or equal end.')
        count=int(request.args['months']) if 'months' in request.args else None
        if count is not None and not 1<=count<=1200:
            raise ValueError('months must be an integer between 1 and 1200.')
        canonical=resolve_district_id(district_id)
        connection=get_connection()
        frame=read_frame('''SELECT to_char(date,'YYYY-MM') AS month,gwl_current AS gwl,rainfall_current AS rainfall,
            is_observed,is_imputed,months_since_observation,feature_generation FROM features
            WHERE district_id=%s AND date>=%s AND date<=%s AND feature_generation=%s ORDER BY date''',
            connection,(canonical,start,end,feature_generation()))
        if count is not None:
            frame=frame.tail(count)
        rows=frame.to_dict('records')
        for row in rows:
            row['date']=row['month']
        return response({'district_id':canonical,'requested_id':district_id,'start':start,'end':end,'data':rows,'history':rows})
    except Exception as error:
        return failure(error)
    finally:
        if connection is not None:
            connection.close()
