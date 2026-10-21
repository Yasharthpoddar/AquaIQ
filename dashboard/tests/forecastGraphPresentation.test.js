import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { pathToFileURL } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { transformWithOxc } from 'vite';
import { followingCalendarMonths } from '../src/components/forecastGraph.js';
import { annualBaselineReference, loadRequestedForecastGraph, requestedOriginMonth } from '../src/components/forecastGraphPresentation.js';

const componentUrl = new URL('../src/components/ForecastGraphPanel.jsx', import.meta.url);
const require = createRequire(import.meta.url);
const transformed = await transformWithOxc(readFileSync(componentUrl, 'utf8'), componentUrl.pathname, { jsx: { runtime: 'automatic' } });
const compiled = transformed.code.replace(/from (["'])([^"']+)\1/g, (_match, _quote, specifier) => {
  const resolved = specifier.startsWith('.')
    ? new URL(`${specifier}.js`, componentUrl).href
    : pathToFileURL(require.resolve(specifier)).href;
  return `from ${JSON.stringify(resolved)}`;
});
const { default: ForecastGraphPanel, ForecastGraphView, forecastPlot } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

function fixture(origin = '2026-05', ml = null, baseline = 6.553) {
  const months = followingCalendarMonths(origin);
  return {
    product: 'direct_12month_research_graph', horizon_months: 12, units: 'm_bgl',
    status: ml == null ? 'unavailable' : 'available',
    output_kind: ml == null ? 'current_vintage_research' : 'historical_research',
    forecast_issued_at: null, origin_month: origin, target_month: months?.[11] ?? null,
    ml_estimate_m: ml, annual_baseline_m: baseline,
    source: { name: 'SYNTHETIC TEST FIXTURE ONLY', origin_is_observed: true, origin_is_imputed: false },
    forecast: Array.from({ length: 12 }, (_, index) => ({
      month: months?.[index] ?? null, horizon_months: index + 1,
      predicted_gwl: index === 11 ? ml : null,
      annual_baseline_m: index === 11 ? baseline : null,
    })), unavailable_reasons: ml == null ? ['Required current inputs are missing.'] : [],
    limitations: ['Synthetic fixture; not evidence of forecasting skill.'],
  };
}

test('explicit historical month is sent unchanged and latest origin remains the default', async () => {
  const calls = [];
  const read = async (district, month) => { calls.push([district, month]); return fixture(month || '2026-05'); };
  const latest = await loadRequestedForecastGraph('TS-Adilabad', null, read);
  const historical = await loadRequestedForecastGraph('TS-Adilabad', '2024-01', read);
  assert.deepEqual(calls, [['TS-Adilabad', null], ['TS-Adilabad', '2024-01']]);
  assert.equal(latest.origin_month, '2026-05');
  assert.equal(historical.origin_month, '2024-01');
  assert.equal(requestedOriginMonth('?origin_month=2024-01'), '2024-01');
  assert.equal(requestedOriginMonth(''), null);
});

test('mismatched responses cannot silently replace a user-selected historical origin', async () => {
  await assert.rejects(loadRequestedForecastGraph('TS-Adilabad', '2024-01', async () => fixture()), /No fallback origin has been displayed/);
  let reads = 0;
  await assert.rejects(loadRequestedForecastGraph('TS-Adilabad', '2024-13', async () => { reads += 1; return fixture(); }), /YYYY-MM/);
  assert.equal(reads, 0);
});

test('annual baseline is a single observed-origin reference, including a legitimate zero', () => {
  assert.deepEqual(annualBaselineReference(fixture()), { month: '2027-05', depth: 6.553 });
  assert.deepEqual(annualBaselineReference(fixture('2026-05', null, 0)), { month: '2027-05', depth: 0 });
  assert.equal(annualBaselineReference(fixture('2026-05', null, null)), null);
  assert.equal(annualBaselineReference(fixture(null, null, null)), null);
  const imputed = fixture(); imputed.source.origin_is_imputed = true;
  assert.equal(annualBaselineReference(imputed), null);
});

test('unknown origins and read failures retain an explicit graph-sized unavailable frame', () => {
  const unknown = renderToStaticMarkup(createElement(ForecastGraphView, { projection: fixture(null, null, null) }));
  assert.match(unknown, /id="forecast-graph"/);
  assert.match(unknown, /height:380px/);
  assert.match(unknown, /no source-backed origin month is available/);
  assert.match(unknown, /No calendar months or values have been invented/);
  const failed = renderToStaticMarkup(createElement(ForecastGraphView, { error: 'Read failed: 503' }));
  assert.match(failed, /Read failed: 503/);
  assert.match(failed, /Retry prediction/);
  assert.match(failed, /height:380px/);
});

test('panel renders origin controls and loading frame before legacy scoring is available', () => {
  const html = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: ['/district/TS-Adilabad?origin_month=2024-01#forecast-graph'] },
    createElement(ForecastGraphPanel, { districtId: 'TS-Adilabad' })));
  assert.match(html, /type="month"[^>]*value="2024-01"/);
  assert.match(html, />Apply<\/button>/);
  assert.match(html, /Latest observed origin/);
  assert.match(html, /Defaults to the latest observed origin/);
  assert.match(html, /id="forecast-graph"/);
  const detail = readFileSync(new URL('../src/pages/DistrictDetail.jsx', import.meta.url), 'utf8');
  assert.equal((detail.match(/<ForecastGraphPanel key=\{id\} districtId=\{id\} \/>/g) || []).length, 3);
  assert.match(detail, /if \(error\).*Retry district<\/button>.*<ForecastGraphPanel/);
});

test('Home exposes one explicitly historical graph link without replacing the map or risk cards', () => {
  const home = readFileSync(new URL('../src/pages/Home.jsx', import.meta.url), 'utf8');
  assert.match(home, /to="\/district\/TS-Adilabad\?origin_month=2024-01#forecast-graph"/);
  assert.match(home, /historical graph example \(January 2024 origin\)/);
  assert.match(home, /<MapComponent/);
  assert.match(home, /className="summary-cards"/);
  assert.doesNotMatch(home, /<ForecastGraphPanel|<ResearchForecast/);
});

test('baseline-only view clearly distinguishes its marker from unavailable ML', () => {
  const html = renderToStaticMarkup(createElement(ForecastGraphView, { projection: fixture() }));
  assert.match(html, /Blue marker: annual baseline at M\+12/);
  assert.match(html, /Twelve-month ML is unavailable/);
  assert.match(html, /6\.55 m below ground/);
  assert.match(html, /not an ML estimate or a monthly curve/);
});

test('actual chart element preserves twelve slots with one separate baseline reference and no fabricated ML', () => {
  const baselineOnly = forecastPlot(fixture(), { width: 720, height: 380 });
  assert.equal(baselineOnly.props.data.length, 12);
  assert.ok(baselineOnly.props.data.every(row => row.predicted === null));
  const children = baselineOnly.props.children.flat().filter(Boolean);
  const baseline = children.find(child => child.props.ifOverflow === 'extendDomain');
  assert.equal(baseline.props.x, '2027-05');
  assert.equal(baseline.props.y, 6.553);
  assert.equal(baseline.props.fill, '#2563eb');
  const historical = forecastPlot(fixture('2024-01', 4.2), { width: 720, height: 380 });
  assert.equal(historical.props.data.filter(row => row.predicted !== null).length, 1);
  assert.equal(historical.props.data[11].predicted, 4.2);
  const html = renderToStaticMarkup(historical);
  assert.match(html, /recharts-wrapper/);
});
