"""Own-district source contracts. Synthetic CSVs are confined to pytest paths."""
from datetime import datetime, timezone
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from models import scenario_sources as sources
from models import experimental_scenario as scenario
from models import research_forecast as direct

NOW = datetime(2026,10,21,12,tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def guard_io(monkeypatch):
    import psycopg2
    import xgboost
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
    from sklearn.linear_model import LinearRegression, Ridge
    def forbidden(*args,**kwargs):
        pytest.fail("Own-district scenarios must not access DB or fit/load active ML")
    monkeypatch.setattr(psycopg2,"connect",forbidden)
    monkeypatch.setattr(xgboost.XGBRegressor,"load_model",forbidden)
    for model in (xgboost.XGBRegressor,HistGradientBoostingRegressor,RandomForestRegressor,LinearRegression,Ridge):
        monkeypatch.setattr(model,"fit",forbidden)
    sources._parse.cache_clear()
    yield
    sources._parse.cache_clear()


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(sources,"ROOT",tmp_path)
    dates=pd.date_range("2010-01-01","2027-02-01",freq="MS")
    frame=pd.concat([pd.DataFrame({"district_id":district,"date":dates,"GWL_current":base+np.sin(dates.month*np.pi/6),
                                   "gwl_current":base+np.sin(dates.month*np.pi/6),"is_observed":True,"is_imputed":False,
                                   "feature_generation":"physical-v3-causal-monthly-SYNTHETIC"})
                     for district,base in (("HR-Fixture",10),("GJ-Fixture",30))],ignore_index=True)
    registry=pd.DataFrame({"canonical_district_id":["HR-Fixture","GJ-Fixture"],"canonical_name":["SYNTHETIC Haryana","SYNTHETIC Gujarat"],
                           "canonical_state":["SYNTHETIC ONLY","SYNTHETIC ONLY"],"legacy_district_id":["HR-Fixture","GJ-Fixture"]})
    config={"schema_version":1,"product":"experimental_12month_scenario_sources","scope":"canonical_district_own_observed_history",
            "feature_generation_id":"physical-v3-causal-monthly-SYNTHETIC","units":"m_bgl","units_qualification":"SYNTHETIC ONLY: datum unknown",
            "district_count":2,"source_name":"SYNTHETIC TEST FIXTURE ONLY","feature_csv_path":"features.csv",
            "feature_manifest_path":"manifest.json","district_crosswalk_path":"registry.csv"}
    manifest={"generation_id":config["feature_generation_id"],"units":{"gwl":"m_bgl"},"causal_preprocessing":True,"sample_only":False,
              "observation_column":"is_observed","date_start":"2010-01-01","date_end":"2027-02-01"}
    def publish():
        frame.to_csv(tmp_path/'features.csv',index=False)
        manifest['feature_csv_sha256']=hashlib.sha256((tmp_path/'features.csv').read_bytes()).hexdigest()
        (tmp_path/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        registry.to_csv(tmp_path/'registry.csv',index=False)
        for key in ('feature_csv','feature_manifest','district_crosswalk'):
            config[key+'_sha256']=hashlib.sha256((tmp_path/config[key+'_path']).read_bytes()).hexdigest()
        (tmp_path/'research').mkdir(exist_ok=True)
        (tmp_path/sources.DEFAULT_CONFIG).write_text(json.dumps(config),encoding='utf-8')
        monkeypatch.setattr(sources,'CONFIG_SHA256',direct._canonical_hash(config))
    publish()
    return {'root':tmp_path,'frame':frame,'registry':registry,'config':config,'manifest':manifest,'publish':publish}


def test_two_districts_use_their_own_history_without_cross_contamination(fixture,monkeypatch):
    monkeypatch.setattr(direct,'_load_bundle',lambda *_:pytest.fail('National scenario loaded Adilabad artifact'))
    first=scenario.scenario('HR-Fixture',now=NOW)
    second=scenario.scenario('GJ-Fixture',now=NOW)
    assert first['source']['district_name']=='SYNTHETIC Haryana'
    assert first['source']['scope']=='district_own_observed_history'
    assert first['source']['well_count'] is None and first['source']['panel_sha256'] is None
    assert first['source']['actual_acquisition_at'] is None and first['source']['input_available_at'] is None
    assert len(first['forecast'])==len(second['forecast'])==12
    assert all(abs(b['projected_gwl']-a['projected_gwl']-20)<1e-8 for a,b in zip(first['forecast'],second['forecast']))


def test_current_future_and_filled_rows_cannot_change_scenario(fixture):
    frame=fixture['frame'];mask=frame.date.dt.month.eq(2)
    frame.loc[mask,'is_observed']=False;frame.loc[mask,'is_imputed']=True;fixture['publish']()
    before=scenario.scenario('HR-Fixture',now=NOW)
    changed=frame.date.ge('2026-10-01')|mask
    frame.loc[changed,['GWL_current','gwl_current']]=99999;fixture['publish']()
    after=scenario.scenario('HR-Fixture',now=NOW)
    assert before['forecast']==after['forecast']
    assert before['method']['history_sha256']==after['method']['history_sha256']
    assert 2 in after['method']['unobserved_calendar_months']


def test_private_district_slice_cannot_mutate_cached_source(fixture):
    one=sources.load_district('HR-Fixture');one['frame'].loc[:,'gwl_current']=99999
    two=sources.load_district('HR-Fixture')
    assert two['frame'].gwl_current.max()<12
    assert two['frame'].district_id.eq('HR-Fixture').all()


def test_revised_source_bytes_block_before_cached_parse_is_used(fixture):
    sources.load_district('HR-Fixture')
    with (fixture['root']/'features.csv').open('a',encoding='utf-8') as f:f.write('\n')
    with pytest.raises(direct.ResearchContractError,match='checksum mismatch'):
        sources.load_district('HR-Fixture')


def test_changed_configuration_requires_separate_review(fixture):
    path=fixture['root']/sources.DEFAULT_CONFIG
    config=json.loads(path.read_text());config['district_count']=99;path.write_text(json.dumps(config))
    with pytest.raises(direct.ResearchContractError,match='pinned reviewed version'):
        sources.load_district('HR-Fixture')


@pytest.mark.parametrize('field,value',[('units',{'gwl':'feet'}),('generation_id','unknown'),('causal_preprocessing',False),('sample_only',True),('observation_column','unknown')])
def test_even_reviewed_hashes_cannot_hide_invalid_manifest_semantics(fixture,field,value):
    fixture['manifest'][field]=value;fixture['publish']()
    with pytest.raises(direct.ResearchContractError):sources.load_district('HR-Fixture')


@pytest.mark.parametrize('problem',['unknown_flag','contradictory_flag','duplicate_month','non_month_start','wrong_generation','alias_mismatch','negative_observed','missing_district'])
def test_bad_history_schema_never_supplies_an_observed_fit(fixture,problem):
    frame=fixture['frame']
    if problem=='unknown_flag':frame['is_observed']=frame.is_observed.astype(object);frame.loc[0,'is_observed']='unknown'
    if problem=='contradictory_flag':frame.loc[0,'is_imputed']=True
    if problem=='duplicate_month':frame.loc[1,'date']=frame.loc[0,'date']
    if problem=='non_month_start':frame.loc[0,'date']=pd.Timestamp('2010-01-02')
    if problem=='wrong_generation':frame.loc[0,'feature_generation']='other'
    if problem=='alias_mismatch':frame.loc[0,'GWL_current']=999
    if problem=='negative_observed':frame.loc[0,['GWL_current','gwl_current']]=-1
    if problem=='missing_district':frame.loc[frame.district_id.eq('GJ-Fixture'),'district_id']='XX-Unknown'
    fixture['publish']()
    with pytest.raises(direct.ResearchContractError):sources.load_district('HR-Fixture')


def test_unknown_and_insufficient_districts_return_no_borrowed_curve(fixture):
    unknown=scenario.scenario('HR-Unknown',now=NOW)
    assert unknown['status']=='unavailable' and unknown['forecast']==[]
    frame=fixture['frame'];mask=frame.district_id.eq('HR-Fixture')
    frame.loc[mask,'is_observed']=False;frame.loc[mask,'is_imputed']=True;fixture['publish']()
    absent=scenario.scenario('HR-Fixture',now=NOW)
    assert absent['status']=='unavailable' and absent['forecast']==[]
    assert absent['source']['observed_months_available']==0
    assert 'No source-marked' in absent['unavailable_reasons'][0]


def test_real_kaithal_has_twelve_own_district_points_and_unknown_panel():
    value=scenario.scenario('HR-Kaithal',now=NOW)
    assert value['status']=='scenario' and len(value['forecast'])==12
    assert value['source']['last_observed_month']=='2026-01' and value['source']['data_age_months']==9
    assert value['method']['observed_month_count']==77
    assert value['source']['district_name']=='Kaithal'
    assert value['source']['well_count'] is None and value['source']['availability_verified'] is False


def test_existing_adilabad_numerical_scenario_is_preserved():
    path=sources.ROOT/'reports/candidates/current_twelve_month_scenario_20261021/local_scenario_example.json'
    before=json.loads(path.read_text(encoding='utf-8'))
    after=scenario.scenario('TS-Adilabad',before['as_of'],now=NOW)
    assert before['forecast']==after['forecast']
    assert before['estimated_current_gwl']==after['estimated_current_gwl']
    assert before['method']['history_sha256']==after['method']['history_sha256']
