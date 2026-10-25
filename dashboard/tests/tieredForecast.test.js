import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadJsx } from './helpers/loadJsx.js';
import { validateClimate12mForecast, climate12mChartRows } from '../src/components/climateForecast12mContract.js';
import { validateStateForecast } from '../src/components/stateForecastContract.js';
const { ClimateForecast12mView } = await loadJsx(new URL('../src/components/DistrictForecastGraph.jsx', import.meta.url));

function fallback(tier='C') {
  return { product:'climate_informed_12m_forecast',model_version:'1.0-reference-12m',district_id:'HR-Z',
    status:'forecast',as_of:'2026-10-25',forecast_origin:'2026-10-01',timezone:'Asia/Kolkata',
    horizon_months:12,units:'m_bgl',evidence_tier:tier,observation_count:tier==='C'?0:3,
    forecast_method:tier==='C'?'regional_seasonal_reference':'local_persistence',
    projection_method:tier==='C'?'regional_seasonal_reference':'local_persistence',
    estimate_type:tier==='C'?'regional_reference':'district_level',warning:'Limited evidence: no target-specific validation.',
    fallback_reason:'Insufficient local history',forecast_start:'2026-11',forecast_end:'2027-10',
    estimated_current_gwl:10,last_observed_date:null,forecast:Array.from({length:12},(_,i)=>({
      month:new Date(Date.UTC(2026,10+i,1)).toISOString().slice(0,7),date:new Date(Date.UTC(2026,10+i,1)).toISOString().slice(0,10),
      horizon:i+1,predicted_gwl:10,delta_from_current_m:0,lower_gwl:0,upper_gwl:25,
      weather:{rainfall_mm:null,temperature_c:null,evapotranspiration_mm:null}}))};
}

test('zero and sparse outputs pass the contract without invented weather',()=>{
  for(const tier of ['B','C','D']) {
    const value=validateClimate12mForecast(fallback(tier),'HR-Z');
    assert.equal(climate12mChartRows(value).length,12);
    assert.equal(climate12mChartRows(value)[0].lower,0);
  }
  const value=fallback();value.forecast[0].weather.rainfall_mm=0;
  assert.throws(()=>validateClimate12mForecast(value),/weather/);
});

test('invalid evidence and uncertainty cannot masquerade as supported forecasts',()=>{
  const value=fallback();value.evidence_tier='A';
  assert.throws(()=>validateClimate12mForecast(value),/reference evidence/);
  const bad=fallback();bad.forecast[0].lower_gwl=11;
  assert.throws(()=>validateClimate12mForecast(bad),/prediction range/);
});

test('fallback view exposes values, limitations, observation count and uncertainty',()=>{
  const html=renderToStaticMarkup(createElement(ClimateForecast12mView,{value:fallback()}));
  assert.match(html,/Evidence tier C/);assert.match(html,/Regional reference estimate/);
  assert.match(html,/0 genuine observed district months/);assert.match(html,/Historical range/);
  assert.match(html,/Limited evidence/);assert.match(html,/View all 12/);
  assert.doesNotMatch(html,/only XGBoost supplies/);
});

test('tiered state contracts require an explicit complete evidence mix',()=>{
  const value={product:'state_groundwater_12m_forecast',model_version:'3.0-state-tiered',model_name:'district_tiered_equal_weight',
    state_id:'HR',state_name:'Haryana',units:'m_bgl',horizon_months:12,as_of:'2026-10-25',forecast_origin:'2026-10-01',
    computed_at:'2026-10-25T12:00:00Z',status:'forecast',districts:['HR-Z'],contributing_district_ids:['HR-Z'],
    total_districts_in_state:1,contributing_districts_count:1,district_coverage_pct:100,current_depth_basis:'estimated_district_inputs',
    estimated_current_gwl_m_bgl:10,excluded_districts:[],panel_id:'fixture',aggregation_method:'equal_weight_all_registered_districts',
    evidence_tier_counts:{C:1},evidence_tier_proportions:{A:0,B:0,C:1,D:0},history:[],
    forecast:fallback().forecast.map(r=>({horizon:r.horizon,target_date:r.date,predicted_gwl:r.predicted_gwl,delta_from_current_m:0}))};
  assert.equal(validateStateForecast(value,'HR').forecast.length,12);
  value.evidence_tier_counts={A:1,C:1};assert.throws(()=>validateStateForecast(value,'HR'),/evidence tier counts/);
});
