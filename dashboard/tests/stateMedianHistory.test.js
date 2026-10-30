import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement, Children } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadJsx } from './helpers/loadJsx.js';
import { validateStateMedianHistory, stateMedianChartRows, stateRecordedHistoryRows, state12mPredictionRows, stateHistoryKey, currentStateHistoryRead, medianSummaryRecords } from '../src/components/stateMedianForecastContract.js';
const { loadFullStateMedianHistory, StateMedianForecastView, StateMedianCoverageCard, StateMedianTooltip, stateMedianForecastPlot, StateRecordedHistoryTooltip, stateRecordedHistoryPlot, State12mPredictionTooltip, state12mPredictionPlot } = await loadJsx(new URL('../src/components/StateMedianForecast.jsx', import.meta.url));

// Synthetic fixtures exercise contracts and rendering, never stand in for historical evidence.
function forecast() {
  return { state_id: 'TN', state_name: 'Tamil Nadu', as_of: '2026-10-29', forecast_origin: '2026-10-01',
    generation_id: 'fixture-generation', source_data_sha256: 'fixture-source', feature_generation: 'fixture-features',
    artifact_release: 'synthetic-only', registry_sha256: 'fixture-registry', release_manifest_sha256: 'fixture-manifest', input_cutoff: '2026-09-01',
    model_version: '1.0-state-median-xgboost', model_name: 'state_median_xgboost', status: 'forecast',
    promotion_status: 'experimental', training_cutoff: '2019-12-01', computed_at: '2026-10-29T00:00:00Z',
    historical_reference_date: '2026-01-01', last_observed_gwl_m_bgl: 4, contributing_districts_count: 2,
    total_districts_in_state: 4, district_coverage_pct: 50, history: [historyRow('2026-01-01', 4)],
    forecast: Array.from({ length: 12 }, (_, i) => ({ target_date: new Date(Date.UTC(2026, 10 + i, 1)).toISOString().slice(0, 10), horizon: i + 1, predicted_gwl: 4 + i / 10, is_forecast: true, is_observed: false })),
    evaluation: { status: 'not_evaluated', n: 0, mae_m: null, rmse_m: null }, limitations: [] };
}
function historyRow(date, value, eligible = true) {
  return { date, gwl_m_bgl: value, training_eligible: eligible, contributing_districts_count: value === null ? 0 : eligible ? 2 : 1,
    total_districts_in_state: 4, district_coverage_pct: value === null ? 0 : eligible ? 50 : 25,
    coverage_ratio: value === null ? 0 : eligible ? .5 : .25, observation_count: value === null ? 0 : 2,
    observation_quality: value === null ? 'missing' : eligible ? 'coverage_qualified' : 'low_coverage',
    is_observed: value !== null, is_forecast: false };
}
function fullHistory() {
  const value = forecast();
  return { product: 'state_median_groundwater_history', units: 'm_bgl', state_id: value.state_id, state_name: value.state_name,
    as_of: value.as_of, generation_id: value.generation_id, model_version: value.model_version,
    source_data_sha256: value.source_data_sha256, feature_generation: value.feature_generation,
    artifact_release: value.artifact_release, registry_sha256: value.registry_sha256, release_manifest_sha256: value.release_manifest_sha256, input_cutoff: value.input_cutoff,
    earliest_eligible_date: '2002-01-01', earliest_observation_date: '2002-01-01',
    history: [historyRow('2002-01-01', 2), historyRow('2002-02-01', null, false), historyRow('2002-03-01', 3, false), historyRow('2002-04-01', 4)] };
}

