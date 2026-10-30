import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { fetchPrimaryStates, fetchPrimaryStatesSummary, fetchPrimaryStatePredict, fetchStatesSummary, fetchStatePredict } from '../src/api.js';
import { validateMedianStatesRegistry, validateMedianStatesSummary, validateStateMedianForecast, medianStateDetails } from '../src/components/stateMedianForecastContract.js';
import { getMedianStateColor, medianStateMapDescription } from '../src/stateMap.js';
import { createElement, Children } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadJsx } from './helpers/loadJsx.js';
const { default: StateMedianSummaryTable } = await loadJsx(new URL('../src/components/StateMedianSummaryTable.jsx', import.meta.url));

const registry = () => ({ total: 2, as_of: null, horizon_months: 12, states: [
  { state_id: 'TN', state_name: 'Tamil Nadu', state_type: 'State', districts: ['TN-A', 'TN-B'], total_districts: 2 },
  { state_id: 'AN', state_name: 'Andaman', state_type: 'Union Territory', districts: ['AN-A'], total_districts: 1 },
] });
const row = () => ({ state_id: 'TN', state_name: 'Tamil Nadu', status: 'available', last_observed_gwl_m_bgl: 9,
  historical_reference_date: '2026-01-01', forecast_12m_gwl_m_bgl: 10, projected_change_12m_m: 1,
  contributing_districts_count: 2, total_districts_in_state: 2, district_coverage_pct: 100, forecast_month_count: 12 });
const summary = () => ({ product: 'state_median_groundwater_summary', model_name: 'state_median_xgboost', model_version: '1.0-state-median-xgboost',
  as_of: '2026-10-29', generation_id: 'generation-one', horizon_months: 12, total_states: 2, available_states_count: 1, insufficient_data_states_count: 1,
  forecast_month_count: 12, unavailable_states_count: 1, states: [row(), { ...row(), state_id: 'AN', state_name: 'Andaman', status: 'insufficient_data', last_observed_gwl_m_bgl: null,
    historical_reference_date: null, forecast_12m_gwl_m_bgl: null, projected_change_12m_m: null,
    contributing_districts_count: 0, total_districts_in_state: 1, district_coverage_pct: 0, forecast_month_count: 0 }] });

test('primary registry permits no published vintage while preserving canonical district navigation', () => {
  assert.equal(validateMedianStatesRegistry(registry()).as_of, null);
  const bad = registry(); bad.states[0].districts = ['AN-A', 'TN-B'];
  assert.throws(() => validateMedianStatesRegistry(bad), /membership/);
});

test('primary summary validates median identity, real historical references and complete state membership', () => {
  assert.equal(validateMedianStatesSummary(summary(), registry()).states.length, 2);
  for (const mutate of [s => { s.product = 'state_groundwater_summary'; }, s => { s.states[0].projected_change_12m_m = 5; },
    s => { s.generation_id = null; }, s => { s.states[1].forecast_12m_gwl_m_bgl = 8; },
    s => { s.states[0].historical_reference_date = '2027-01-01'; }, s => { s.available_states_count = 2; },
    s => { s.states[0].total_districts_in_state = 3; }, s => { s.forecast_month_count = 24; },
    s => { s.states[0].forecast_month_count = 11; }, s => { s.states[1].forecast_month_count = 12; }]) {
    const bad = summary(); mutate(bad);
    assert.throws(() => validateMedianStatesSummary(bad, registry()), /Invalid state median forecast/);
  }
});

test('median map uses explicitly dated historical median rather than legacy current depth', () => {
  const state = { ...row(), current_gwl_m_bgl: 100 };
  assert.equal(getMedianStateColor(state), '#eab308');
  assert.equal(getMedianStateColor({ ...state, last_observed_gwl_m_bgl: null }), '#e2e8f0');
  assert.equal(getMedianStateColor({ ...state, status: 'insufficient_data', projected_change_12m_m: null }, 'delta'), '#e2e8f0');
  const label = medianStateMapDescription(state);
  assert.match(label, /Observed reference median: 9.00 m bgl \(2026-01-01\)/);
  assert.match(label, /M\+12 median forecast: 10.00/);
  assert.doesNotMatch(label, /current|Tier|100.00/);
  assert.match(medianStateMapDescription({ ...state, status: 'insufficient_data' }), /Insufficient historical data/);
});

