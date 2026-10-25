import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement, Children } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { readFileSync } from 'node:fs';
import { loadJsx } from './helpers/loadJsx.js';
import { stateForecastMonths, validateStateForecast, stateChartRows, validateStatesSummary, STATE_XGB_VERSION } from '../src/components/stateForecastContract.js';
import { buildStateLookup, matchState, searchStates, stateSelectionId } from '../src/stateMap.js';
import { fetchStatePredict, fetchStatesSummary } from '../src/api.js';

const { default: StateForecastGraph, stateForecastPlot, StateForecastTooltip } = await loadJsx(new URL('../src/components/StateForecastGraph.jsx', import.meta.url));
const { forecast12mPlot, loadDistrictForecast } = await loadJsx(new URL('../src/components/DistrictForecastGraph.jsx', import.meta.url));
export const fixture = () => ({
  product: 'state_groundwater_12m_forecast', model_version: STATE_XGB_VERSION, model_name: 'district_xgboost_equal_weight',
  state_id: 'TN', state_name: 'Tamil Nadu', units: 'm_bgl', horizon_months: 12, status: 'forecast',
  as_of: '2026-10-25', forecast_origin: '2026-10-01', computed_at: '2026-10-25T06:00:00Z',
  districts: ['TN-A','TN-B'], contributing_district_ids: ['TN-A','TN-B'], contributing_districts_count: 2,
  total_districts_in_state: 2, excluded_districts: [], district_coverage_pct: 100, panel_id: 'synthetic-panel',
  aggregation_method: 'equal_weight_fixed_district_xgboost_panel', estimated_current_gwl_m_bgl: 10, current_depth_basis: 'estimated_district_inputs',
  history: [{ date: '2026-08-01', gwl_m_bgl: 9, contributing_districts_count: 2, district_coverage_pct: 100 }],
  forecast: stateForecastMonths('2026-10-25').map((month,i) => ({ target_date: `${month}-01`, horizon: i+1, predicted_gwl: 10+i/10, delta_from_current_m: i/10 })),
});

test('fixed-panel contract validates identity, dates, coverage and all twelve returned points', () => {
  const valid = fixture();
  assert.equal(validateStateForecast(valid, 'TN', valid.as_of), valid);
  for (const mutate of [v => {v.state_id='HR';}, v => {v.model_version='trend';}, v => {v.units='feet';},
    v => {v.forecast.reverse();}, v => {v.forecast.pop();}, v => {v.forecast[2].predicted_gwl=NaN;},
    v => {v.forecast[2].delta_from_current_m=3;}, v => {v.district_coverage_pct=10;},
    v => {v.contributing_district_ids=['TN-A','TN-A'];}, v => {v.history[0].date='2027-02-01';},
    v => {v.as_of='2026-09-25';}]) {
    const bad = fixture(); mutate(bad);
    assert.throws(() => validateStateForecast(bad,'TN','2026-10-25'), /Invalid state XGBoost response/);
  }
});

test('monthly chart preserves gaps and never invents or interpolates points', () => {
  const rows = stateChartRows(fixture());
  assert.deepEqual(rows.filter(r => r.predicted !== null).map(r => r.predicted), fixture().forecast.map(r => r.predicted_gwl));
  assert.equal(rows.find(r => r.month==='2026-09').predicted,null);
  assert.equal(rows.find(r => r.month==='2026-09').observed,null);
  assert.deepEqual(stateForecastMonths('2024-02-29').slice(0,2), ['2024-03','2024-04']);
});

test('state and district plots contain only XGBoost predictions even when API has baseline fields', () => {
  const state = stateForecastPlot(fixture());
  const lines = Children.toArray(state.props.children).filter(child => child.props.dataKey && ['observed','predicted','persistence','seasonal'].includes(child.props.dataKey));
  assert.deepEqual(lines.map(line=>[line.props.dataKey,line.props.name]), [['observed','Observed reporting-district mean'],['predicted','XGBoost Forecast']]);
  const district = forecast12mPlot({status:'forecast',forecast:[{month:'2026-11',predicted_gwl:5,baselines:{persistence:3,seasonal:4}}]});
  const predictionLines = Children.toArray(district.props.children).filter(child=>child.props.name);
  assert.deepEqual(predictionLines.map(line=>line.props.name),['XGBoost Forecast']);
});

