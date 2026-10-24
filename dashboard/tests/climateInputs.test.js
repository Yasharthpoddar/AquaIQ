import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { CLIMATE_FIELDS, loadClimateInputs, validateClimateInputs } from '../src/components/climateInputs.js';

const districtId = 'HR-Kaithal';
const asOf = '2026-10-24';
const months = ['2026-11', '2026-12', '2027-01', '2027-02', '2027-03', '2027-04'];
const context = { districtId, asOf };

function fixture() {
  return {
    district_id: districtId, as_of: asOf, horizon_months: 6, status: 'projection', estimate_type: 'district_level',
    source_zone: null, projection_method: 'climate_conditioned_xgboost_monthly',
    forecast: months.map((month, index) => ({ month, date: `${month}-01`,
      weather: { rainfall_mm: index === 0 ? 0 : 10 + index,
        temperature_c: index === 0 ? -2.5 : 20 + index, evapotranspiration_mm: 80 + index } })),
    weather_basis: {
      source: 'historical_weather_climatology', method: 'historical_monthly_climatology', as_of: asOf,
      units: { rainfall: 'mm/month', temperature: 'degC', evapotranspiration: 'mm/month' },
      future_weather_is_observed: false, weather_history_may_include_filled_values: true,
      latest_historical_weather_dates: { rainfall: '2026-09-01', temperature: '2025-02-01', evapotranspiration: '2024-12-01' },
      origin_weather: { method: 'historical_monthly_climatology', rainfall_mm: 5,
        temperature_c: 22, evapotranspiration_mm: 90 },
    },
  };
}

let originalFetch;
beforeEach(() => { originalFetch = globalThis.fetch; });
afterEach(() => { globalThis.fetch = originalFetch; });

test('weather table fields distinguish monthly water fluxes from temperature and evaporation alone', () => {
  assert.deepEqual(CLIMATE_FIELDS, [
    { key: 'rainfall', label: 'Rainfall', unit: 'mm/month' },
    { key: 'temperature', label: 'Temperature', unit: '°C' },
    { key: 'evapotranspiration', label: 'Evapotranspiration', unit: 'mm/month' },
  ]);
});

test('the loader reuses the canonical six-month predict API with the exact captured scenario date', async () => {
  const urls = [];
  globalThis.fetch = async url => { urls.push(url); return { ok: true, json: async () => fixture() }; };
  const result = await loadClimateInputs(districtId, asOf);
  assert.deepEqual(urls, ['/api/predict/HR-Kaithal?months=6&as_of=2026-10-24&window=next_six_months']);
  assert.equal(result.status, 'available');
  assert.equal(result.asOf, asOf);
  assert.deepEqual(result.rows.map(row => row.month), months);
  assert.equal(result.rows.length, 6, 'No weather values are fabricated for months 7–12');
});

test('the loader preserves API failure for the parent retry state and retries with a fresh request', async () => {
  let reads = 0;
  globalThis.fetch = async () => { reads += 1; return { ok: false, status: 503 }; };
  await assert.rejects(loadClimateInputs(districtId, asOf), /Predict fetch failed: 503/);
  globalThis.fetch = async () => { reads += 1; return { ok: true, json: async () => fixture() }; };
  assert.equal((await loadClimateInputs(districtId, asOf)).status, 'available');
  assert.equal(reads, 2);
});

test('request identity and dates are validated before starting a network request', async () => {
  let reads = 0;
  globalThis.fetch = async () => { reads += 1; throw new Error('Unexpected network read'); };
  for (const [id, date] of [['', asOf], [null, asOf], [districtId, '2026-02-30'],
    [districtId, '2026-13-01'], [districtId, '2026-1-01'], [districtId, undefined]]) {
    await assert.rejects(loadClimateInputs(id, date), /Compatible six-month weather assumptions/);
  }
  assert.equal(reads, 0);
});

test('a normalized result retains actual weather cells, field-specific source dates and optional origin inputs', () => {
  const input = fixture();
  const snapshot = structuredClone(input);
  const result = validateClimateInputs(input, context);
  assert.equal(result.status, 'available');
  assert.equal(result.partial, false);
  assert.equal(result.message, '');
  assert.equal(result.methodLabel, 'Historical monthly averages');
  assert.equal(result.estimateType, 'district_level');
  assert.equal(result.sourceZone, null);
  assert.equal(result.includesFilledHistory, true);
  assert.deepEqual(result.rows[0], { month: '2026-11', rainfall: 0, temperature: -2.5, evapotranspiration: 80 });
  assert.deepEqual(result.sourceDates, { rainfall: '2026-09-01', temperature: '2025-02-01', evapotranspiration: '2024-12-01' });
  assert.deepEqual(result.origin, { month: '2026-10', rainfall: 5, temperature: 22, evapotranspiration: 90,
    basisLabel: 'Historical monthly averages' });
  assert.deepEqual(input, snapshot);
});

