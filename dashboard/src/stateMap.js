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

export function buildStateLookup(states = []) {
  const lookup = {};
  states.forEach(s => {
    if (s.state_id) lookup[s.state_id.toUpperCase()] = s;
    if (s.state_name) lookup[s.state_name.toLowerCase()] = s;
  });
  return lookup;
}

export function matchState(properties = {}, lookup = {}) {
  const sid = String(properties.state_id || '').toUpperCase();
  if (sid && lookup[sid]) return lookup[sid];
  const sName = String(properties.state_name || properties.st_nm || '').toLowerCase();
  if (sName && lookup[sName]) return lookup[sName];
  return null;
}
