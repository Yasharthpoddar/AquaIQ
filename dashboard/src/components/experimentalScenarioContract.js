import { followingCalendarMonths } from './forecastGraph.js';

export function validateExperimentalScenario(value, expectedDistrict = null) {
  const invalid = () => { throw new Error('A compatible twelve-month experimental scenario is unavailable.'); };
  if (!value || typeof value.district_id !== 'string' || (expectedDistrict !== null && value.district_id !== expectedDistrict)
    || value.product !== 'experimental_12month_scenario'
    || value.output_kind !== 'assumption_based_scenario' || value.units !== 'm_bgl'
    || value.horizon_months !== 12 || value.forecast_issued_at !== null
    || !['scenario', 'unavailable'].includes(value.status)
    || value.validation?.status !== 'unvalidated_scenario'
    || value.validation?.prospective_skill_verified !== false
    || value.validation?.sufficient_for_operational_use !== false
    || value.source?.availability_verified !== false
    || !/^\d{4}-\d{2}-\d{2}$/.test(value.as_of || '')
    || !Number.isFinite(Date.parse(`${value.as_of}T00:00:00Z`))
    || new Date(`${value.as_of}T00:00:00Z`).toISOString().slice(0, 10) !== value.as_of
    || value.as_of_timezone !== 'Asia/Kolkata'
    || !/(Z|[+-]\d\d:\d\d)$/.test(value.computed_at || '')
    || !Number.isFinite(Date.parse(value.computed_at))
    || !Array.isArray(value.forecast)) invalid();
  for (const key of ['assumptions', 'limitations', 'unavailable_reasons']) {
    if (!Array.isArray(value[key]) || !value[key].every(item => typeof item === 'string')) invalid();
  }
  if (value.status === 'unavailable') {
    if (value.forecast.length !== 0 || value.estimated_current_gwl !== null || !value.unavailable_reasons.length) invalid();
    return value;
  }
  const months = followingCalendarMonths(value.as_of.slice(0, 7));
  if (!months || value.forecast.length !== 12 || !Number.isFinite(value.estimated_current_gwl)
    || value.estimated_current_gwl < 0 || value.forecast_start !== months[0] || value.forecast_end !== months[11]
    || !followingCalendarMonths(value.source.last_observed_month)
    || value.source.last_observed_month >= value.as_of.slice(0, 7)
    || !Number.isInteger(value.source.data_age_months) || value.source.data_age_months < 1
    || !Number.isFinite(value.source.last_observed_gwl) || value.source.last_observed_gwl < 0
    || value.source.scope !== 'district_own_observed_history'
    || typeof value.source.name !== 'string' || !value.source.name.trim()
    || typeof value.source.units_qualification !== 'string' || !value.source.units_qualification.trim()
    || !Number.isInteger(value.method?.observed_month_count) || value.method.observed_month_count < 24
    || value.method.name !== 'damped_seasonal_trend' || value.method.parameters_saved !== false
    || !Array.isArray(value.method.observed_calendar_months)) invalid();
  const valid = value.forecast.every((row, i) => row.month === months[i] && row.date === `${months[i]}-01`
    && row.horizon_months === i + 1 && Number.isFinite(row.projected_gwl) && row.projected_gwl >= 0);
  const [currentYear, currentMonth] = value.as_of.split('-').map(Number);
  const [observedYear, observedMonth] = value.source.last_observed_month.split('-').map(Number);
  if (!valid || value.source.data_age_months !== (currentYear-observedYear)*12+currentMonth-observedMonth) invalid();
  return value;
}

export function scenarioChartRows(value) {
  return value?.status === 'scenario' ? value.forecast.map(row => ({ month: row.month, projected: row.projected_gwl })) : [];
}

export function forecastView(search) {
  const params = new URLSearchParams(search);
  if (params.get('view') === 'scenario') return 'scenario';
  return params.get('view') === 'historical' || params.has('origin_month') ? 'historical' : 'scenario';
}
