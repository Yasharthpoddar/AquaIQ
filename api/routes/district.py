from flask import Blueprint
from models.ensemble import compute_crisis_score
from api.district_resolver import resolve_district_id,get_district_metadata
from api.contracts import response,parse_as_of,failure

district_bp=Blueprint('district',__name__)

@district_bp.route('/district/<district_id>')
def get_district(district_id):
    try:
        canonical=resolve_district_id(district_id)
        data=compute_crisis_score(canonical,parse_as_of())
        data.update(metadata=get_district_metadata(canonical),resolved_id=canonical,
            ensemble_components=data.get('components',{}))
        return response(data)
    except Exception as error:
        return failure(error)
