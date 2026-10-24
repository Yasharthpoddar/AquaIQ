import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { followingCalendarMonths } from '../src/components/forecastGraph.js';
import { loadJsx } from './helpers/loadJsx.js';

const { default: ClimateInputs, ClimateInputsView } = await loadJsx(new URL('../src/components/ClimateInputs.jsx', import.meta.url));
const fixture = () => ({
  status:'available',asOf:'2026-10-24',methodLabel:'Historical monthly averages',estimateType:'district_level',
  sourceZone:null,partial:false,includesFilledHistory:true,
  sourceDates:{rainfall:'2026-09-01',temperature:'2025-02-01',evapotranspiration:null},
  origin:{month:'2026-10',rainfall:20,temperature:17,evapotranspiration:90,basisLabel:'Historical monthly averages'},
  rows:followingCalendarMonths('2026-10').slice(0,6).map((month,index)=>({month,rainfall:index*10,temperature:-5+index,evapotranspiration:30+index})),
});
const render = props => renderToStaticMarkup(createElement(ClimateInputsView,{districtId:'HR-Kaithal',...props}));

test('weather table presents only the six exact input months, units and assumption status', () => {
  const data = fixture();
  const before = structuredClone(data);
  const html = render({data});
  const table = html.split('aria-label="Six-month weather input table"')[1].split('</table>')[0];
  assert.equal((table.match(/<th scope="row">/g)||[]).length,6);
  assert.match(table,/Nov 2026/);
  assert.match(table,/Apr 2027/);
  assert.doesNotMatch(table,/May 2027|Oct 2027/);
  assert.match(table,/Rainfall/);
  assert.match(table,/Temperature/);
  assert.match(table,/Evapotranspiration/);
  assert.match(table,/mm\/month/);
  assert.match(table,/°C/);
  assert.match(table,/<td>0\.00<\/td>/);
  assert.match(table,/<td>-5\.00<\/td>/);
  assert.match(html,/not weather predictions/);
  assert.match(html,/12-month seasonal\/trend graph above does not use weather inputs/);
  assert.match(html,/separate evaporation forecast is not provided/);
  assert.deepEqual(data,before);
});

test('source dates remain per-field, unknown metadata stays unknown and origin values remain separate', () => {
  const html = render({data:fixture()});
  assert.match(html,/Rainfall<\/th><td>Sep 2026/);
  assert.match(html,/Temperature<\/th><td>Feb 2025/);
  assert.match(html,/Evapotranspiration<\/th><td>Unknown/);
  assert.match(html,/Origin-month weather inputs.*Oct 2026/);
  assert.match(html,/<td>20\.00<\/td>/);
  assert.match(html,/<td>17\.00<\/td>/);
  assert.match(html,/<td>90\.00<\/td>/);
  assert.match(html,/may include forward-filled values/);
  assert.match(html,/do not certify acquisition or publication times/);
});

test('partial values, zone history and unreported origin inputs stay explicit', () => {
  const data = fixture();
  data.partial = true; data.rows[0].rainfall = null; data.rows[0].temperature = null;
  data.estimateType = 'zone_fallback'; data.sourceZone = 'Fixture zone'; data.origin = null;
  data.includesFilledHistory = null;
  const html = render({data});
  assert.match(html,/Uses zone-based history: Fixture zone/);
  assert.match(html,/Some inputs were not available/);
  assert.match(html,/<td>Unavailable<\/td><td>Unavailable<\/td>/);
  assert.match(html,/imputation status is unknown/);
  assert.doesNotMatch(html,/Origin-month weather inputs/);
});

test('loading, service failure and unavailable evidence do not show invented table values', () => {
  const loading = render({loading:true});
  assert.match(loading,/aria-busy="true"/);
  assert.match(loading,/Loading rainfall/);
  assert.doesNotMatch(loading,/<tbody>/);
  const error = render({error:'Service failed'});
  assert.match(error,/role="alert"/);
  assert.match(error,/Retry climate inputs/);
  assert.doesNotMatch(error,/<tbody>/);
  const missing = render({data:{status:'unavailable',asOf:'2026-10-24',methodLabel:'Unavailable',message:'Not enough historical weather.'}});
  assert.match(missing,/Climate inputs unavailable/);
  assert.match(missing,/Not enough historical weather/);
  assert.doesNotMatch(missing,/<tbody>/);
});

test('the actual retry control invokes its parent callback', () => {
  let retries = 0;
  const root = ClimateInputsView({districtId:'HR-Kaithal',error:'Failed',onRetry:()=>{retries+=1;}});
  const visit = node => {
    if (!node || typeof node !== 'object') return [];
    if (Array.isArray(node)) return node.flatMap(visit);
    return [node,...visit(node.props?.children)];
  };
  const button = visit(root).find(node=>node.type==='button' && node.props.children==='Retry climate inputs');
  assert.ok(button);
  button.props.onClick();
  assert.equal(retries,1);
});

test('district, zone and service-provided strings render as text rather than HTML', () => {
  const data = fixture(); data.estimateType='zone_fallback';data.sourceZone='<img src=x onerror=alert(1)>';
  const html = render({data,districtId:'<script>district</script>',error:'<script>error</script>'});
  assert.match(html,/&lt;script&gt;district/);
  assert.match(html,/&lt;img/);
  assert.doesNotMatch(html,/<script>|<img/);
});

test('the component is mounted under the actual scenario with its district and exact as-of context', () => {
  const source = readFileSync(new URL('../src/components/ExperimentalScenario.jsx',import.meta.url),'utf8');
  assert.match(source,/<ClimateInputs key=\{`\$\{districtId\}:\$\{value\.as_of\}`\} districtId=\{districtId\} asOf=\{value\.as_of\}/);
  const html = renderToStaticMarkup(createElement(ClimateInputs,{districtId:'HR-Kaithal',asOf:'2026-10-24'}));
  assert.match(html,/Rainfall &amp; climate inputs/);
  assert.match(html,/Loading rainfall/);
});