test('full history requires the exact selected state, vintage, release and source; filled values are rejected', () => {
  assert.equal(validateStateMedianHistory(fullHistory(), forecast()).history[0].date, '2002-01-01');
  for (const mutate of [h => { h.state_id = 'HR'; }, h => { h.as_of = '2026-09-29'; }, h => { h.generation_id = 'other'; },
    h => { h.source_data_sha256 = 'other'; }, h => { h.feature_generation = 'other'; }, h => { h.model_version = '2.0-state-median-tiered'; },
    h => { h.history[0].is_observed = false; }, h => { h.history[0].is_imputed = true; }, h => { h.history.reverse(); },
    h => { h.history[0].date = '2027-01-01'; }, h => { h.history[2].training_eligible = true; },
    h => { h.artifact_release = 'other'; }, h => { h.registry_sha256 = 'other'; }, h => { h.release_manifest_sha256 = 'other'; },
    h => { h.input_cutoff = '2026-08-01'; }, h => { h.history.splice(1, 1); }, h => { h.history[0].training_eligible = false; },
    h => { h.earliest_eligible_date = '2002-04-01'; }]) {
    const invalid = fullHistory(); mutate(invalid); assert.throws(() => validateStateMedianHistory(invalid, forecast()), /Invalid state median forecast/);
  }
});

test('full history begins at the supplied source month and keeps missing/ineligible observations disconnected', () => {
  const value = { ...forecast(), history: fullHistory().history };
  const rows = stateMedianChartRows(value);
  assert.equal(rows[0].month, '2002-01');
  assert.equal(rows.find(row => row.month === '2002-02').observed, null);
  assert.equal(rows.find(row => row.month === '2002-03').observed, null);
  assert.equal(rows.find(row => row.month === '2002-03').lowCoverage, 3);
  assert.equal(rows.find(row => row.month === '2002-04').observed, 4);
  const filled = { ...value, history: [ { ...historyRow('2002-01-01', 10), is_observed: false, is_imputed: true } ] };
  assert.equal(stateMedianChartRows(filled)[0].observed, null);
  assert.equal(stateMedianChartRows(filled)[0].lowCoverage, null);
  const plot = stateMedianForecastPlot(value);
  const lines = Children.toArray(plot.props.children).filter(child => ['observed', 'lowCoverage', 'predicted'].includes(child.props.dataKey));
  assert.ok(lines.every(line => line.props.connectNulls === false));
  assert.equal(lines.find(line => line.props.dataKey === 'observed').props.stroke, '#2563eb');
  assert.equal(lines.find(line => line.props.dataKey === 'observed').props.dot.r, 3);
  assert.equal(lines.find(line => line.props.dataKey === 'predicted').props.stroke, '#0f766e');
  assert.equal(lines.find(line => line.props.dataKey === 'predicted').props.strokeDasharray, '6 3');
});

test('history read guards discard a previous state or generation before it can change the chart', () => {
  const value = forecast(), read = { key: stateHistoryKey(value), value: fullHistory(), loading: false };
  assert.equal(currentStateHistoryRead(read, value), read);
  assert.equal(currentStateHistoryRead(read, { ...value, state_id: 'HR' }), null);
  assert.equal(currentStateHistoryRead(read, { ...value, generation_id: 'next-release' }), null);
  assert.equal(currentStateHistoryRead(read, { ...value, as_of: '2026-09-29' }), null);
});

test('leading absent months do not imply early observations, while grey-only and no-observation history remain explicit', () => {
  const history = { ...fullHistory(), earliest_observation_date: '2002-02-01', earliest_eligible_date: null,
    history: [historyRow('2002-01-01', null, false), historyRow('2002-02-01', 3, false)] };
  validateStateMedianHistory(history, forecast());
  assert.equal(stateMedianChartRows({ ...forecast(), history: history.history })[0].month, '2002-02');
  const greyOnly = renderToStaticMarkup(createElement(StateMedianForecastView, { value: forecast(), fullHistory: history }));
  assert.match(greyOnly, /First genuine state median: Feb 2002/);
  assert.match(greyOnly, /No historical month meets the XGBoost training-target coverage criteria/);
  const empty = { ...history, earliest_observation_date: null, history: [historyRow('2002-01-01', null, false)] };
  const unavailable = { ...forecast(), status: 'insufficient_data', forecast: [], message: 'Requires more training history.' };
  const noData = renderToStaticMarkup(createElement(StateMedianForecastView, { value: unavailable, fullHistory: empty }));
  assert.match(noData, /No usable groundwater observations/);
  assert.match(noData, /matching release source contains no genuine groundwater observations/);
  assert.doesNotMatch(noData, /Requires more training history/);
});

