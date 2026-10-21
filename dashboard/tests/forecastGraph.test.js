import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { fetchPredict, fetchResearchGraph } from '../src/api.js';
import { followingCalendarMonths, forecastChartRows, validateForecastGraph } from '../src/components/forecastGraph.js';

// Synthetic contract fixtures only; these are never saved as real forecast records.
function graphFixture(origin = '2026-05', ml = null, baseline = 6.553) {
  const months = followingCalendarMonths(origin);
  return {
    product: 'direct_12month_research_graph', horizon_months: 12, units: 'm_bgl',
    status: ml == null ? 'unavailable' : 'available',
    output_kind: 'current_vintage_research', forecast_issued_at: null,
    origin_month: origin, target_month: months?.[11] ?? null,
    ml_estimate_m: ml, annual_baseline_m: baseline,
    source: { origin_is_observed: true, origin_is_imputed: false },
    forecast: Array.from({ length: 12 }, (_, index) => ({
      month: months?.[index] ?? null, horizon_months: index + 1,
      predicted_gwl: index === 11 ? ml : null,
      annual_baseline_m: index === 11 ? baseline : null,
    })),
    unavailable_reasons: ml == null ? ['Twelve-month ML inputs are unavailable.'] : [],
    limitations: ['Only the M+12 artifact is supported; intermediate horizons remain missing.'],
  };
}

test('twelve calendar slots cross December to January and retain exact M+12 target', () => {
  assert.deepEqual(followingCalendarMonths('2024-12'), [
    '2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06',
    '2025-07', '2025-08', '2025-09', '2025-10', '2025-11', '2025-12',
  ]);
  assert.equal(followingCalendarMonths('2024-02')[11], '2025-02');
  for (const origin of ['2024-13', '2024-00', '2024-2', '2024-02-01', null]) assert.equal(followingCalendarMonths(origin), null);
});

test('graph data contains exactly twelve ordered target slots with only the compatible M+12 ML value', () => {
  const fixture = graphFixture('2024-12', 4.25);
  assert.equal(validateForecastGraph(fixture), fixture);
  const chart = forecastChartRows(fixture);
  assert.equal(chart.length, 12);
  assert.deepEqual(chart.map(row => row.month), followingCalendarMonths('2024-12'));
  assert.ok(chart.slice(0, 11).every(row => row.predicted === null));
  assert.equal(chart[11].predicted, 4.25);
  assert.ok(chart.every(row => !Object.hasOwn(row, 'annual_baseline_m')));
});

test('missing ML preserves the twelve-month domain without zero-filling or plotting baseline as ML', () => {
  const fixture = graphFixture();
  assert.equal(validateForecastGraph(fixture), fixture);
  const chart = forecastChartRows(fixture);
  assert.equal(chart.length, 12);
  assert.ok(chart.every(row => row.predicted === null));
  assert.equal(fixture.forecast[11].annual_baseline_m, 6.553);
  assert.ok(fixture.forecast.slice(0, 11).every(row => row.annual_baseline_m === null));
});

test('SYNTHETIC render-data fixture retains twelve existing numeric points without approving unsupported artifacts', () => {
  // Render-data mapping only: these invented values are not real forecasts or evaluation evidence.
  const fixture = graphFixture('2024-12');
  fixture.forecast.forEach((row, index) => { row.predicted_gwl = 3 + index / 10; });
  const chart = forecastChartRows(fixture);
  assert.equal(chart.length, 12);
  assert.deepEqual(chart.map(row => row.month), followingCalendarMonths('2024-12'));
  assert.deepEqual(chart.map(row => row.predicted), fixture.forecast.map(row => row.predicted_gwl));
  // The current M+12-only artifact contract must still reject all intermediate numeric estimates.
  assert.throws(() => validateForecastGraph(fixture), /compatible twelve-month/);
});

test('six-month contracts and truncated or reordered monthly arrays cannot satisfy the graph', () => {
  for (const mutate of [value => { value.horizon_months = 6; },
    value => { value.product = 'climate_conditioned_xgboost_monthly'; },
    value => { value.units = 'mm'; },
    value => { value.forecast.pop(); },
    value => { [value.forecast[0], value.forecast[1]] = [value.forecast[1], value.forecast[0]]; },
    value => { value.target_month = '2026-11'; },
    value => { value.forecast[2].month = '2026-09'; }]) {
    const fixture = graphFixture(); mutate(fixture);
    assert.throws(() => validateForecastGraph(fixture), /compatible twelve-month/);
  }
});

