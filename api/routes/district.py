from flask import Blueprint
from models.ensemble import compute_crisis_score
from api.district_resolver import resolve_district_id,get_district_metadata
from api.contracts import response,parse_as_of,failure
from models.district_registry import get_registry

district_bp=Blueprint('district',__name__)


@district_bp.route('/districts')
def get_district_catalog():
    """Navigation uses registered identities, independent of scoring/model availability."""
    try:
        districts=[{'district_id':row['district_id'],'name':row['district_name'],
            'state':row['state_name'],'state_id':row['state_id']} for row in get_registry()]
        return response({'status':'success','total':len(districts),'districts':districts})
    except Exception:
        return failure(RuntimeError('District registry unavailable.'))

@district_bp.route('/district/<district_id>')
def get_district(district_id):
    try:
        cutoff=parse_as_of()
        canonical=resolve_district_id(district_id)
        data=compute_crisis_score(canonical,cutoff)
        data.update(metadata=get_district_metadata(canonical),resolved_id=canonical,
            ensemble_components=data.get('components',{}))
        return response(data)
    except Exception as error:
        return failure(error)