test('unavailable, error and loading states never show stale forecasts or fallback paths', () => {
  const unavailable = {...fixture(), status:'model_unavailable',forecast:[],message:'Verified model missing'};
  validateStateForecast(unavailable,'TN');
  assert.match(renderToStaticMarkup(createElement(StateForecastGraph,{forecastData:unavailable})),/Verified model missing/);
  const error = renderToStaticMarkup(createElement(StateForecastGraph,{forecastData:fixture(),error:'Service failed'}));
  assert.match(error,/Retry state forecast/); assert.doesNotMatch(error,/View all 12/);
  assert.match(renderToStaticMarkup(createElement(StateForecastGraph,{loading:true})),/Loading state forecast/);
  const tip = renderToStaticMarkup(createElement(StateForecastTooltip,{active:true,payload:[{payload:{month:'2027-01',predicted:12,horizon:3,delta:2}}]}));
  assert.match(tip,/Jan 2027/); assert.match(tip,/12.00 m bgl/); assert.match(tip,/M\+3/);
});

test('selector and map resolve the same stable IDs without name fallback', () => {
  const states=[{state_id:'TN',state_name:'Tamil Nadu'},{state_id:'HR',state_name:'Haryana'}];
  assert.deepEqual(searchStates(states,'tamil na').map(r=>r.state_id),['TN']);
  assert.equal(stateSelectionId(states,'hr'),'HR');
  assert.equal(stateSelectionId(states,'fake'),null);
  assert.equal(matchState({state_id:'HR'},buildStateLookup(states)).state_name,'Haryana');
  assert.equal(matchState({state_name:'Haryana'},buildStateLookup(states)),null);
  assert.throws(()=>buildStateLookup([states[0],states[0]]),/Duplicate/);
});

test('state API calls fix twelve-month horizon, encode identity and preserve 503 abstention', async t => {
  const calls=[];
  t.mock.method(globalThis,'fetch',async url=>{calls.push(url); return {ok:false,status:503,json:async()=>({...fixture(),status:'model_unavailable',forecast:[],message:'Missing model'})};});
  const result=await fetchStatePredict('TN',12,'2026-10-25');
  assert.equal(result.status,'model_unavailable'); assert.equal(result.forecast.length,0);
  assert.equal(calls[0],'/api/predict/state/TN?horizon=12&as_of=2026-10-25');
  await assert.rejects(fetchStatesSummary(),/503/);
  assert.equal(calls[1],'/api/states/summary?horizon=12');
  assert.equal(calls.length,2);
});

test('summary rejects duplicate IDs and stale alternative-model payloads', () => {
  const value={product:'state_groundwater_summary',model_version:STATE_XGB_VERSION,horizon_months:12,as_of:'2026-10-25',total_states:0,states:[],available_states_count:0,insufficient_data_states_count:0};
  assert.equal(validateStatesSummary(value),value);
  assert.throws(()=>validateStatesSummary({...value,model_version:'1.0'}),/Invalid/);
});

test('active routes do not expose old alternative-model controls; scientific modules stay preserved', () => {
  const app=readFileSync(new URL('../src/App.jsx',import.meta.url),'utf8');
  assert.doesNotMatch(app,/<ResearchForecast/);
  assert.match(app,/path="\/states\/:id"/);
  assert.match(readFileSync(new URL('../src/components/ResearchForecast.jsx',import.meta.url),'utf8'),/annual baseline/);
});

test('district XGBoost failures perform one request without a scenario fallback', async () => {
  const reads=[];
  await assert.rejects(loadDistrictForecast('HR-Kaithal', async id=>{reads.push(id);throw new Error('Model unavailable');}),/Model unavailable/);
  assert.deepEqual(reads,['HR-Kaithal']);
  await assert.rejects(loadDistrictForecast('HR-Kaithal', async()=>({district_id:'HR-Kaithal',product:'experimental_12month_scenario'})),/Expected product/);
});
