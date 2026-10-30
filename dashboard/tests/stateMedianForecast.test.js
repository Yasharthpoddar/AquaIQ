import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement, Children } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { readFileSync } from 'node:fs';
import { loadJsx } from './helpers/loadJsx.js';
import { fetchStateMedianPredict, fetchStatePredict } from '../src/api.js';
import { STATE_MEDIAN_VERSION, STATE_MEDIAN_PRODUCT, validateStateMedianForecast, stateMedianChartRows } from '../src/components/stateMedianForecastContract.js';

const { StateMedianForecastView, StateMedianTooltip, stateMedianForecastPlot, loadStateMedianForecast } = await loadJsx(new URL('../src/components/StateMedianForecast.jsx', import.meta.url));

// Synthetic fixtures exercise rendering/contracts only; these are not model results.
function fixture() {
  return { product: STATE_MEDIAN_PRODUCT, model_name: 'state_median_xgboost', model_version: STATE_MEDIAN_VERSION,
    state_id: 'TN', state_name: 'Tamil Nadu', units: 'm_bgl', horizon_months: 12, promotion_status: 'experimental', status: 'forecast',
    as_of: '2026-10-25', forecast_origin: '2026-10-01', computed_at: '2026-10-25T06:00:00Z', training_cutoff: '2026-09-01',
    contributing_districts_count: 2, total_districts_in_state: 4, district_coverage_pct: 50,
    history: [
      { date: '2026-07-01', gwl_m_bgl: 0, contributing_districts_count: 2, total_districts_in_state: 4, district_coverage_pct: 50, coverage_ratio: .5, training_eligible: true, observation_count: 2, observation_quality: 'observed' },
      { date: '2026-09-01', gwl_m_bgl: 6, contributing_districts_count: 1, total_districts_in_state: 4, district_coverage_pct: 25, coverage_ratio: .25, training_eligible: false, observation_count: 1, observation_quality: 'low_coverage' },
    ],
    forecast: Array.from({ length: 12 }, (_, i) => ({ horizon: i + 1, target_date: new Date(Date.UTC(2026, 10 + i, 1)).toISOString().slice(0, 10), predicted_gwl: i / 10, is_forecast: true, is_observed: false })),
    evaluation: { status: 'historical_backtest', mae_m: 1.2, rmse_m: 1.5, n: 12, period_start: '2024-01-01', period_end: '2024-12-01', description: 'Held-out synthetic fixture',
      horizons: [1], states_evaluated: 1, unique_state_month_targets: 1, comparison_states_evaluated: 17, comparison_unique_state_month_targets: 17,
      evaluated_artifact_training_cutoff: '2019-12-01', artifact_role: 'frozen_historical_reference' },
    limitations: ['Synthetic UI test fixture only.'] };
}

test('median contract requires explicit model identity, calendar, provenance and held-out metrics', () => {
  const good = fixture();
  assert.equal(validateStateMedianForecast(good, 'TN', good.as_of), good);
  for (const mutate of [value => { value.model_version = '3.0-state-tiered'; }, value => { value.state_id = 'HR'; },
    value => { value.forecast[0].is_observed = true; }, value => { value.forecast.pop(); },
    value => { value.forecast[0].target_date = '2026-10-01'; }, value => { value.forecast[0].predicted_gwl = null; },
    value => { value.training_cutoff = '2027-01-01'; }, value => { value.district_coverage_pct = 80; },
    value => { value.evaluation.n = 0; }, value => { value.evaluation.period_end = '2027-01-01'; },
    value => { value.history[0].coverage_ratio = .2; }, value => { value.history[0].gwl_m_bgl = null; }]) {
    const bad = fixture(); mutate(bad);
    assert.throws(() => validateStateMedianForecast(bad, 'TN', '2026-10-25'), /Invalid state median forecast/);
  }
});

test('median chart retains zero, missing months and low coverage without bridging to forecasts', () => {
  const rows = stateMedianChartRows(fixture());
  assert.equal(rows.find(row => row.month === '2026-07').observed, 0);
  assert.equal(rows.find(row => row.month === '2026-08').observed, null);
  assert.equal(rows.find(row => row.month === '2026-09').observed, null);
  assert.equal(rows.find(row => row.month === '2026-09').lowCoverage, 6);
  assert.equal(rows.find(row => row.month === '2026-10').predicted, null);
  assert.equal(rows.find(row => row.month === '2026-11').observed, null);
  assert.deepEqual(rows.filter(row => row.predicted !== null).map(row => row.predicted), fixture().forecast.map(row => row.predicted_gwl));
});

test('median plot contains separate disconnected observation/forecast lines and an origin marker', () => {
  const children = Children.toArray(stateMedianForecastPlot(fixture()).props.children);
  const lines = children.filter(child => ['observed', 'predicted', 'lowCoverage'].includes(child.props.dataKey));
  assert.deepEqual(lines.map(line => line.props.dataKey), ['observed', 'lowCoverage', 'predicted']);
  assert.ok(lines.every(line => line.props.connectNulls === false));
  const lowCoverage = lines.find(line => line.props.dataKey === 'lowCoverage');
  assert.equal(lowCoverage.props.stroke, '#94a3b8');
  assert.equal(lowCoverage.props.strokeWidth, 0); // Visible legend without a path connecting low-coverage readings.
  assert.equal(lowCoverage.props.legendType, 'circle');
  assert.ok(lowCoverage.props.dot.r >= 3);
  assert.equal(children.find(child => child.props.x === '2026-10')?.props.label.value, 'Forecast origin');
});

