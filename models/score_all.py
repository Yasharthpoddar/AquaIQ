"""Publish a complete scoring run and its auditable six-month predictions."""
import argparse
from datetime import date
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
import json
import sys
import math
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from db.connection import read_frame
from db.scoring_storage import get_scoring_connection as get_connection, initialize_test_schema
from models.ensemble import compute_crisis_score, _load_bundle, feature_generation, _as_of, scoring_signature
from models.tiers import score_to_tier


def _derive_top_factors(components):
    labels = {'xgb_risk':'Groundwater depth and six-month forecast','lr_trend':'Observed long-term groundwater trend',
        'drought_frequency':'Observed depth exceedance frequency','fuzzy_logic':'Rainfall anomaly and annual groundwater change'}
    values = [(value,labels[key]) for key,value in components.items() if key in labels and value is not None and value>30]
    factors = [label for _,label in sorted(values,reverse=True)[:3]]
    return tuple((factors+[None]*3)[:3])


def score_all_districts(forecast_date=None, *, connection=None):
    cutoff = forecast_date or date.today()
    if isinstance(cutoff,str):
        cutoff = date.fromisoformat(cutoff)
    cutoff = _as_of(cutoff).date()
    _,card = _load_bundle()
    generation = feature_generation()
    signature = scoring_signature()
    basis = json.dumps([cutoff.isoformat(),generation,card['model_sha256'],signature],sort_keys=True)
    run_id = str(uuid5(NAMESPACE_URL,'aquaiq:scoring:'+basis))
    own = connection is None
    connection = connection or get_connection()
    try:
        districts = read_frame('SELECT district_id FROM districts ORDER BY district_id',connection).district_id.tolist()
        records = []
        zone_cache = {}
        for index,district_id in enumerate(districts):
            records.append(compute_crisis_score(district_id,cutoff,connection,zone_cache))
            if (index+1)%100==0:
                print(f'Scored {index+1}/{len(districts)} canonical districts.',flush=True)
        if len(records)!=len(districts) or {r['district_id'] for r in records}!=set(districts):
            raise ValueError('Incomplete district scoring run.')
        for record in records:
            value=record['crisis_score']
            if value is not None and (isinstance(value,bool) or not math.isfinite(value) or not 0<=value<=100
                    or value != int(value) or record['tier'] != score_to_tier(value)):
                raise ValueError('Invalid risk score; publication refused.')
            if value is None and record['tier'] is not None:
                raise ValueError('An unavailable score cannot have a risk tier.')
        if feature_generation()!=generation or scoring_signature()!=signature or _load_bundle()[1]['model_sha256']!=card['model_sha256']:
            raise RuntimeError('Scoring inputs changed before publication.')
        # A model/DB exception aborts publication; missing evidence is an explicit null result.
        with connection:
            with connection.cursor() as cursor:
                cursor.execute('''INSERT INTO scoring_runs(run_id,as_of,feature_generation,model_version,model_sha256,district_count,status,scoring_signature)
                    VALUES(%s,%s,%s,%s,%s,%s,'completed',%s)
                    ON CONFLICT(run_id) DO UPDATE SET completed_at=CURRENT_TIMESTAMP,district_count=EXCLUDED.district_count''',
                    (run_id,cutoff,generation,card['version'],card.get('model_sha256',''),len(records),signature))
                for record in records:
                    factors = _derive_top_factors(record['components']) if record['crisis_score'] is not None else (None,None,None)
                    cursor.execute('''INSERT INTO crisis_scores(district_id,forecast_date,aquaiq_score,tier,estimate_type,zone_fallback_reason,
                        top_factor_1,top_factor_2,top_factor_3,run_id,last_observed_date,feature_generation,model_version)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(district_id,forecast_date) DO UPDATE SET aquaiq_score=EXCLUDED.aquaiq_score,tier=EXCLUDED.tier,
                        estimate_type=EXCLUDED.estimate_type,zone_fallback_reason=EXCLUDED.zone_fallback_reason,
                        top_factor_1=EXCLUDED.top_factor_1,top_factor_2=EXCLUDED.top_factor_2,top_factor_3=EXCLUDED.top_factor_3,
                        run_id=EXCLUDED.run_id,last_observed_date=EXCLUDED.last_observed_date,
                        feature_generation=EXCLUDED.feature_generation,model_version=EXCLUDED.model_version,updated_at=CURRENT_TIMESTAMP''',
                        (record['district_id'],cutoff,record['crisis_score'],record['tier'],record['estimate_type'],record.get('zone_fallback_reason'),
                            *factors,run_id,record.get('last_observed_date'),generation,record.get('model_version')))
                    for point in record['forecast']:
                        cursor.execute('''INSERT INTO predictions(district_id,forecast_date,model_name,predicted_gwl,predicted_risk_tier,
                            run_id,origin_date,as_of_date,model_version,feature_generation,estimate_type,source_zone)
                            VALUES(%s,%s,'xgboost',%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT(run_id,district_id,forecast_date,model_name) DO NOTHING''',
                            (record['district_id'],point['month']+'-01',point['predicted_gwl'],record['tier'],run_id,record['forecast_origin'],
                                cutoff,record['model_version'],generation,record['estimate_type'],record.get('source_zone')))
        print(f'Published complete run {run_id}: {len(records)} districts, {sum(len(r["forecast"]) for r in records)} forecasts.')
        return len(records)
    finally:
        if own: connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=date.fromisoformat,default=date.today())
    parser.add_argument('--test-schema',help='Publish only to an isolated aquaiq_test_* output schema; source tables remain unchanged')
    args = parser.parse_args(argv)
    connection=initialize_test_schema(args.test_schema) if args.test_schema else None
    try:
        score_all_districts(args.date,connection=connection)
    finally:
        if connection is not None: connection.close()


if __name__=='__main__':
    main()
