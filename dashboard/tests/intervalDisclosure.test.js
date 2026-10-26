import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadJsx } from './helpers/loadJsx.js';
import { validateClimate12mForecast, climate12mChartRows } from '../src/components/climateForecast12mContract.js';
const { ClimateForecast12mView } = await loadJsx(new URL('../src/components/DistrictForecastGraph.jsx', import.meta.url));

function value(status='unavailable') {
  return { product:'climate_informed_12m_forecast',model_version:'1.0-reference-12m',district_id:'HR-Z',
    status:'forecast',as_of:'2026-10-26',forecast_origin:'2026-10-01',timezone:'Asia/Kolkata',
    horizon_months:12,units:'m_bgl',evidence_tier:'C',observation_count:0,
    forecast_method:'regional_seasonal_reference',projection_method:'regional_seasonal_reference',
    estimate_type:'regional_reference',warning:'No local groundwater observations.',
    forecast_start:'2026-11',forecast_end:'2027-10',estimated_current_gwl:10,last_observed_date:null,
    uncertainty:{status,policy_version:'2.0-empirical-error-band-disclosure',local_coverage_guarantee:false,
      reason:'Calibration support is insufficient; point estimates remain available.'},
    forecast:Array.from({length:12},(_,i)=>({horizon:i+1,
      month:new Date(Date.UTC(2026,10+i,1)).toISOString().slice(0,7),date:new Date(Date.UTC(2026,10+i,1)).toISOString().slice(0,10),
      predicted_gwl:10,delta_from_current_m:0,interval_status:status,
      ...(status==='unavailable'?{}:{lower_gwl:0,upper_gwl:20}),
      weather:{rainfall_mm:null,temperature_c:null,evapotranspiration_mm:null}}))};
}

test('unavailable intervals retain every point and disclose missing ranges visibly',()=>{
  const v=validateClimate12mForecast(value(),'HR-Z');
  assert.equal(climate12mChartRows(v).length,12);
  assert.ok(climate12mChartRows(v).every(row=>row.predicted===10&&row.lower===undefined));
  const html=renderToStaticMarkup(createElement(ClimateForecast12mView,{value:v}));
  assert.match(html,/Uncertainty ranges unavailable/);
  assert.match(html,/point estimates remain available/);
  assert.match(html,/no guaranteed local coverage/);
});

test('empirical undercoverage carries the actual pooled denominator without a local claim',()=>{
  const v=value('empirical_undercovered');
  v.uncertainty.historical_validation={covered_cases:3,band_cases:15,band_districts:15};
  validateClimate12mForecast(v);
  const html=renderToStaticMarkup(createElement(ClimateForecast12mView,{value:v}));
  assert.match(html,/showed undercoverage/);
  assert.match(html,/3 of 15 cases/);
  assert.match(html,/not this district/);
  assert.match(html,/uncalibrated/);
});

test('new uncertainty status cannot contradict numerical bounds or claim local probability',()=>{
  const v=value();v.forecast[0].lower_gwl=0;v.forecast[0].upper_gwl=20;
  assert.throws(()=>validateClimate12mForecast(v),/contradicts/);
  const claim=value('historical_reference_only');claim.uncertainty.local_coverage_guarantee=true;
  assert.throws(()=>validateClimate12mForecast(claim),/uncertainty disclosure/);
});

test('upper bound without lower bound is rejected for legacy payloads too',()=>{
  const v=value();delete v.uncertainty;v.forecast[0].upper_gwl=20;
  assert.throws(()=>validateClimate12mForecast(v),/prediction range/);
});

test('legacy unavailable metadata cannot display stale partial historical bands',()=>{
  const v=value();delete v.uncertainty.policy_version;
  v.forecast[0].lower_gwl=0;v.forecast[0].upper_gwl=20;
  const rows=climate12mChartRows(v);
  assert.equal(rows[0].lower,undefined);
  assert.equal(rows[0].upper,undefined);
  assert.equal(rows[0].predicted,10);
});
