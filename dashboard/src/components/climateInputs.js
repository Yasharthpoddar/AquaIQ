import { fetchPredict } from '../api.js';
import { followingCalendarMonths } from './forecastGraph.js';

export const CLIMATE_FIELDS = Object.freeze([
  { key: 'rainfall', label: 'Rainfall', unit: 'mm/month' },
  { key: 'temperature', label: 'Temperature', unit: '°C' },
  { key: 'evapotranspiration', label: 'Evapotranspiration', unit: 'mm/month' },
].map(field => Object.freeze(field)));

const API_FIELDS = { rainfall: 'rainfall_mm', temperature: 'temperature_c', evapotranspiration: 'evapotranspiration_mm' };
const EXPECTED_UNITS = { rainfall: 'mm/month', temperature: 'degC', evapotranspiration: 'mm/month' };
const ORIGIN_METHODS = {
  historical_origin_weather: 'Historical origin-month inputs',
  historical_monthly_climatology: 'Historical monthly averages',
};
const incompatible = () => { throw new Error('Compatible six-month weather assumptions are unavailable. Please retry.'); };
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = value => typeof value === 'string' && value.trim() ? value : null;

function validDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/u.test(value)) return false;
  const timestamp = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === value;
}

function requestMonths(districtId, asOf) {
  if (!text(districtId) || !validDate(asOf)) incompatible();
  const months = followingCalendarMonths(asOf.slice(0, 7));
  if (!months) incompatible();
  return months.slice(0, 6);
}

function climateCell(value, field) {
  if (!Number.isFinite(value)) return null;
  return field === 'temperature' ? value >= -100 && value <= 70 ? value : null : value >= 0 ? value : null;
}

function climateValues(weather) {
  return Object.fromEntries(CLIMATE_FIELDS.map(({ key }) => [key, climateCell(weather?.[API_FIELDS[key]], key)]));
}

/** Normalize only exposed weather assumptions; groundwater depth outputs are unrelated. */
export function validateClimateInputs(value, { districtId, asOf }) {
  const months = requestMonths(districtId, asOf);
  if (!object(value) || value.district_id !== districtId || value.as_of !== asOf
    || value.horizon_months !== 6 || value.projection_method !== 'climate_conditioned_xgboost_monthly'
    || !['projection', 'insufficient_data'].includes(value.status) || !Array.isArray(value.forecast)
    || !['district_level', 'zone_fallback', 'insufficient_data'].includes(value.estimate_type)) incompatible();
  const sourceZone = value.estimate_type === 'zone_fallback' ? text(value.source_zone) : null;
  if (value.estimate_type === 'zone_fallback' && sourceZone === null) incompatible();
  if (value.status === 'projection' && value.estimate_type === 'insufficient_data') incompatible();
  const basis = value.weather_basis;
  // Legitimate early abstentions have not computed weather metadata yet.
  if (basis != null && (!object(basis) || basis.source !== 'historical_weather_climatology'
    || basis.method !== 'historical_monthly_climatology' || basis.as_of !== asOf
    || basis.future_weather_is_observed !== false || !object(basis.units)
    || CLIMATE_FIELDS.some(({ key }) => basis.units[key] !== EXPECTED_UNITS[key]))) incompatible();
  const sourceDates = Object.fromEntries(CLIMATE_FIELDS.map(({ key }) => {
    const date = basis?.latest_historical_weather_dates?.[key];
    return [key, validDate(date) && date <= asOf ? date : null];
  }));
  const result = {
    status: 'unavailable', asOf, rows: [],
    message: text(value.message) || 'Weather assumptions are unavailable for this district.',
    methodLabel: basis ? 'Historical monthly averages' : 'Unavailable',
    estimateType: value.estimate_type, sourceZone, sourceDates,
    includesFilledHistory: typeof basis?.weather_history_may_include_filled_values === 'boolean'
      ? basis.weather_history_may_include_filled_values : null,
    origin: null, partial: false,
  };
  if (value.status === 'insufficient_data') {
    if (value.forecast.length) incompatible();
    return result;
  }
  if (!basis || value.forecast.length !== 6) incompatible();
  result.rows = value.forecast.map((row, index) => {
    if (!object(row) || row.month !== months[index] || row.date !== `${months[index]}-01`) incompatible();
    const values = climateValues(row.weather);
    if (Object.values(values).some(cell => cell === null)) result.partial = true;
    return { month: row.month, ...values };
  });
  const origin = basis.origin_weather;
  if (object(origin) && Object.hasOwn(ORIGIN_METHODS, origin.method)) {
    const values = climateValues(origin);
    if (Object.values(values).some(cell => cell === null)) result.partial = true;
    if (Object.values(values).some(cell => cell !== null)) {
      result.origin = { month: asOf.slice(0, 7), ...values, basisLabel: ORIGIN_METHODS[origin.method] };
    }
  }
  result.status = 'available';
  result.message = result.partial ? 'Some weather inputs are unavailable.' : '';
  return result;
}

export async function loadClimateInputs(districtId, asOf) {
  requestMonths(districtId, asOf);
  const value = await fetchPredict(districtId, { window: 'next_six_months', months: 6, as_of: asOf });
  return validateClimateInputs(value, { districtId, asOf });
}