test('history loader requests only the selected published release and propagates errors without inventing history', async t => {
  const urls = [];
  t.mock.method(globalThis, 'fetch', async url => { urls.push(url); return { ok: true, json: async () => fullHistory() }; });
  const result = await loadFullStateMedianHistory(forecast());
  assert.equal(result.history.length, 4);
  assert.equal(urls[0], '/api/v2/history/state/TN?as_of=2026-10-29&generation_id=fixture-generation');
  await assert.rejects(loadFullStateMedianHistory(forecast(), async () => { throw new Error('Source snapshot unavailable'); }), /Source snapshot unavailable/);
  const html = renderToStaticMarkup(createElement(StateMedianForecastView, { value: forecast(), historyError: 'Source snapshot unavailable' }));
  assert.match(html, /Showing only the history window bundled with this forecast/);
  assert.match(html, /Retry full history/); assert.doesNotMatch(html, /Full source history/);
  const complete = renderToStaticMarkup(createElement(StateMedianForecastView, { value: forecast(), fullHistory: fullHistory() }));
  assert.match(complete, /Full source history · Jan 2002/);
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, status: 503, json: async () => ({ product: 'state_median_groundwater_history', status: 'model_unavailable', message: 'Matching source snapshot is unavailable.' }) }));
  await assert.rejects(loadFullStateMedianHistory(forecast()), /Matching source snapshot is unavailable/);
});

test('coverage card counts actual complete records from both methods and keeps unavailable separate', () => {
  const summary = { total_states: 3, model_version: '2.0-state-median-tiered', states: [
    { status: 'available', forecast_month_count: 12, forecast_method: 'state_median_xgboost' },
    { status: 'available', forecast_month_count: 12, forecast_method: 'persistence_fallback' },
    { status: 'insufficient_data', forecast_month_count: 0, forecast_method: 'no_observations' },
  ] };
  assert.deepEqual(medianSummaryRecords(summary), { available: 2, unavailable: 1, forecastMonths: 24, xgboost: 1, persistence: 1, noObservations: 1 });
  const html = renderToStaticMarkup(createElement(StateMedianCoverageCard, { summary }));
  assert.match(html, /Forecastable States/);
  assert.match(html, /2 <small>\/ 3/);
  assert.match(html, /1 XGBoost · 1 Persistence · 1 unavailable/);
  const unknown = renderToStaticMarkup(createElement(StateMedianCoverageCard, { summary: { total_states: 36, states: [{ status: 'available' }] } }));
  assert.match(unknown, /Unverified/);
});

test('state tooltip exposes actual historical coverage and labels forecast reference coverage as historical', () => {
  const rows = stateMedianChartRows(forecast());
  const observed = rows.find(row => row.observed !== null), predicted = rows.find(row => row.predicted !== null);
  const html = renderToStaticMarkup(createElement(StateMedianTooltip, { active: true, payload: [{ payload: observed }] }));
  assert.match(html, /Tamil Nadu/); assert.match(html, /Observed historical state median/); assert.match(html, /2 \/ 4 reporting districts · 50.0% coverage/);
  const forecastHtml = renderToStaticMarkup(createElement(StateMedianTooltip, { active: true, payload: [{ payload: predicted }] }));
  assert.match(forecastHtml, /State median XGBoost/); assert.match(forecastHtml, /Genuine reference observation: 2026-01-01/);
  assert.match(forecastHtml, /Forecast-period coverage is not observed/);
});

