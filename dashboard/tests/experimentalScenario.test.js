import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { fetchExperimentalScenario, fetchResearchGraph } from '../src/api.js';
import { followingCalendarMonths } from '../src/components/forecastGraph.js';
import { forecastView, scenarioChartRows, validateExperimentalScenario } from '../src/components/experimentalScenarioContract.js';
import { loadJsx } from './helpers/loadJsx.js';

function fixture(asOf = '2026-10-21', districtId = 'TS-Adilabad') {
  const months = followingCalendarMonths(asOf.slice(0, 7));
  const [year, month] = asOf.split('-').map(Number);
  return {
    product: 'experimental_12month_scenario', status: 'scenario', output_kind: 'assumption_based_scenario',
    district_id: districtId, horizon_months: 12, units: 'm_bgl', as_of: asOf, as_of_timezone: 'Asia/Kolkata',
    computed_at: '2026-10-21T12:00:00+00:00', forecast_issued_at: null,
    forecast_start: months[0], forecast_end: months[11], estimated_current_gwl: 5,
    source: { name: 'SYNTHETIC TEST FIXTURE ONLY: district history', scope: 'district_own_observed_history',
      units_qualification: 'SYNTHETIC TEST FIXTURE ONLY: repository m_bgl convention; certified datum unknown.',
      availability_verified: false, last_observed_month: '2020-05', last_observed_gwl: 6,
      data_age_months: (year-2020)*12+month-5, well_count: 3 },
    method: { name: 'damped_seasonal_trend', observed_month_count: 60, parameters_saved: false,
      observed_calendar_months: [1, 5, 8, 11], annual_seasonality: true },
    validation: { status: 'unvalidated_scenario', prospective_skill_verified: false, sufficient_for_operational_use: false },
    forecast: months.map((month, i) => ({ month, date: `${month}-01`, horizon_months: i+1, projected_gwl: 5+i/10 })),
    assumptions: ['SYNTHETIC TEST FIXTURE ONLY: repeating seasonal pattern'],
    limitations: ['SYNTHETIC TEST FIXTURE ONLY; no forecast skill'], unavailable_reasons: [],
  };
}

const { ScenarioView, scenarioPlot } = await loadJsx(new URL('../src/components/ExperimentalScenario.jsx', import.meta.url));

test('today-based scenario contains exactly twelve next full months across a year boundary', () => {
  const value = fixture();
  assert.equal(validateExperimentalScenario(value), value);
  assert.equal(scenarioChartRows(value).length, 12);
  assert.equal(value.forecast[0].month, '2026-11');
  assert.equal(value.forecast[11].month, '2027-10');
  assert.equal(validateExperimentalScenario(fixture('2025-12-31')).forecast[0].month, '2026-01');
  assert.equal(validateExperimentalScenario(fixture('2024-02-29')).forecast[11].month, '2025-02');
});

test('partial, duplicated, redated, nonfinite and incompatible-model paths are rejected', () => {
  for (const mutate of [v => v.forecast.pop(), v => { v.forecast[1].month = v.forecast[0].month; },
    v => { v.forecast[0].projected_gwl = NaN; }, v => { v.forecast[0].projected_gwl = -1; },
    v => { v.forecast[0].projected_gwl = '5'; }, v => { v.product = 'direct_12month_research_graph'; },
    v => { v.horizon_months = 6; }, v => { v.units = 'feet'; }, v => { v.as_of = '2026-02-30'; },
    v => { v.validation.prospective_skill_verified = true; }, v => { v.forecast_issued_at = v.computed_at; },
    v => { v.source.availability_verified = true; }, v => { v.source.last_observed_month = '2026-10'; },
    v => { v.source.data_age_months = 0; }, v => { v.source.last_observed_gwl = -1; },
    v => { v.source.scope = 'zone_fallback'; }, v => { delete v.source.name; },
    v => { v.source.units_qualification = ''; }]) {
    const value = fixture(); mutate(value);
    assert.throws(() => validateExperimentalScenario(value), /compatible twelve-month experimental/);
  }
  assert.throws(() => validateExperimentalScenario(fixture(), 'GJ-Gandhinagar'));
});

