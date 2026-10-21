"""Verify immutable research outputs arithmetically and reload only new H12 models."""
from pathlib import Path
import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[2]
sys.path.insert(0,str(ROOT))
from models import research_horizon as research
from scripts import backtest_twelve_month as runner


def main():
    checksum = research.sha256_file(RUN/'protocol.json')
    protocol = json.loads((RUN/'protocol.json').read_text())
    output = RUN/'evaluation'
    metrics = json.loads((output/'metrics.json').read_text())
    predictions = {}
    summaries = []
    for dataset in ('full_coordinate','exact_name_coordinate'):
        table = pd.read_csv(output/(dataset+'_predictions.csv'),parse_dates=['date','target_date'])
        frozen = pd.read_csv(RUN/'cohorts'/(dataset+'_inventory.csv'))
        assert table.case_id.tolist() == frozen.case_id.tolist()
        assert table.common_eligible.tolist() == frozen.common_eligible.tolist()
        assert table.target_date.eq(table.date+pd.DateOffset(months=12)).all()
        paired = table.loc[table.common_eligible]
        assert paired.origin_is_observed.all() and paired.target_is_observed.all()
        assert paired.persistence.eq(paired.annual_seasonal_naive).all()
        for period in ('primary','secondary'):
            part=paired.loc[paired.period.eq(period)]
            for name in runner.MODELS:
                error=part[name].to_numpy()-part.actual.to_numpy()
                values={'mae_m':float(np.abs(error).mean()),'rmse_m':float(np.sqrt(np.square(error).mean())),
                    'bias_m':float(error.mean())}
                expected=metrics[dataset+'_'+period]['models'][name]
                assert expected['n']==len(part)
                assert all(np.isclose(value,expected[key],rtol=0,atol=1e-10) for key,value in values.items())
        predictions[dataset]=table
        summaries.append({'dataset':dataset,'common_cases':len(paired),'paired_observed_targets':True,
            'baseline_identity':True,'metrics_recomputed':True})
    cards=[]
    for path in sorted((output/'models').rglob('*_card.json')):
        card=json.loads(path.read_text())
        model,loaded=research.load_research_model(path,12,checksum,card['features'])
        dataset=path.parent.name
        year=int(path.stem.split('_')[-2])
        table=predictions[dataset]
        table=table.loc[table.common_eligible & table.target_date.dt.year.eq(year)]
        if card['family']=='linear_regression':
            values=pd.Series(index=table.index,dtype=float)
            for district,part in table.groupby('district_id'):
                values.loc[part.index]=model[district].predict(part[card['features']])
            actual=values.to_numpy()
        else:
            actual=model.predict(table[card['features']])
            if card['family']=='hist_gradient_boosting':
                actual=np.maximum(0,table.gwl_current.to_numpy()+actual)
        expected=table[card['model_name']].to_numpy()
        error=float(np.max(np.abs(actual-expected)))
        assert np.allclose(actual,expected,rtol=0,atol=1e-8),path
        # Contract checks reject the other horizon before native deserialization.
        try:
            research.validate_card(loaded,6,checksum,card['features'])
        except ValueError:
            pass
        else:
            raise AssertionError('Twelve-month artifact accepted as six-month')
        cards.append({'card':path.relative_to(RUN).as_posix(),'model_sha256':loaded['model_sha256'],
            'roundtrip_max_abs_prediction_difference_m':error,'horizon_guard_verified':True})
    active=ROOT/'models/checkpoints/aquaiq_xgb.json'
    pointer=json.loads(active.read_text())
    active_card=json.loads((active.parent/pointer['card_path']).read_text())
    try:
        research.validate_card(active_card,12,checksum,runner.F)
    except ValueError:
        pass
    else:
        raise AssertionError('Active six-month artifact accepted as twelve-month research')
    matched=pd.read_csv(output/'six_vs_twelve_same_target.csv')
    assert np.allclose(matched.persistence_12,matched.seasonal_naive_6,rtol=0,atol=1e-10)
    normalized=pd.read_csv(ROOT/'reports/actual_forecast_validation_20261019/normalized_v2/normalized_well_observations.csv')
    normalized['date']=pd.to_datetime(normalized.date)
    normalized['name_unknown']=normalized.source_name_district_id.isna()
    normalized['name_coordinate_conflict']=~normalized.name_unknown & normalized.source_name_district_id.ne(normalized.district_id)
    normalized['over_listed_depth']=normalized.gwl_m_bgl.gt(normalized.well_depth_m)
    grouped=normalized.groupby(['district_id','date']).agg(total=('gwl_m_bgl','size'),
        conflict=('name_coordinate_conflict','sum'),unknown=('name_unknown','sum'),over_depth=('over_listed_depth','sum')).reset_index()
    primary=predictions['full_coordinate'].loc[lambda f:f.common_eligible & f.period.eq('primary')]
    composition=primary[['case_id','district_id','target_date']].merge(grouped.rename(columns={'date':'target_date'}),
        on=['district_id','target_date'],validate='one_to_one')
    for name in ('conflict','unknown','over_depth'): composition[name+'_share']=composition[name]/composition.total
    composition_path=RUN/'target_panel_quality.csv'
    with composition_path.open('x',encoding='utf-8',newline='') as handle: composition.to_csv(handle,index=False)
    record={'verified_at_utc':datetime.now(timezone.utc).isoformat(),'protocol_sha256':checksum,
        'model_cards_verified':len(cards),'new_research_model_roundtrips':cards,'cohort_checks':summaries,
        'active_six_month_card_rejected_as_twelve_month':True,
        'six_month_seasonal_equals_twelve_month_persistence_on_matched_targets':True,
        'primary_target_panels_with_conflicts':int(composition.conflict.gt(0).sum()),
        'primary_mean_target_conflict_share':float(composition.conflict_share.mean()),
        'primary_mean_target_unknown_name_share':float(composition.unknown_share.mean()),
        'primary_target_panels_with_reading_over_listed_depth':int(composition.over_depth.gt(0).sum()),
        'model_fitting_performed':False,'database_accessed':False,'production_model_loaded':False}
    with (RUN/'result_verification.json').open('x',encoding='utf-8') as handle: json.dump(record,handle,indent=2)
    print(json.dumps({key:value for key,value in record.items() if key not in ('new_research_model_roundtrips','cohort_checks')},indent=2))


if __name__=='__main__':
    main()