test('selected median cards derive change only from the actual observed reference', () => {
  const details = medianStateDetails({ state_id: 'TN', state_name: 'Tamil Nadu', status: 'forecast', last_observed_gwl_m_bgl: 9,
    historical_reference_date: '2026-01-01', contributing_districts_count: 2, total_districts_in_state: 2,
    district_coverage_pct: 100, estimated_current_gwl_m_bgl: 50, forecast: [{ predicted_gwl: 10 }] });
  assert.equal(details.projected_change_12m_m, 1);
  assert.equal(details.last_observed_gwl_m_bgl, 9);
  assert.equal(details.estimated_current_gwl_m_bgl, undefined);
  assert.equal(medianStateDetails({ ...details, status: 'insufficient_data', forecast: [] }).forecast_12m_gwl_m_bgl, null);
});

test('versioned API pins exact model generation without changing legacy Home or district reads', async t => {
  const urls = [];
  t.mock.method(globalThis, 'fetch', async url => { urls.push(url); return { ok: true, json: async () => ({}) }; });
  await fetchPrimaryStates(); await fetchPrimaryStatesSummary();
  await fetchPrimaryStatePredict('TN', '2026-10-29', 'generation-one');
  await fetchStatesSummary(); await fetchStatePredict('TN', 12, '2026-10-25');
  assert.deepEqual(urls, ['/api/v2/states', '/api/v2/states/summary?horizon=12',
    '/api/v2/predict/state/TN?horizon=12&as_of=2026-10-29&generation_id=generation-one',
    '/api/states/summary?horizon=12', '/api/predict/state/TN?horizon=12&as_of=2026-10-25']);
});

test('detail generation is checked before rendering values from a pinned summary', () => {
  const payload = { product: 'state_median_groundwater_12m_forecast', model_name: 'state_median_xgboost', model_version: '1.0-state-median-xgboost',
    state_id: 'TN', units: 'm_bgl', horizon_months: 12, promotion_status: 'experimental', status: 'model_unavailable',
    as_of: '2026-10-29', forecast_origin: '2026-10-01', computed_at: '2026-10-29T00:00:00Z', training_cutoff: null,
    contributing_districts_count: 0, total_districts_in_state: 2, district_coverage_pct: 0, history: [], forecast: [],
    generation_id: 'generation-one', message: 'No matching artifact', evaluation: { status: 'unavailable', n: 0, mae_m: null, rmse_m: null } };
  assert.equal(validateStateMedianForecast(payload, 'TN', '2026-10-29', 'generation-one'), payload);
  assert.throws(() => validateStateMedianForecast(payload, 'TN', '2026-10-29', 'generation-two'), /generation differs/);
});

test('median comparison table renders real dated values, preserves abstention and selection callbacks', () => {
  let chosen;
  const table = StateMedianSummaryTable({ states: summary().states, selectedId: 'TN', onSelect: id => { chosen = id; } });
  const html = renderToStaticMarkup(table);
  assert.match(html, /Observed reference median/); assert.match(html, /2026-01-01/);
  assert.match(html, /9.00 m bgl/); assert.match(html, /\+1.00 m/);
  assert.match(html, /Insufficient history/); assert.match(html, /No genuine reference/);
  assert.doesNotMatch(html, /current depth|Tier|fixed panel/i);
  function buttons(element) {
    if (!element || typeof element !== 'object') return [];
    return [...(element.type === 'button' ? [element] : []), ...Children.toArray(element.props?.children).flatMap(buttons)];
  }
  buttons(table)[1].props.onClick(); assert.equal(chosen, 'AN');
  assert.match(renderToStaticMarkup(createElement(StateMedianSummaryTable, { states: [], onSelect: () => {} })), /No states match/);
});

test('primary page has one controlled median chart and explicit build-time legacy rollback', () => {
  const source = readFileSync(new URL('../src/pages/States.jsx', import.meta.url), 'utf8');
  assert.equal((source.match(/<StateMedianForecastView /g) || []).length, 1);
  assert.match(source, /fetchPrimaryStatePredict\(selectedId, asOf, generationId\)/);
  assert.match(source, /mode="median"/);
  assert.match(source, /VITE_STATE_FORECAST_MODE/);
  assert.match(source, /registeredState.districts.map/);
  assert.doesNotMatch(source, /<StateForecastGraph|estimated_current_gwl|evidence_tier_counts/);
  const rollback = readFileSync(new URL('../src/pages/LegacyStates.jsx', import.meta.url), 'utf8');
  assert.match(rollback, /<StateForecastGraph/);
  assert.doesNotMatch(rollback, /<StateMedianForecast/);
});