test('cross-year and leap-day requests preserve exactly the six next full calendar months', () => {
  for (const [date, expected] of [
    ['2026-12-31', ['2027-01', '2027-02', '2027-03', '2027-04', '2027-05', '2027-06']],
    ['2024-02-29', ['2024-03', '2024-04', '2024-05', '2024-06', '2024-07', '2024-08']],
  ]) {
    const value = fixture();
    value.as_of = date;
    value.weather_basis.as_of = date;
    value.forecast.forEach((row, index) => { row.month = expected[index]; row.date = `${expected[index]}-01`; });
    assert.deepEqual(validateClimateInputs(value, { districtId, asOf: date }).rows.map(row => row.month), expected);
  }
});

test('identity, date, horizon, model, status and metadata mismatches never display a different product', () => {
  for (const mutate of [
    value => { value.district_id = 'TS-Adilabad'; }, value => { value.as_of = '2026-10-23'; },
    value => { value.horizon_months = 12; }, value => { value.horizon_months = '6'; },
    value => { value.projection_method = 'damped_seasonal_trend'; }, value => { value.status = 'success'; },
    value => { value.estimate_type = 'unknown'; }, value => { value.estimate_type = 'insufficient_data'; },
    value => { value.estimate_type = 'zone_fallback'; value.source_zone = null; },
    value => { value.weather_basis = null; }, value => { value.weather_basis.units = null; },
    value => { value.weather_basis.units.rainfall = 'mm'; }, value => { value.weather_basis.units.temperature = 'F'; },
    value => { value.weather_basis.units.evapotranspiration = 'm/month'; },
    value => { value.weather_basis.source = 'live_weather_forecast'; },
    value => { value.weather_basis.method = 'specified_weather_scenario'; },
    value => { value.weather_basis.as_of = '2026-10-01'; },
    value => { value.weather_basis.future_weather_is_observed = true; },
    value => { delete value.weather_basis.future_weather_is_observed; },
  ]) {
    const value = fixture(); mutate(value);
    assert.throws(() => validateClimateInputs(value, context), /Compatible six-month weather assumptions/);
  }
});

test('incomplete, repeated, shifted and misdated month rows are incompatible rather than reordered or padded', () => {
  for (const mutate of [
    value => { value.forecast = {}; }, value => { value.forecast.pop(); },
    value => { value.forecast.push(value.forecast[0]); }, value => { value.forecast[0] = null; },
    value => { value.forecast[1].month = value.forecast[0].month; },
    value => { value.forecast.reverse(); }, value => { value.forecast[0].month = '2026-10'; },
    value => { value.forecast[0].date = '2026-11-02'; }, value => { value.forecast[0].date = '2026-11'; },
  ]) {
    const value = fixture(); mutate(value);
    assert.throws(() => validateClimateInputs(value, context), /Compatible six-month weather assumptions/);
  }
});

test('missing, nonnumeric, nonfinite and nonphysical weather cells remain null in otherwise usable rows', () => {
  const examples = [
    ['rainfall_mm', 'rainfall', -1], ['rainfall_mm', 'rainfall', '0'],
    ['rainfall_mm', 'rainfall', true], ['rainfall_mm', 'rainfall', null],
    ['temperature_c', 'temperature', -101], ['temperature_c', 'temperature', 71],
    ['temperature_c', 'temperature', NaN], ['temperature_c', 'temperature', Infinity],
    ['evapotranspiration_mm', 'evapotranspiration', -1],
    ['evapotranspiration_mm', 'evapotranspiration', undefined],
  ];
  for (const [apiKey, key, invalid] of examples) {
    const value = fixture(); value.forecast[0].weather[apiKey] = invalid;
    const result = validateClimateInputs(value, context);
    assert.equal(result.status, 'available');
    assert.equal(result.rows[0][key], null);
    assert.equal(result.rows.length, 6);
    assert.equal(result.partial, true);
    assert.match(result.message, /Some weather inputs are unavailable/);
  }
  const value = fixture(); delete value.forecast[0].weather;
  assert.deepEqual(validateClimateInputs(value, context).rows[0],
    { month: '2026-11', rainfall: null, temperature: null, evapotranspiration: null });
});

