from flask import Blueprint,request
from db.scoring_storage import get_scoring_connection as get_connection
from api.routes.scores import latest_scores,score_records
from api.contracts import response,failure

alerts_bp=Blueprint('alerts',__name__)

@alerts_bp.route('/alerts')
def get_alerts():
    connection=None
    try:
        tier=request.args.get('tier','all').lower()
        if tier not in ('all','safe','watch','warning','crisis'):
            raise ValueError('tier must be Safe, Watch, Warning, Crisis, or All.')
        limit=int(request.args.get('limit',100))
        if not 1<=limit<=1000:
            raise ValueError('limit must be an integer between 1 and 1000.')
        connection=get_connection()
        records=score_records(latest_scores(connection))
        status='success' if records else 'awaiting_complete_scoring_run'
        if tier!='all':
            records=[row for row in records if row['tier'] and row['tier'].lower()==tier]
        total=len(records)
        records=sorted(records,key=lambda row:row['score'] if row['score'] is not None else -1,reverse=True)[:limit]
        for row in records:
            row['crisis_score']=row['score']
            row['risk_tier']=row['tier']
            row['recommendation']='Review observed history and the historical forecast before planning action.' if row['score'] is not None else 'Risk-index evidence is insufficient. Open the district to review its separate twelve-month outlook.'
        return response({'alerts':records,'count':len(records),'total':total,'has_more':total>len(records),'status':status})
    except Exception as error:
        return failure(error)
    finally:
        if connection is not None:
            connection.close()