test('unavailable scope remains empty with no replacement points', () => {
  const value = fixture();
  Object.assign(value, { status: 'unavailable', forecast: [], estimated_current_gwl: null, unavailable_reasons: ['Unsupported scope'] });
  assert.equal(validateExperimentalScenario(value), value);
  assert.deepEqual(scenarioChartRows(value), []);
  value.forecast = fixture().forecast;
  assert.throws(() => validateExperimentalScenario(value));
});

test('mode defaults to today while explicitly requested historical origins remain historical', () => {
  assert.equal(forecastView(''), 'scenario');
  assert.equal(forecastView('?origin_month=2024-01'), 'historical');
  assert.equal(forecastView('?view=scenario&origin_month=2024-01'), 'scenario');
  assert.equal(forecastView('?view=historical'), 'historical');
});

test('scenario reads use a separate route and leave the historical request unchanged', async () => {
  const original = globalThis.fetch; const urls = [];
  globalThis.fetch = async url => { urls.push(url); return { ok: true, json: async () => ({ synthetic: true }) }; };
  try {
    await fetchExperimentalScenario('TS-Adilabad');
    await fetchExperimentalScenario('TS-Adilabad', '2026-10-21');
    await fetchResearchGraph('TS-Adilabad', '2024-01');
    assert.deepEqual(urls, ['/api/research/scenario/TS-Adilabad?months=12', '/api/research/scenario/TS-Adilabad?months=12&as_of=2026-10-21', '/api/research/graph/TS-Adilabad?months=12&origin_month=2024-01']);
  } finally { globalThis.fetch = original; }
});

test('rendered disclosure and table distinguish current estimate, stale observation and all twelve values', () => {
  const html = renderToStaticMarkup(createElement(ScenarioView, { value: fixture() }));
  assert.match(html, /Experimental estimate/);
  assert.match(html, /Unvalidated seasonal\/trend scenario/);
  assert.match(html, /As of 2026-10-21/);
  assert.match(html, /77.*calendar months/);
  assert.match(html, /Estimated current depth/);
  assert.match(html, /not current measurements or a validated real-time forecast/);
  assert.match(html, /acquisition times remain unknown/);
  assert.equal((html.match(/<th scope="row">/g) || []).length, 12);
  assert.match(html, /Nov 2026/);
  assert.match(html, /Oct 2027/);
  assert.match(html, /<details class="technical-details"><summary>Details<\/summary>/);
  const mainCard = html.split('<details class="technical-details">')[0];
  assert.doesNotMatch(mainCard, /SHA-256|Assumptions|Latest contributing well count/);
  assert.match(mainCard, /77 calendar months/);
});

test('read failure exposes retry without silently displaying historical estimates', () => {
  const html = renderToStaticMarkup(createElement(ScenarioView, { error: 'Source unavailable' }));
  assert.match(html, /Retry scenario/);
  assert.doesNotMatch(html, /<tbody>|M\+12 research estimate/);
});

test('arbitrary registered district owns all twelve chart rows and cannot receive a different district response', () => {
  const value = fixture('2026-10-21', 'HR-Kaithal');
  value.source.district_name = 'Kaithal'; value.source.state_name = 'Haryana';
  assert.equal(validateExperimentalScenario(value, 'HR-Kaithal'), value);
  assert.throws(() => validateExperimentalScenario(value, 'TS-Adilabad'));
  const plot = scenarioPlot(value, { width: 720, height: 380 });
  assert.equal(plot.props.data.length, 12);
  assert.deepEqual(plot.props.data.map(row => row.projected), value.forecast.map(row => row.projected_gwl));
  assert.deepEqual(plot.props.data.map(row => row.month), followingCalendarMonths('2026-10'));
  const html = renderToStaticMarkup(createElement(ScenarioView, { value }));
  assert.match(html, /Kaithal, Haryana \(HR-Kaithal\)/);
  assert.match(html, /Only this district’s own observed history is used/);
  assert.doesNotMatch(html, /Adilabad/);
});