test('zero rainfall and ET and physical negative Celsius values never become unavailable', () => {
  const value = fixture();
  value.forecast[0].weather = { rainfall_mm: 0, temperature_c: -10, evapotranspiration_mm: 0 };
  const result = validateClimateInputs(value, context);
  assert.deepEqual(result.rows[0], { month: '2026-11', rainfall: 0, temperature: -10, evapotranspiration: 0 });
  assert.equal(result.partial, false);
});

test('unrelated depth estimates are not required or validated as weather inputs', () => {
  const value = fixture();
  value.units = 'unrelated-depth-unit';
  value.estimated_current_gwl = NaN;
  value.forecast[0].predicted_gwl = '<invalid depth>';
  assert.equal(validateClimateInputs(value, context).status, 'available');
});

test('zone fallback and field-specific historical freshness remain explicit without invented combined dates', () => {
  const value = fixture();
  value.estimate_type = 'zone_fallback'; value.source_zone = 'Western Plateau and Hills';
  value.weather_basis.latest_historical_weather_dates = { rainfall: '2026-09-01', temperature: '2025-02-29', evapotranspiration: '2027-01-01' };
  value.weather_basis.latest_historical_weather_date = '2026-09-01';
  delete value.weather_basis.weather_history_may_include_filled_values;
  const result = validateClimateInputs(value, context);
  assert.equal(result.estimateType, 'zone_fallback');
  assert.equal(result.sourceZone, 'Western Plateau and Hills');
  assert.deepEqual(result.sourceDates, { rainfall: '2026-09-01', temperature: null, evapotranspiration: null });
  assert.equal(result.includesFilledHistory, null);
  delete value.weather_basis.latest_historical_weather_dates;
  assert.deepEqual(validateClimateInputs(value, context).sourceDates, { rainfall: null, temperature: null, evapotranspiration: null });
  value.weather_basis.weather_history_may_include_filled_values = false;
  assert.equal(validateClimateInputs(value, context).includesFilledHistory, false);
});

test('optional origin inputs require an exposed known basis and keep unavailable cells distinct', () => {
  const value = fixture(); delete value.weather_basis.origin_weather;
  assert.equal(validateClimateInputs(value, context).origin, null);
  assert.equal(validateClimateInputs(value, context).partial, false);
  value.weather_basis.origin_weather = { method: 'historical_origin_weather', rainfall_mm: 0,
    temperature_c: Infinity, evapotranspiration_mm: 90 };
  const result = validateClimateInputs(value, context);
  assert.deepEqual(result.origin, { month: '2026-10', rainfall: 0, temperature: null, evapotranspiration: 90,
    basisLabel: 'Historical origin-month inputs' });
  assert.equal(result.partial, true);
  value.weather_basis.origin_weather.method = 'live_observation';
  assert.equal(validateClimateInputs(value, context).origin, null, 'Do not invent origin provenance');
});

test('insufficient-data abstentions preserve the exact plain-text reason and never manufacture rows', () => {
  const value = fixture();
  value.status = 'insufficient_data'; value.forecast = []; value.weather_basis = null;
  value.message = 'Not enough historical rainfall, temperature or evapotranspiration for all future months.';
  const result = validateClimateInputs(value, context);
  assert.equal(result.status, 'unavailable');
  assert.equal(result.message, value.message);
  assert.deepEqual(result.rows, []);
  assert.equal(result.origin, null);
  assert.equal(result.partial, false);
  assert.equal(result.methodLabel, 'Unavailable');
  assert.deepEqual(result.sourceDates, { rainfall: null, temperature: null, evapotranspiration: null });
  assert.equal(result.includesFilledHistory, null);
  value.message = { unsafe: 'Not a text message' };
  assert.equal(validateClimateInputs(value, context).message, 'Weather assumptions are unavailable for this district.');
  value.forecast = fixture().forecast;
  assert.throws(() => validateClimateInputs(value, context), /Compatible six-month weather assumptions/);
});

test('server-provided reasons and zone names remain plain text for React escaping', () => {
  const value = fixture();
  value.status = 'insufficient_data'; value.forecast = [];
  value.estimate_type = 'zone_fallback'; value.source_zone = '<img src=x onerror=alert(1)>';
  value.message = '<script>service unavailable</script>';
  const result = validateClimateInputs(value, context);
  assert.equal(typeof result.message, 'string');
  const html = renderToStaticMarkup(createElement('div', null, result.message, result.sourceZone));
  assert.match(html, /&lt;script&gt;service unavailable&lt;\/script&gt;/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(html, /<script|<img/);
});