test('two independent charts: recorded history and 12-month prediction plots are completely isolated', () => {
  const f = forecast(), h = fullHistory();
  // Add consecutive observations to exercise observation guides as well as gap guides
  h.history.push(historyRow('2002-05-01', 5));
  const histRows = stateRecordedHistoryRows(h.history, f.state_name);
  assert.equal(histRows[0].month, '2002-01');
  assert.equal(histRows.at(-1).month, '2002-05');
  assert.ok(histRows.every(r => !('predicted' in r)));

  const histPlot = stateRecordedHistoryPlot(histRows);
  const histChildren = Children.toArray(histPlot.props.children);
  const histLines = histChildren.filter(c => c.props && (c.props.dataKey || c.props.className));
  assert.ok(histLines.some(l => l.props.dataKey === 'observed'));
  assert.ok(histLines.some(l => l.props.dataKey === 'filled'));
  assert.ok(histLines.some(l => l.props.dataKey === 'lowCoverage'));
  assert.ok(histLines.some(l => l.props.className === 'history-observation-guide'));
  assert.ok(histLines.some(l => l.props.className === 'history-gap-guide'));
  assert.ok(histLines.every(l => l.props.dataKey !== 'predicted'));

  const predRows = state12mPredictionRows(f);
  assert.equal(predRows.length, 12);
  assert.equal(predRows[0].month, '2026-11');
  assert.equal(predRows.at(-1).month, '2027-10');
  assert.ok(predRows.every(r => !('observed' in r) && !('lowCoverage' in r) && !('filled' in r)));

  const predPlot = state12mPredictionPlot(predRows, f);
  const predChildren = Children.toArray(predPlot.props.children);
  const predLines = predChildren.filter(c => c.props?.name && c.props?.dataKey);
  assert.equal(predLines.length, 1);
  assert.equal(predLines[0].props.dataKey, 'predicted');
  assert.equal(predLines[0].props.stroke, '#0f766e');
  assert.equal(predLines[0].props.strokeDasharray, '6 3');
});

test('StateMedianForecastView renders two separate cards with exact headers and disclosures', () => {
  const f = forecast(), h = fullHistory();
  const html = renderToStaticMarkup(createElement(StateMedianForecastView, { value: f, fullHistory: h }));

  assert.match(html, /<section class="card history-card state-history-card"/);
  assert.match(html, /<h2>Recorded History<\/h2>/);
  assert.match(html, /Depth is measured in metres below ground \(m bgl\)/);
  assert.match(html, /Full source history/);
  assert.match(html, /First genuine state median: Jan 2002/);

  assert.match(html, /<section class="card forecast-card state-forecast-card"/);
  assert.match(html, /<h2>12-Month Groundwater Prediction<\/h2>/);
  assert.match(html, /Forecast origin: 2026-10/);
  assert.match(html, /Forecast period: Nov 2026/);
  assert.match(html, /Vintage: 2026-10-29/);
});

test('tooltips for both graphs show their dedicated attributes accurately', () => {
  const histTip = renderToStaticMarkup(createElement(StateRecordedHistoryTooltip, {
    active: true,
    payload: [{
      payload: {
        month: '2002-01',
        observed: 4.25,
        filled: null,
        lowCoverage: null,
        districts: 3,
        registered: 4,
        coverage: 75.0,
        observations: 3,
        stateName: 'Tamil Nadu',
      },
    }],
  }));
  assert.match(histTip, /January 2002/);
  assert.match(histTip, /Tamil Nadu/);
  assert.match(histTip, /Observed state median/);
  assert.match(histTip, /4.25 m below ground/);
  assert.match(histTip, /3 \/ 4 reporting districts · 75.0% coverage/);

  const predTip = renderToStaticMarkup(createElement(State12mPredictionTooltip, {
    active: true,
    payload: [{
      payload: {
        month: '2026-11',
        horizon: 1,
        predicted: 5.12,
        isFallback: true,
        referenceDate: '2020-01-01',
        referenceAge: 81,
        stateName: 'Tamil Nadu',
      },
    }],
  }));
  assert.match(predTip, /November 2026 \(M\+1\)/);
  assert.match(predTip, /Persistence Fallback: 5.12 m below ground/);
  assert.match(predTip, /Reference observation: 2020-01-01 \(81 months old\)/);
  assert.match(predTip, /Latest genuine observed state median held constant/);
});
