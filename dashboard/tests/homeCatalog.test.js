import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { mergeDistrictScores, validateDistrictCatalog, validateHomeForecastSummary } from '../src/components/districtCatalog.js';
import { loadJsx } from './helpers/loadJsx.js';
const { ForecastCoverage, RiskIndexNotice } = await loadJsx(new URL('../src/components/ForecastCoverage.jsx', import.meta.url));

const districts = [
  { district_id:'HR-Kaithal',name:'Kaithal',state:'Haryana',state_id:'HR' },
  { district_id:'AN-Nicobars',name:'Nicobars',state:'Andaman and Nicobar Islands',state_id:'AN' },
];
function summary() {
  return {product:'state_groundwater_summary',model_version:'3.0-state-tiered',horizon_months:12,as_of:'2026-10-25',
    total_states:1,available_states_count:1,insufficient_data_states_count:0,districts_total:4,districts_forecast:4,
    evidence_tier_counts:{A:1,B:1,C:1,D:1},states:[{state_id:'HR',state_name:'Haryana',status:'available',
      total_districts:4,contributing_districts:4,district_coverage_pct:100,current_gwl_m_bgl:10,
      forecast_12m_gwl_m_bgl:11,projected_change_12m_m:1,evidence_tier_counts:{A:1,B:1,C:1,D:1}}]};
}

test('all registered districts survive absent, partial and unrelated risk records',()=>{
  const catalog=validateDistrictCatalog({total:districts.length,districts});
  assert.equal(mergeDistrictScores(catalog.districts,[]).length,2);
  const merged=mergeDistrictScores(catalog.districts,[{district_id:'HR-Kaithal',name:'Wrong name',state:'Wrong state',score:0,tier:'Safe'},
    {district_id:'ZZ-Unknown',name:'Unknown',score:100,tier:'Crisis'}]);
  assert.deepEqual(merged.map(d=>d.district_id),districts.map(d=>d.district_id));
  assert.equal(merged[0].score,0);assert.equal(merged[0].name,'Kaithal');assert.equal(merged[0].state,'Haryana');
  assert.equal(merged[1].score,null);assert.equal(merged[1].tier,null);
});

test('catalog integrity rejects duplicate IDs and wrong state membership',()=>{
  assert.throws(()=>validateDistrictCatalog({total:2,districts:[districts[0],districts[0]]}),/identities/);
  assert.throws(()=>validateDistrictCatalog({total:1,districts:[{...districts[0],state_id:'AN'}]}),/identities/);
});

test('forecast coverage validates global counts against actual state evidence',()=>{
  assert.equal(validateHomeForecastSummary(summary()).districts_forecast,4);
  const wrong=summary();wrong.evidence_tier_counts={A:2,C:1,D:1};
  assert.throws(()=>validateHomeForecastSummary(wrong),/differ/);
  const incomplete=summary();incomplete.districts_forecast=3;
  assert.throws(()=>validateHomeForecastSummary(incomplete),/incomplete/);
});

test('Home displays real forecast counts without assigning risk tiers to fallbacks',()=>{
  const html=renderToStaticMarkup(createElement(MemoryRouter,null,createElement(ForecastCoverage,{summary:summary(),loading:false})));
  assert.match(html,/4 \/ 4 districts/);assert.match(html,/12 monthly outputs/);
  for(const tier of ['A','B','C','D'])assert.match(html,new RegExp('Tier '+tier));
  assert.match(html,/Zero-history references/);assert.match(html,/does not establish accuracy/);
  assert.doesNotMatch(html,/Safe|Crisis/);
});

test('missing or failed risk scores explain the limitation without blocking forecasts',()=>{
  for(const error of [null,'Scores fetch failed: 503']) {
    const html=renderToStaticMarkup(createElement(RiskIndexNotice,{ready:false,loading:false,error}));
    assert.match(html,/do not require risk scores/);assert.match(html,/Check risk scores again/);
    assert.doesNotMatch(html,/empty-state|disabled/);
  }
});
