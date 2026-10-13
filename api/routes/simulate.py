"""Scenario sensitivity on the same selected evidence as ordinary scoring."""
import math
import numpy as np
from flask import Blueprint,request
from api.contracts import response,failure
from api.district_resolver import resolve_district_id
from models.ensemble import select_evidence,score_evidence,forecast_from_evidence,components_from_history,blend_components,CONFIG
from models.tiers import score_to_tier

simulate_bp=Blueprint('simulate',__name__)

@simulate_bp.route('/simulate',methods=['POST'])
def simulate():
    try:
        body=request.get_json(silent=True)
        if not isinstance(body,dict):
            raise ValueError('Request body must be a JSON object.')
        if not isinstance(body.get('district_id'),str) or not body['district_id'].strip():
            raise ValueError('district_id is required.')
        rainfall=float(body.get('rainfall_change_pct',0))
        extraction=float(body.get('extraction_change_pct',0))
        if not all(math.isfinite(v) and -100<=v<=100 for v in (rainfall,extraction)):
            raise ValueError('Policy changes must be finite numbers between -100 and 100 percent.')
        canonical=resolve_district_id(body['district_id'].strip())
        evidence=select_evidence(canonical,body.get('as_of'))
        baseline=score_evidence(evidence)
        value=baseline['crisis_score']
        data={'district_id':canonical,'baseline_score':value,'baseline_crisis_score':value,
            'baseline_tier':baseline['tier'],'simulated_score':value,'simulated_crisis_score':value,
            'simulated_tier':baseline['tier'],'delta':0 if value is not None else None,
            'status':baseline['status'],'estimate_type':baseline['estimate_type'],
            'zone_fallback_reason':baseline.get('zone_fallback_reason'),'last_observed_date':baseline.get('last_observed_date'),
            'extraction_heuristic_applied':False,'simulation_details':{
                'rainfall_change_pct':rainfall,'extraction_change_pct':extraction,
                'xgb_inference_used':False,'extraction_method':'project sensitivity heuristic, not learned causal effect'}}
        if value is None or (rainfall==0 and extraction==0):
            return response(data)
        row=evidence['frame'][evidence['frame'].date==evidence['origin']].iloc[-1]
        change=rainfall/100.
        override={key:float(row[key])*(1.+change) for key in ('rainfall_current','rainfall_3mo_avg')}
        if not all(np.isfinite(v) for v in override.values()):
            raise ValueError('Rainfall observations are unavailable for this scenario.')
        anomaly=float(row['monsoon_deficit_pct'])
        override['monsoon_deficit_pct']=(100.+anomaly)*(1.+change)-100. if np.isfinite(anomaly) else np.nan
        override['water_balance_proxy']=override['rainfall_current']-float(row['evapotranspiration'])
        changed_forecast=forecast_from_evidence(evidence,override)
        changed_history=evidence['history'].copy()
        changed_history.loc[changed_history.date==evidence['origin'],'monsoon_deficit_pct']=override['monsoon_deficit_pct']
        components=components_from_history(changed_history,changed_forecast['forecast'][0]['predicted_gwl'])
        changed_score,_=blend_components(components)
        heuristic=CONFIG.get('policy_simulation',{}).get('extraction_heuristic_delta_per_pct',.2)*extraction
        simulated=round(float(np.clip(changed_score+heuristic,0,100)))
        data.update(simulated_score=simulated,simulated_crisis_score=simulated,simulated_tier=score_to_tier(simulated),
            delta=simulated-value,extraction_heuristic_applied=extraction!=0)
        data['simulation_details']['xgb_inference_used']=True
        return response(data)
    except (TypeError,ValueError) as error:
        return failure(ValueError(str(error)))
    except Exception as error:
        return failure(error)