test('unavailable median model shows history and honest unavailable metrics without forecast rows', () => {
  const value = { ...fixture(), status: 'insufficient_data', training_cutoff: null, forecast: [], message: 'Only two eligible state months.',
    evaluation: { status: 'unavailable', n: 0, mae_m: null, rmse_m: null, description: 'No qualifying held-out targets.' } };
  validateStateMedianForecast(value, 'TN');
  const html = renderToStaticMarkup(createElement(StateMedianForecastView, { value }));
  assert.match(html, /Insufficient historical data for this model/);
  assert.match(html, /Only two eligible state months/);
  assert.match(html, /No qualifying held-out targets/);
  assert.match(html, /Historical reference coverage/);
  assert.doesNotMatch(html, /View all 12 median estimates/);
});

test('median view presents coverage, model/version and historical test period separately', () => {
  const html = renderToStaticMarkup(createElement(StateMedianForecastView, { value: fixture() }));
  assert.match(html, /2 \/ 4 districts · 50.0%/);
  assert.match(html, /Held-out backtest MAE/);
  assert.match(html, /Held-out backtest MAE<\/dt><dd>1.20 m<\/dd>/);
  assert.match(html, /Held-out backtest RMSE<\/dt><dd>1.50 m<\/dd>/);
  assert.match(html, /2024-01-01–2024-12-01; 12 eligible forecast cases/);
  assert.match(html, /1.0-state-median-xgboost/);
  assert.match(html, /Evaluated horizons: M\+1/);
  assert.match(html, /across 1 state\./);
  assert.match(html, /Overall paired historical comparison: 17 states and 17 distinct state-month targets/);
  assert.match(html, /frozen historical reference artifact trained through 2019-12-01/);
  assert.match(html, /rather than a held-out test of the refitted serving artifact/);
  assert.ok(html.indexOf('Evaluation: 2024-01-01') > html.indexOf('<details class="technical-details"'));
  assert.match(html, /Historical error period: 2024-01-01–2024-12-01/);
  assert.match(html, /typical district/);
  assert.doesNotMatch(html, /accuracy score/i);
  assert.equal((html.match(/scope="row"/g) || []).length, 12);
});

test('loading and service errors suppress stale median evidence and retry invokes callback', () => {
  const loading = renderToStaticMarkup(createElement(StateMedianForecastView, { value: fixture(), loading: true }));
  assert.match(loading, /Loading state median evidence/); assert.doesNotMatch(loading, /View all 12/);
  let retried = false;
  const view = StateMedianForecastView({ value: fixture(), error: 'Service unavailable', onRetry: () => { retried = true; } });
  const html = renderToStaticMarkup(view);
  assert.match(html, /Service unavailable/); assert.doesNotMatch(html, /Held-out backtest MAE/);
  function findButton(element) {
    if (!element || typeof element !== 'object') return null;
    if (element.type === 'button') return element;
    return Children.toArray(element.props?.children).map(findButton).find(Boolean);
  }
  findButton(view).props.onClick(); assert.equal(retried, true);
});

test('median tooltip discloses low coverage, observations and true zero depths', () => {
  const html = renderToStaticMarkup(createElement(StateMedianTooltip, { active: true, payload: [{ payload: {
    month: '2026-09', observed: null, lowCoverage: 0, predicted: null, districts: 1, registered: 4, coverage: 25, observations: 1,
  } }] }));
  assert.match(html, /0.00 m bgl/); assert.match(html, /25.0% coverage/); assert.match(html, /Excluded from training targets/);
});

test('median API requests an explicit experimental mode and preserves structured model unavailability', async t => {
  const urls = [];
  t.mock.method(globalThis, 'fetch', async url => {
    urls.push(url);
    return { ok: false, status: 503, json: async () => ({ ...fixture(), status: 'model_unavailable', forecast: [], message: 'Candidate not generated.' }) };
  });
  assert.equal((await fetchStateMedianPredict('TN', '2026-10-25')).status, 'model_unavailable');
  assert.equal(urls[0], '/api/predict/state/TN?model=median_xgboost&horizon=12&as_of=2026-10-25');
  await assert.rejects(fetchStatePredict('TN', 12, '2026-10-25'), /503/);
  assert.equal(urls[1], '/api/predict/state/TN?horizon=12&as_of=2026-10-25');
});

test('latest median vintage is selected independently of the production registry date', async t => {
  const urls = [];
  t.mock.method(globalThis, 'fetch', async url => { urls.push(url); return { ok: true, json: async () => fixture() }; });
  const value = await loadStateMedianForecast('TN');
  assert.equal(value.as_of, '2026-10-25');
  assert.equal(urls[0], '/api/predict/state/TN?model=median_xgboost&horizon=12');
  const html = renderToStaticMarkup(createElement(StateMedianForecastView, { value }));
  assert.match(html, /Forecast vintage: 2026-10-25/);
});

test('median loader validates requested state and date rather than accepting another result', async () => {
  assert.equal((await loadStateMedianForecast('TN', '2026-10-25', async () => fixture())).state_id, 'TN');
  await assert.rejects(loadStateMedianForecast('HR', '2026-10-25', async () => fixture()), /identity/);
  await assert.rejects(loadStateMedianForecast('TN', '2026-09-25', async () => fixture()), /identity/);
});

test('one controlled primary median chart is mounted on States; district components remain unchanged', () => {
  const states = readFileSync(new URL('../src/pages/States.jsx', import.meta.url), 'utf8');
  assert.equal((states.match(/<StateMedianForecastView /g) || []).length, 1);
  assert.doesNotMatch(states, /<StateForecastGraph|<StateMedianForecast stateId/);
  const district = readFileSync(new URL('../src/pages/DistrictDetail.jsx', import.meta.url), 'utf8');
  assert.doesNotMatch(district, /StateMedianForecast|median_xgboost/);
});
