/** The only current research artifact estimates M+12; intermediate ML values stay missing. */
export function followingCalendarMonths(origin) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(origin || '')) return null;
  const absolute = Number(origin.slice(0, 4)) * 12 + Number(origin.slice(5)) - 1;
  const months = Array.from({ length: 12 }, (_, index) => {
    const target = absolute + index + 1;
    return `${String(Math.floor(target / 12)).padStart(4, '0')}-${String(target % 12 + 1).padStart(2, '0')}`;
  });
  return months.every(month => /^\d{4}-\d{2}$/.test(month)) ? months : null;
}

export function validateForecastGraph(result) {
  const unsupported = () => { throw new Error('A compatible twelve-month research graph is currently unavailable. Please retry.'); };
  if (!result || result.product !== 'direct_12month_research_graph'
    || result.horizon_months !== 12 || result.units !== 'm_bgl'
    || !['available', 'unavailable'].includes(result.status)
    || !['historical_research', 'current_vintage_research'].includes(result.output_kind)
    || result.forecast_issued_at !== null
    || !Array.isArray(result.forecast) || result.forecast.length !== 12) unsupported();
  const months = result.origin_month == null ? null : followingCalendarMonths(result.origin_month);
  if (result.origin_month != null && !months) unsupported();
  if (result.target_month !== (months?.[11] ?? null)) unsupported();
  for (const [index, row] of result.forecast.entries()) {
    if (!row || row.horizon_months !== index + 1 || row.month !== (months?.[index] ?? null)) unsupported();
    for (const field of ['predicted_gwl', 'annual_baseline_m']) {
      const value = row[field];
      if (value !== null && (!Number.isFinite(value) || index !== 11 || !months
        || result.source?.origin_is_observed !== true || result.source?.origin_is_imputed !== false)) unsupported();
    }
  }
  if (result.forecast[11].predicted_gwl !== result.ml_estimate_m
    || result.forecast[11].annual_baseline_m !== result.annual_baseline_m
    || !Array.isArray(result.unavailable_reasons) || !Array.isArray(result.limitations)
    || [...result.unavailable_reasons, ...result.limitations].some(value => typeof value !== 'string')) unsupported();
  if (result.status === 'unavailable' && result.ml_estimate_m !== null
    || result.status === 'available' && !Number.isFinite(result.ml_estimate_m)) unsupported();
  return result;
}

export function forecastChartRows(result) {
  return (result?.forecast || []).filter(row => row.month != null).map(row => ({
    month: row.month,
    predicted: Number.isFinite(row.predicted_gwl) ? row.predicted_gwl : null,
  }));
}
