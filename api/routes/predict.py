"""Historical model endpoint and clearly labelled present-day projections."""
from flask import Blueprint, request
from models.ensemble import forecast_result
from models.monthly_projection import forecast_next_six_months
from api.district_resolver import resolve_district_id
from api.contracts import response, parse_as_of, failure

predict_bp=Blueprint('predict',__name__)

@predict_bp.route('/predict/<district_id>')
def get_prediction(district_id):
    try:
        window=request.args.get('window','observed_endpoint')
        if window not in ('observed_endpoint','next_six_months'):
            raise ValueError('window must be observed_endpoint or next_six_months.')
        if any(key in request.args for key in ('target_year','year','start','start_month')):
            raise ValueError('year, target_year, start, and start_month are unsupported. Use as_of and window to select the prediction window.')
        if request.args.get('months','6')!='6':
            raise ValueError('Only a six-month prediction horizon is supported; months must equal 6.')
        cutoff=parse_as_of()
        canonical=resolve_district_id(district_id)
        data=(forecast_next_six_months(canonical,cutoff) if window=='next_six_months'
              else forecast_result(canonical,cutoff))
        data['requested_id']=district_id
        data['resolved_id']=canonical
        return response(data)
    except Exception as error:
        return failure(error)
