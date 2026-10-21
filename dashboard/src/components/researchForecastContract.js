// Exact calendar arithmetic, independent of local timezones and irregular rows.
export function twelveMonthTarget(origin) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(origin || '')) return null;
  return `${String(Number(origin.slice(0, 4)) + 1).padStart(4, '0')}-${origin.slice(5)}`;
}

const incompatible = () => { throw new Error('The twelve-month research response is incompatible or incomplete. No research estimate has been displayed.'); };

function validateProduct(result) {
  if (!result || result.product !== 'direct_12month_research'
    || result.horizon_months !== 12 || result.units !== 'm_bgl') incompatible();
}

export function validateResearchCatalog(result) {
  validateProduct(result);
  if (!Array.isArray(result.districts) || result.districts.some(district =>
    typeof district.district_id !== 'string' || !district.district_id
    || !Array.isArray(district.origin_months)
    || district.origin_months.some(month => !twelveMonthTarget(month)))) incompatible();
  return result;
}

export function validateResearchForecast(result) {
  validateProduct(result);
  if (!['available', 'unavailable'].includes(result.status)
    || !['historical_research', 'current_vintage_research'].includes(result.output_kind)
    || result.forecast_issued_at !== null) incompatible();
  const dated = result.origin_month != null;
  if (dated ? result.target_month !== twelveMonthTarget(result.origin_month)
    || !twelveMonthTarget(result.origin_month) : result.target_month != null) incompatible();
  for (const field of ['ml_estimate_m', 'annual_baseline_m']) {
    if (result[field] !== null && !Number.isFinite(result[field])) incompatible();
    if (result[field] !== null && (!dated || result.source?.origin_is_observed !== true
      || result.source?.origin_is_imputed !== false)) incompatible();
  }
  if (result.observed_target_m != null && (!Number.isFinite(result.observed_target_m)
    || result.output_kind !== 'historical_research')) incompatible();
  if (!Array.isArray(result.unavailable_reasons) || !Array.isArray(result.limitations)
    || [...result.unavailable_reasons, ...result.limitations].some(value => typeof value !== 'string')) incompatible();
  return result;
}

export function formatResearchDepth(value) {
  return Number.isFinite(value) ? `${value.toFixed(3)} m below ground level` : 'Unavailable';
}
