import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadJsx } from './helpers/loadJsx.js';

const {
  validateClimate12mForecast,
  climate12mChartRows,
} = await loadJsx(new URL('../src/components/climateForecast12mContract.js', import.meta.url));

const {
  ClimateForecast12mView,
  Forecast12mTooltip,
} = await loadJsx(new URL('../src/components/DistrictForecastGraph.jsx', import.meta.url));

function valid12mPayload(overrides = {}) {
  const months = [
    '2026-11', '2026-12', '2027-01', '2027-02', '2027-03', '2027-04',
    '2027-05', '2027-06', '2027-07', '2027-08', '2027-09', '2027-10'
  ];
  return {
    product: 'climate_informed_12m_forecast',
    model_version: '1.0-climate-conditioned-12m-xgb',
    district_id: 'DL-Delhi',
    status: 'forecast',
    as_of: '2026-10-24',
    forecast_origin: '2026-10-01',
    timezone: 'Asia/Kolkata',
    horizon_months: 12,
    forecast_horizon: 'next twelve full calendar months',
    units: 'm_bgl',
    forecast_start: '2026-11',
    forecast_end: '2027-10',
    last_observed_date: '2024-05-01',
    last_observed_gwl: 14.2,
    data_age_months: 29,
    estimated_current_gwl: 16.35,
    current_depth_basis: 'estimated_from_historical_groundwater',
    projection_method: 'climate_conditioned_xgboost_12m',
    model_sha256: 'a'.repeat(64),
    model_train_target_cutoff: '2019-12-31',
    limitations: ['Experimental research model'],
    weather_basis: {
      description: 'Historical same-month climatology available at origin.',
      latest_usable_weather_date: '2026-09-01'
    },
    forecast: months.map((m, i) => ({
      month: m,
      date: `${m}-01`,
      horizon: i + 1,
      predicted_gwl: 16.0 + i * 0.1,
      delta_from_current_m: -0.35 + i * 0.1,
      weather: {
        rainfall_mm: 10.0 + i,
        temperature_c: 20.0 + i * 0.5,
        evapotranspiration_mm: 100.0 + i * 5
      }
    })),
    ...overrides
  };
}

test('validateClimate12mForecast accepts a valid 12-month response and matches district', () => {
  const payload = valid12mPayload();
  const validated = validateClimate12mForecast(payload, 'DL-Delhi');
  assert.equal(validated.product, 'climate_informed_12m_forecast');
  assert.equal(validated.forecast.length, 12);
});

test('validateClimate12mForecast rejects invalid horizons, lengths, units or negative depth', () => {
  assert.throws(() => validateClimate12mForecast(valid12mPayload({ horizon_months: 6 })), /Expected horizon_months 12/);
  assert.throws(() => validateClimate12mForecast(valid12mPayload({ units: 'feet' })), /Expected units m_bgl/);
  assert.throws(() => validateClimate12mForecast(valid12mPayload({ model_version: 'wrong' })), /Expected model_version/);
  assert.throws(() => validateClimate12mForecast(valid12mPayload({ product: 'wrong' })), /Expected product/);
  assert.throws(() => validateClimate12mForecast(valid12mPayload({ district_id: 'OTHER' }), 'DL-Delhi'), /District mismatch/);

  // Missing one month
  const shortForecast = valid12mPayload();
  shortForecast.forecast.pop();
  assert.throws(() => validateClimate12mForecast(shortForecast), /Forecast array must contain exactly 12 items/);

  // Negative predicted depth
  const negativeDepth = valid12mPayload();
  negativeDepth.forecast[0].predicted_gwl = -1.5;
  assert.throws(() => validateClimate12mForecast(negativeDepth), /invalid predicted_gwl/);

  // Non-finite weather
  const badWeather = valid12mPayload();
  badWeather.forecast[0].weather.rainfall_mm = NaN;
  assert.throws(() => validateClimate12mForecast(badWeather), /weather rainfall_mm is not finite/);
});

test('climate12mChartRows maps all 12 months with predicted depths and weather values', () => {
  const payload = valid12mPayload();
  const rows = climate12mChartRows(payload);
  assert.equal(rows.length, 12);
  assert.equal(rows[0].month, '2026-11');
  assert.equal(rows[0].horizon, 1);
  assert.equal(rows[0].predicted, 16.0);
  assert.equal(rows[0].rainfall, 10.0);
  assert.equal(rows[11].month, '2027-10');
  assert.equal(rows[11].horizon, 12);
});

test('ClimateForecast12mView renders loading, error, and insufficient data states cleanly', () => {
  const loadingHtml = renderToStaticMarkup(createElement(ClimateForecast12mView, { loading: true }));
  assert.match(loadingHtml, /Loading this district’s 12-month climate forecast/);

  const errorHtml = renderToStaticMarkup(createElement(ClimateForecast12mView, { error: 'Failed to connect to API' }));
  assert.match(errorHtml, /Failed to connect to API/);
  assert.match(errorHtml, /Retry forecast/);

  const insufficientHtml = renderToStaticMarkup(createElement(ClimateForecast12mView, {
    value: { district_id: 'XX-Empty', status: 'insufficient_data', message: 'Not enough observations' }
  }));
  assert.match(insufficientHtml, /12-month forecast unavailable/);
  assert.match(insufficientHtml, /Not enough observations/);
});

test('ClimateForecast12mView renders complete 12-month forecast table and details', () => {
  const payload = valid12mPayload();
  const html = renderToStaticMarkup(createElement(ClimateForecast12mView, { value: payload }));
  assert.match(html, /Next 12 months/);
  assert.match(html, /Experimental forecast/);
  assert.match(html, /District: DL-Delhi/);
  assert.match(html, /Estimated current depth/);
  assert.match(html, /16\.35 m/);
  assert.match(html, /Nov 2026–Oct 2027/);
  assert.match(html, /Higher depth = lower water level/);
  assert.match(html, /View all 12 monthly predictions &amp; climate inputs/);
  assert.match(html, /1\.0-climate-conditioned-12m-xgb/);
  assert.match(html, /Historical same-month climatology available at origin/);
  // Verify month rows in table
  assert.match(html, /Nov 2026/);
  assert.match(html, /M\+1/);
  assert.match(html, /Oct 2027/);
  assert.match(html, /M\+12/);
});

test('Forecast12mTooltip formats depth and weather inputs correctly', () => {
  const activePayload = [{
    payload: {
      month: '2026-11',
      horizon: 1,
      predicted: 17.2187,
      delta: 0.8653,
      rainfall: 4.8,
      temperature: 19.4,
      evapotranspiration: 102.2
    }
  }];
  const html = renderToStaticMarkup(createElement(Forecast12mTooltip, { active: true, payload: activePayload }));
  assert.match(html, /Nov 2026 \(M\+1\)/);
  assert.match(html, /17\.22 m/);
  assert.match(html, /\+0\.87 m/);
  assert.match(html, /Rainfall: 4\.8 mm/);
  assert.match(html, /Temp: 19\.4 °C/);
  assert.match(html, /ET: 102\.2 mm/);
});
