import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement, Children } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadJsx } from './helpers/loadJsx.js';
import { validateStateMedianForecast, validateMedianStatesSummary, medianStateDetails, medianMethodLabel, STATE_MEDIAN_TIERED_VERSION, STATE_MEDIAN_POLICY_VERSION } from '../src/components/stateMedianForecastContract.js';
import { medianStateMapDescription, getMedianStateColor } from '../src/stateMap.js';
const { StateMedianForecastView, stateMedianForecastPlot, StateMedianTooltip } = await loadJsx(new URL('../src/components/StateMedianForecast.jsx', import.meta.url));
const { default: StateMedianSummaryTable } = await loadJsx(new URL('../src/components/StateMedianSummaryTable.jsx', import.meta.url));

// Synthetic UI fixtures only. Do not represent source observations or model evidence.
function fallback() {
  const reference = { date: '2020-01-01', gwl_m_bgl: 4, contributing_districts_count: 1, total_districts_in_state: 10,
    district_coverage_pct: 10, coverage_ratio: .1, training_eligible: false, observation_count: 1,
    observation_quality: 'low_coverage', is_observed: true, is_forecast: false };
  return { product: 'state_median_groundwater_12m_forecast', model_name: 'state_median_tiered', model_version: STATE_MEDIAN_TIERED_VERSION,
    policy_version: STATE_MEDIAN_POLICY_VERSION, forecast_method: 'persistence_fallback', promotion_status: 'experimental', status: 'forecast',
    state_id: 'TN', state_name: 'Tamil Nadu', units: 'm_bgl', horizon_months: 12, as_of: '2026-10-29', forecast_origin: '2026-10-01',
    computed_at: '2026-10-29T00:00:00Z', training_cutoff: null, model_sha256: null, features: ['latest_genuine_state_median'],
    genuine_observed_months: 1, genuine_observation_count: 1, latest_observation_date: reference.date, observation_age_months: 81,
    reference_observation: reference, historical_reference_date: reference.date, last_observed_gwl_m_bgl: 4,
    reference_age_months: 81, reference_is_stale: true, reference_training_eligible: false,
    contributing_districts_count: 1, total_districts_in_state: 10, district_coverage_pct: 10,
    fallback_reason: 'One genuine state month; insufficient XGBoost history.', history: [reference],
    forecast: Array.from({ length: 12 }, (_, i) => ({ target_date: new Date(Date.UTC(2026, 10 + i, 1)).toISOString().slice(0, 10), horizon: i + 1, predicted_gwl: 4, is_forecast: true, is_observed: false })),
    evaluation: { status: 'not_evaluated_for_fallback', n: 0, mae_m: null, rmse_m: null, period_start: null, period_end: null, description: 'No historical error calibration for this fallback.' },
    limitations: ['Synthetic fixture only.'] };
}

test('one genuine low-coverage stale observation supports a strictly identified persistence forecast', () => {
  const value = fallback(); assert.equal(validateStateMedianForecast(value, 'TN'), value);
  assert.equal(medianMethodLabel(value), 'Persistence fallback');
  for (const mutate of [v => { v.forecast[4].predicted_gwl = 8; }, v => { v.training_cutoff = '2019-12-01'; },
    v => { v.reference_observation = null; }, v => { v.genuine_observed_months = 0; }, v => { v.observation_age_months = 1; },
    v => { v.features = ['rainfall_lag1']; }, v => { v.fallback_reason = ''; },
    v => { v.evaluation = { status: 'historical_backtest', n: 1, mae_m: .2, rmse_m: .2, period_start: '2021-01-01', period_end: '2021-01-01' }; }]) {
    const bad = fallback(); mutate(bad); assert.throws(() => validateStateMedianForecast(bad, 'TN'), /Invalid state median forecast/);
  }
});

test('a few genuine observations retain deterministic fallback instead of weakening training requirements', () => {
  const value = fallback(); value.genuine_observed_months = 3; value.genuine_observation_count = 5;
  assert.equal(validateStateMedianForecast(value, 'TN').forecast.length, 12);
});