test('direct M+12 artifact cannot be stretched into intermediate ML points or baseline curves', () => {
  for (const field of ['predicted_gwl', 'annual_baseline_m']) {
    const fixture = graphFixture();
    fixture.forecast[0][field] = 5;
    assert.throws(() => validateForecastGraph(fixture), /compatible twelve-month/);
  }
  const mismatch = graphFixture('2024-01', 5);
  mismatch.forecast[11].predicted_gwl = 6;
  assert.throws(() => validateForecastGraph(mismatch), /compatible twelve-month/);
});

test('imputed origins and nonfinite numeric values remain ineligible', () => {
  for (const mutate of [value => { value.source.origin_is_observed = false; },
    value => { value.source.origin_is_imputed = true; },
    value => { value.forecast[11].predicted_gwl = NaN; value.ml_estimate_m = NaN; },
    value => { value.forecast[11].predicted_gwl = '6'; value.ml_estimate_m = '6'; }]) {
    const fixture = graphFixture(); mutate(fixture);
    assert.throws(() => validateForecastGraph(fixture), /compatible twelve-month/);
  }
});

test('unavailable ML cannot carry a plotted number and available ML cannot be null', () => {
  const unavailable = graphFixture('2024-12', 5);
  unavailable.status = 'unavailable';
  assert.throws(() => validateForecastGraph(unavailable), /compatible twelve-month/);
  const missing = graphFixture();
  missing.status = 'available';
  assert.throws(() => validateForecastGraph(missing), /compatible twelve-month/);
});

test('graph artifact failures preserve the public-safe reason without changing legacy requests', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 503, json: async () => ({
    product: 'direct_12month_research_graph', unavailable_reasons: ['Research artifact checksum mismatch; estimates are blocked.'],
  }) });
  try {
    await assert.rejects(fetchResearchGraph('TS-Adilabad'), /checksum mismatch/);
  } finally { globalThis.fetch = originalFetch; }
});

test('unknown origin stays unavailable without inventing twelve calendar months', () => {
  const fixture = graphFixture(null, null, null);
  assert.equal(validateForecastGraph(fixture), fixture);
  assert.equal(forecastChartRows(fixture).length, 0);
  assert.ok(fixture.forecast.every(row => row.month === null && row.predicted_gwl === null));
});

test('graph explicitly requests twelve months and the separately requested legacy endpoint is unchanged', async () => {
  const originalFetch = globalThis.fetch;
  const urls = [];
  globalThis.fetch = async url => { urls.push(url); return { ok: true, json: async () => ({ synthetic: true }) }; };
  try {
    await fetchResearchGraph('TS-Adilabad');
    await fetchResearchGraph('TS-Adilabad', '2024-01');
    await fetchPredict('TS-Adilabad', { window: 'next_six_months' });
    assert.deepEqual(urls, ['/api/research/graph/TS-Adilabad?months=12',
      '/api/research/graph/TS-Adilabad?months=12&origin_month=2024-01',
      '/api/predict/TS-Adilabad?window=next_six_months']);
  } finally { globalThis.fetch = originalFetch; }
});

test('original graph card, responsive styles, axes, line color and retry control remain in place', () => {
  const detail = readFileSync(new URL('../src/pages/DistrictDetail.jsx', import.meta.url), 'utf8');
  const panel = readFileSync(new URL('../src/components/ForecastGraphPanel.jsx', import.meta.url), 'utf8');
  for (const markup of [
    'padding:\'1.25rem\',margin:\'1.5rem 0\'',
    '<h2>Monthly research projections</h2>',
    '<ResponsiveContainer width="100%" height={380}>',
    'data={projectionChart} margin={{top:15,right:25,bottom:15,left:15}}>',
    '<CartesianGrid strokeDasharray="3 3" />',
    '<XAxis dataKey="month" tickFormatter={formatMonth} minTickGap={20} />',
    '<YAxis label={{value:\'Depth (m below ground)\',angle:-90,position:\'insideLeft\'}} />',
    'stroke="#ef4444" strokeWidth={2} dot={{r:5}} isAnimationActive={false}',
    'onClick={onRetry}>Retry prediction</button>',
  ]) assert.ok(panel.includes(markup), `Preserve original markup: ${markup}`);
  assert.ok(detail.indexOf('<div className={`score-badge') < detail.lastIndexOf('<ForecastGraphPanel key={id} districtId={id} />'));
  assert.ok(detail.lastIndexOf('<ForecastGraphPanel key={id} districtId={id} />') < detail.indexOf('<h2>Recorded groundwater history</h2>'));
  assert.match(panel, /Annual baseline at/);
  assert.match(panel, /Months 1–11 remain gaps/);
  assert.doesNotMatch(panel, /name="Annual baseline"|<ResearchForecast|connectNulls=\{true\}/);
});
