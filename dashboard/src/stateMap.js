import { medianMethodLabel } from './components/stateMedianForecastContract.js';

/**
 * AquaIQ — State Map Helper and Color Scales
 *
 * Pure JavaScript utilities for India state GeoJSON boundaries,
 * state lookups, and hydrogeological metric color scales.
 */

export function getStateColor(state, metric = 'depth') {
  if (!state || state.status !== 'available') return '#e2e8f0'; // slate-200

  if (metric === 'depth') {
    const depth = state.current_gwl_m_bgl;
    if (typeof depth !== 'number' || !Number.isFinite(depth)) return '#e2e8f0';
    if (depth < 5.0) return '#22c55e'; // shallow / good availability (green)
    if (depth < 10.0) return '#eab308'; // moderate depth (yellow)
    if (depth < 20.0) return '#f97316'; // deep water table (orange)
    return '#ef4444'; // very deep / high depletion (red)
  }

  // metric === 'delta' (12m projected change in depth)
  const delta = state.projected_change_12m_m;
  if (typeof delta !== 'number' || !Number.isFinite(delta)) return '#e2e8f0';
  if (delta < -1.0) return '#059669'; // substantial water table rise / recharge (dark green)
  if (delta <= 0.0) return '#10b981'; // mild rise (green)
  if (delta <= 1.0) return '#f59e0b'; // mild drop in water table (amber)
  return '#ef4444'; // substantial depletion / water table drop (red)
}

/** Primary median map uses an explicitly dated observed reference, never a current-depth estimate. */
export function getMedianStateColor(state, metric = 'depth') {
  if (!state) return '#e2e8f0';
  if (metric === 'depth') {
    const value = state.last_observed_gwl_m_bgl;
    if (!Number.isFinite(value)) return '#e2e8f0';
    if (value < 5) return '#22c55e';
    if (value < 10) return '#eab308';
    if (value < 20) return '#f97316';
    return '#ef4444';
  }
  const value = state.projected_change_12m_m;
  if (state.status !== 'available' || !Number.isFinite(value)) return '#e2e8f0';
  if (value < -1) return '#059669';
  if (value <= 0) return '#10b981';
  if (value <= 1) return '#f59e0b';
  return '#ef4444';
}

export function medianStateMapDescription(state) {
  if (!state) return 'State median summary unavailable.';
  if (state.status === 'pending') return `${state.state_name} · Median summary loading. Select to inspect this state.`;
  if (state.status === 'summary_error') return `${state.state_name} · Median summary unavailable. Select to inspect this state.`;
  const reference = Number.isFinite(state.last_observed_gwl_m_bgl)
    ? `Observed reference median: ${state.last_observed_gwl_m_bgl.toFixed(2)} m bgl (${state.historical_reference_date})${Number.isInteger(state.reference_age_months) ? `, ${state.reference_age_months} months old` : ''}.`
    : 'No genuine historical median reference.';
  const forecast = state.status === 'available' ? `M+12 median forecast: ${state.forecast_12m_gwl_m_bgl.toFixed(2)} m bgl.`
    : state.status === 'insufficient_data' ? 'Insufficient historical data for this model.' : 'Median model unavailable.';
  return `${state.state_name} · ${medianMethodLabel(state)}. ${reference} ${forecast} Reference coverage: ${state.contributing_districts_count}/${state.total_districts_in_state} districts (${state.district_coverage_pct.toFixed(1)}%).${state.reference_training_eligible === false ? ' Below XGBoost training-target coverage.' : ''}`;
}

export function buildStateLookup(states = []) {
  const lookup = {};
  states.forEach(s => {
    if (s.state_id) {
      const id = s.state_id.toUpperCase();
      if (lookup[id]) throw new Error(`Duplicate state ID: ${id}`);
      lookup[id] = s;
    }
  });
  return lookup;
}

export function matchState(properties = {}, lookup = {}) {
  const sid = String(properties.state_id || '').toUpperCase();
  if (sid && lookup[sid]) return lookup[sid];
  return null;
}

export function searchStates(states = [], query = '') {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return states.filter(row => terms.every(term => `${row.state_name} ${row.state_id}`.toLowerCase().includes(term)));
}

export function stateSelectionId(states, candidate) {
  const id = String(candidate || '').trim().toUpperCase();
  return states.some(row => row.state_id === id) ? id : null;
}
