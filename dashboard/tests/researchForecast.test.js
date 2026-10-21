import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { pathToFileURL } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { transformWithOxc } from 'vite';
import { fetchResearchCatalog, fetchResearchForecast, fetchPredict } from '../src/api.js';
import { formatResearchDepth, twelveMonthTarget, validateResearchCatalog, validateResearchForecast } from '../src/components/researchForecastContract.js';

// Compile the existing JSX in memory. No browser, server, database, or build output.
const componentUrl = new URL('../src/components/ResearchForecast.jsx', import.meta.url);
const require = createRequire(import.meta.url);
const transformed = await transformWithOxc(readFileSync(componentUrl, 'utf8'), componentUrl.pathname, { jsx: { runtime: 'automatic' } });
const compiled = transformed.code.replace(/from (["'])([^"']+)\1/g, (_match, _quote, specifier) => {
  const resolved = specifier.startsWith('.')
    ? new URL(`${specifier}.js`, componentUrl).href
    : pathToFileURL(require.resolve(specifier)).href;
  return `from ${JSON.stringify(resolved)}`;
});
const { default: ResearchForecast, ResearchForecastEvidence } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

function response(overrides = {}) {
  return {
    product: 'direct_12month_research', horizon_months: 12, units: 'm_bgl',
    status: 'unavailable', output_kind: 'current_vintage_research',
    origin_month: '2026-05', target_month: '2027-05', forecast_issued_at: null,
    ml_estimate_m: null, annual_baseline_m: 6.553,
    source: { name: 'Synthetic fixture only', origin_is_observed: true, origin_is_imputed: false,
      latest_observed_month: '2026-05', input_flags: [{ feature: 'temperature', status: 'missing' }] },
    scope: { description: 'Adilabad metadata-agreement research cohort', supported_district_ids: ['TS-Adilabad'] },
    unavailable_reasons: ['Current weather inputs are missing; this artifact is historical-only.'],
    limitations: ['Availability and datum continuity are unverified.'], ...overrides,
  };
}

test('exact M+12 target preserves calendar month across year boundaries and leap years', () => {
  assert.equal(twelveMonthTarget('2023-12'), '2024-12');
  assert.equal(twelveMonthTarget('2024-02'), '2025-02');
  for (const value of ['2024-13', '2024-00', '2024-2', '2024-02-01', '', null]) assert.equal(twelveMonthTarget(value), null);
});

test('research responses reject a legacy horizon, units, product, or shifted target', () => {
  for (const changed of [{ horizon_months: 6 }, { units: 'metres' }, { product: 'legacy' },
    { target_month: '2026-11' }, { origin_month: '2026-13', target_month: null }]) {
    assert.throws(() => validateResearchForecast(response(changed)), /incompatible/);
  }
});

test('a baseline may be available while ML abstains, without inventing a zero prediction', () => {
  const result = response();
  assert.equal(validateResearchForecast(result), result);
  assert.equal(formatResearchDepth(result.ml_estimate_m), 'Unavailable');
  assert.equal(formatResearchDepth(0), '0.000 m below ground level');
  const html = renderToStaticMarkup(createElement(ResearchForecastEvidence, { result }));
  assert.match(html, /Unavailable/);
  assert.match(html, /6\.553 m below ground level/);
  assert.match(html, /Current weather inputs are missing/);
  assert.match(html, /persistence = annual seasonal naive/);
  assert.equal((html.match(/<tr>/g) || []).length, 5); // two headers, two methods, one provenance row
  assert.doesNotMatch(html, /0\.000 m below ground level/);
});

test('no observed-baseline or ML number is accepted from an imputed or missing origin', () => {
  for (const flags of [{ origin_is_observed: false, origin_is_imputed: false },
    { origin_is_observed: true, origin_is_imputed: true }, {}]) {
    assert.throws(() => validateResearchForecast(response({ source: flags })), /incompatible/);
  }
  for (const value of [undefined, NaN, Infinity, '6.553']) {
    assert.throws(() => validateResearchForecast(response({ ml_estimate_m: value })), /incompatible/);
  }
});

test('unsupported districts can remain unavailable without borrowing another origin or district', () => {
  const result = response({ origin_month: null, target_month: null, annual_baseline_m: null,
    source: {}, unavailable_reasons: ['District outside supported research scope.'] });
  assert.equal(validateResearchForecast(result), result);
  const html = renderToStaticMarkup(createElement(ResearchForecastEvidence, { result }));
  assert.match(html, /District outside supported research scope/);
  assert.match(html, /TS-Adilabad/);
  assert.doesNotMatch(html, /6\.553/);
});

test('historical target measurements stay separate from estimates and prospective claims are rejected', () => {
  const historical = response({ output_kind: 'historical_research', origin_month: '2024-01',
    target_month: '2025-01', status: 'available', ml_estimate_m: 5.1, observed_target_m: 5.2 });
  assert.equal(validateResearchForecast(historical), historical);
  const html = renderToStaticMarkup(createElement(ResearchForecastEvidence, { result: historical }));
  assert.match(html, /Historical research estimate/);
  assert.match(html, /Source-backed historical target measurement/);
  assert.match(html, /no prospective forecast has been issued/);
  assert.throws(() => validateResearchForecast(response({ output_kind: 'prospective_forecast' })), /incompatible/);
  assert.throws(() => validateResearchForecast(response({ forecast_issued_at: '2026-10-20T00:00:00Z' })), /incompatible/);
  assert.throws(() => validateResearchForecast(response({ observed_target_m: 5.2 })), /incompatible/);
});

test('source text renders as text rather than executable HTML', () => {
  const html = renderToStaticMarkup(createElement(ResearchForecastEvidence, {
    result: response({ unavailable_reasons: ['<script>doNotExecute()</script>'] }),
  }));
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});

test('carried inputs retain their source month and age instead of appearing as fresh measurements', () => {
  const result = response();
  result.source.input_flags = [{ feature: 'temperature', status: 'carried_forward', source_month: '2024-12', age_months: 2 }];
  const html = renderToStaticMarkup(createElement(ResearchForecastEvidence, { result }));
  assert.match(html, /carried forward/);
  assert.match(html, /2024-12/);
  assert.match(html, /<td>2<\/td>/);
  assert.match(html, /do not certify acquisition or model-availability times/);
});

test('primary panel labels the distinct direct horizon and discloses uncertain historical comparison', () => {
  const html = renderToStaticMarkup(createElement(ResearchForecast, { districtId: 'TS-Adilabad' }));
  assert.match(html, /12 calendar months ahead/);
  assert.match(html, /direct M\+12 target/);
  assert.match(html, /separate from the six-month monthly climate projection/);
  assert.match(html, /does not validate|do not validate/);
  assert.match(html, /HGB remains blocked/);
  const home = readFileSync(new URL('../src/pages/Home.jsx', import.meta.url), 'utf8');
  assert.ok(home.indexOf('<ResearchForecast />') < home.indexOf('Secondary: legacy'));
  const detail = readFileSync(new URL('../src/pages/DistrictDetail.jsx', import.meta.url), 'utf8');
  assert.equal((detail.match(/<ResearchForecast key=\{id\} districtId=\{id\} \/>/g) || []).length, 3);
  assert.match(detail, /window:'next_six_months'/);
  assert.match(detail, /Secondary: six-month climate-conditioned projections/);
  const app = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
  assert.match(app, /<Route path="\/research" element=\{<div className="page"><h1>Twelve-month groundwater research<\/h1><ResearchForecast \/>/);
});

test('catalog rejects incompatible horizons and invalid origin months', () => {
  const valid = { product: 'direct_12month_research', horizon_months: 12, units: 'm_bgl',
    districts: [{ district_id: 'TS-Adilabad', origin_months: ['2024-01', '2026-05'] }] };
  assert.equal(validateResearchCatalog(valid), valid);
  assert.throws(() => validateResearchCatalog({ ...valid, horizon_months: 6 }), /incompatible/);
  assert.throws(() => validateResearchCatalog({ ...valid,
    districts: [{ district_id: 'TS-Adilabad', origin_months: ['2026-13'] }] }), /incompatible/);
});

test('independent research routes preserve the legacy six-month route and default latest origin', async () => {
  const originalFetch = globalThis.fetch;
  const urls = [];
  globalThis.fetch = async url => { urls.push(url); return { ok: true, json: async () => ({ synthetic: true }) }; };
  try {
    await fetchResearchCatalog();
    await fetchResearchForecast('TS-Adilabad');
    await fetchResearchForecast('TS-Adilabad', '2024-01');
    await fetchPredict('TS-Adilabad', { window: 'next_six_months' });
    assert.deepEqual(urls, ['/api/research/forecast', '/api/research/forecast/TS-Adilabad',
      '/api/research/forecast/TS-Adilabad?origin_month=2024-01', '/api/predict/TS-Adilabad?window=next_six_months']);
  } finally { globalThis.fetch = originalFetch; }
});

test('missing research assets disclose the public-safe reason and remain retryable', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 503, json: async () => ({
    product: 'direct_12month_research', unavailable_reasons: ['A required research artifact is missing or unreadable.'],
  }) });
  try {
    await assert.rejects(fetchResearchForecast('TS-Adilabad'), /artifact is missing or unreadable/);
    globalThis.fetch = async () => ({ ok: true, json: async () => ({ retrySucceeded: true }) });
    assert.deepEqual(await fetchResearchForecast('TS-Adilabad'), { retrySucceeded: true });
  } finally { globalThis.fetch = originalFetch; }
});
