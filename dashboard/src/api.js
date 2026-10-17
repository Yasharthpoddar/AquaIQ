/**
 * AquaIQ API Client
 * Centralized API service supporting VITE_API_URL and relative Vite proxy paths.
 */

export const API_BASE = import.meta.env?.VITE_API_URL || '';

// Share pending reads across components and StrictMode's repeated effects.
// Remove settled requests so retries and later visits always read fresh data.
const pendingReads = new Map();

function getJson(path, label) {
  const url = `${API_BASE}${path}`;
  if (pendingReads.has(url)) return pendingReads.get(url);
  const request = (async () => {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${label} fetch failed: ${res.status}`);
    return res.json();
  })().finally(() => {
    if (pendingReads.get(url) === request) pendingReads.delete(url);
  });
  pendingReads.set(url, request);
  return request;
}

export async function fetchConfig() {
  return getJson('/api/config', 'Config');
}

export async function fetchScores() {
  return getJson('/api/scores', 'Scores');
}

export async function fetchAlerts(tier = null, limit = 100) {
  const params = new URLSearchParams();
  if (tier && tier !== 'All') params.set('tier', tier);
  if (limit) params.set('limit', String(limit));
  const qs = params.toString() ? `?${params.toString()}` : '';
  return getJson(`/api/alerts${qs}`, 'Alerts');
}

export async function fetchDistrict(id) {
  return getJson(`/api/district/${encodeURIComponent(id)}`, 'District');
}

export async function fetchHistory(id, start = '2002-01', end = null) {
  const params = new URLSearchParams({ start });
  if (end) params.set('end', end);
  return getJson(`/api/history/${encodeURIComponent(id)}?${params}`, 'History');
}

export async function fetchPredict(id, params = {}) {
  const q = new URLSearchParams();
  if (params.target_year) q.set('target_year', params.target_year);
  if (params.start) q.set('start', params.start);
  if (params.months) q.set('months', String(params.months));
  if (params.as_of) q.set('as_of', params.as_of);
  if (params.window) q.set('window', params.window);
  const qs = q.toString() ? `?${q.toString()}` : '';
  return getJson(`/api/predict/${encodeURIComponent(id)}${qs}`, 'Predict');
}

export async function postSimulate(payload) {
  const res = await fetch(`${API_BASE}/api/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Simulate failed: ${res.status}`);
  return res.json();
}
