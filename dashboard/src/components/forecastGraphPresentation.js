import { fetchResearchGraph } from '../api.js';
import { followingCalendarMonths, validateForecastGraph } from './forecastGraph.js';

export function requestedOriginMonth(search) {
  return new URLSearchParams(search).get('origin_month') || null;
}

export async function loadRequestedForecastGraph(districtId, originMonth = null, readGraph = fetchResearchGraph) {
  if (originMonth !== null && !followingCalendarMonths(originMonth)) {
    throw new Error('Select an origin month in YYYY-MM format. No fallback origin has been selected.');
  }
  const result = validateForecastGraph(await readGraph(districtId, originMonth));
  if (originMonth !== null && result.origin_month !== originMonth) {
    throw new Error('The graph response did not match the selected origin month. No fallback origin has been displayed.');
  }
  return result;
}

export function annualBaselineReference(result) {
  if (!Number.isFinite(result?.annual_baseline_m) || !followingCalendarMonths(result?.origin_month)
    || result.target_month !== followingCalendarMonths(result.origin_month)[11]
    || result.source?.origin_is_observed !== true || result.source?.origin_is_imputed !== false) return null;
  return { month: result.target_month, depth: result.annual_baseline_m };
}