test('fallback chart, table and map label the method, genuine reference age and low coverage', () => {
  const value = fallback();
  const html = renderToStaticMarkup(createElement(StateMedianForecastView, { value }));
  assert.match(html, /Persistence fallback/); assert.match(html, /held constant for all 12 forecast months/);
  assert.match(html, /XGBoost was not used: One genuine state month/);
  assert.match(html, /2020-01-01 · 81 months old/); assert.match(html, /stale historical measurement/);
  assert.match(html, /below the XGBoost training-target criteria/); assert.match(html, /No historical error calibration/);
  assert.doesNotMatch(html, /State median XGBoost forecast|Held-out backtest MAE<\/dt><dd>0/);
  const line = Children.toArray(stateMedianForecastPlot(value).props.children).find(child => child.props.dataKey === 'predicted');
  assert.equal(line.props.name, 'Persistence fallback forecast');
  const details = medianStateDetails(value);
  assert.equal(getMedianStateColor(details), '#22c55e');
  assert.match(medianStateMapDescription(details), /Persistence fallback/);
  assert.match(medianStateMapDescription(details), /81 months old/);
  const table = renderToStaticMarkup(createElement(StateMedianSummaryTable, { states: [details], onSelect: () => {} }));
  assert.match(table, /Persistence fallback/); assert.match(table, /Below training-target coverage/); assert.match(table, /81 months old/);
  const tip = renderToStaticMarkup(createElement(StateMedianTooltip, { active: true, payload: [{ payload: { month: '2026-11', predicted: 4, observed: null, lowCoverage: null, horizon: 1, method: 'Persistence fallback' } }] }));
  assert.match(tip, /Persistence fallback · M\+1/);
});

test('no genuine observations produce no forecast while unknown service evidence stays explicitly unknown', () => {
  const value = { ...fallback(), forecast_method: 'no_observations', status: 'insufficient_data', message: 'No genuine observations.',
    genuine_observed_months: 0, genuine_observation_count: 0, latest_observation_date: null, observation_age_months: null,
    historical_reference_date: null, last_observed_gwl_m_bgl: null, reference_age_months: null, reference_observation: null,
    contributing_districts_count: 0, district_coverage_pct: 0, features: [], history: [], forecast: [],
    evaluation: { status: 'not_evaluated', n: 0, mae_m: null, rmse_m: null } };
  validateStateMedianForecast(value, 'TN');
  assert.equal(medianMethodLabel(value), 'No usable observations');
  const table = renderToStaticMarkup(createElement(StateMedianSummaryTable, { states: [medianStateDetails(value)], onSelect: () => {} }));
  assert.doesNotMatch(table, /Below training-target coverage/);
  const html = renderToStaticMarkup(createElement(StateMedianForecastView, { value }));
  assert.doesNotMatch(html, /View all 12 median estimates/);
  const missing = { ...value, status: 'model_unavailable', forecast_method: null, genuine_observed_months: null, genuine_observation_count: null, message: 'Published release missing.' };
  validateStateMedianForecast(missing, 'TN'); assert.equal(medianMethodLabel(missing), 'Method unavailable');
});

test('tiered summary checks method counts and exposes the same fallback reference as detail', () => {
  const value = fallback(), details = medianStateDetails(value);
  const summary = { product: 'state_median_groundwater_summary', model_name: value.model_name, model_version: value.model_version,
    policy_version: value.policy_version, as_of: value.as_of, horizon_months: 12, generation_id: 'synthetic-preview-only',
    total_states: 1, available_states_count: 1, insufficient_data_states_count: 0, states: [details],
    counts_by_forecast_method: { state_median_xgboost: 0, persistence_fallback: 1, no_observations: 0 } };
  assert.equal(validateMedianStatesSummary(summary), summary);
  assert.throws(() => validateMedianStatesSummary({ ...summary, counts_by_forecast_method: { state_median_xgboost: 1, persistence_fallback: 0, no_observations: 0 } }), /method counts/);
});