test('valid zero depth estimates remain numbers instead of becoming unavailable', () => {
  const value = fixture('2026-10-21', 'GJ-Gandhinagar');
  value.source.last_observed_gwl = 0; value.estimated_current_gwl = 0;
  value.forecast.forEach(row => { row.projected_gwl = 0; });
  validateExperimentalScenario(value, 'GJ-Gandhinagar');
  assert.ok(scenarioChartRows(value).every(row => row.projected === 0));
  const html = renderToStaticMarkup(createElement(ScenarioView, { value }));
  assert.equal((html.match(/<td>0\.00<\/td>/g) || []).length, 12);
});

test('insufficient, missing and unreadable source reasons stay exact without substituting an Adilabad graph', () => {
  for (const reason of ['Insufficient observed history: 12 months; 24 required.',
    'No observed groundwater rows for HR-Kaithal.',
    'Repository feature source is unreadable; no scenario was calculated.',
    'Source units cannot be established from the configured snapshot.']) {
    const value = fixture('2026-10-21', 'HR-Kaithal');
    Object.assign(value, { status: 'unavailable', forecast: [], estimated_current_gwl: null, unavailable_reasons: [reason] });
    value.source = { availability_verified: false };
    validateExperimentalScenario(value, 'HR-Kaithal');
    const html = renderToStaticMarkup(createElement(ScenarioView, { value }));
    assert.ok(html.includes(reason));
    assert.match(html, /No other district, historical origin or model has been substituted/);
    assert.doesNotMatch(html, /Adilabad|<tbody>|recharts/);
  }
});

test('unknown provenance is disclosed and no well count, publication time or certified datum is invented', () => {
  const value = fixture('2026-10-21', 'HR-Kaithal');
  value.source.well_count = null;
  value.source.source_snapshot_sha256 = null;
  const html = renderToStaticMarkup(createElement(ScenarioView, { value }));
  assert.match(html, /certified datum unknown/);
  assert.match(html, /Latest contributing well count: unknown/);
  assert.match(html, /Source snapshot SHA-256: unavailable/);
  assert.match(html, /First availability and actual acquisition times remain unknown/);
  assert.match(html, /not a climate model/);
  assert.match(html, /Registry coverage does not establish observation coverage or nationwide forecasting accuracy/);
});

test('source metadata and unavailable reasons render as escaped text', () => {
  const value = fixture('2026-10-21', 'HR-Kaithal');
  value.source.district_name = '<script>district</script>';
  value.source.units_qualification = '<img src=x onerror=alert(1)>';
  const html = renderToStaticMarkup(createElement(ScenarioView, { value }));
  assert.match(html, /&lt;script&gt;district&lt;\/script&gt;/);
  assert.match(html, /&lt;img/);
  assert.doesNotMatch(html, /<script>|<img/);
});

test('Home promotes district exploration without historical examples or hard-coded registry claims', () => {
  const home = readFileSync(new URL('../src/pages/Home.jsx', import.meta.url), 'utf8');
  assert.match(home, /experimental estimates for the next 12 months/);
  assert.match(home, /totalDistricts/);
  assert.doesNotMatch(home, /origin_month|historical graph example|A registry of 725|nationwide accuracy is verified/);
});

test('sparse calendar phases disclose inferred seasonal values rather than monthly measurements', () => {
  const value = fixture('2026-10-21', 'HR-Kaithal');
  value.method.unobserved_calendar_months = [2, 3, 6, 7, 9];
  const html = renderToStaticMarkup(createElement(ScenarioView, { value }));
  assert.match(html, /Calendar phases without observed history: 2, 3, 6, 7, 9/);
  assert.match(html, /not monthly measurements/);
});
