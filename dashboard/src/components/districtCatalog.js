import { validateStatesSummary } from './stateForecastContract.js';

export function validateDistrictCatalog(value) {
  if (!value || !Array.isArray(value.districts) || value.total !== value.districts.length || !value.total) {
    throw new Error('District registry response is incomplete.');
  }
  const ids = new Set();
  for (const row of value.districts) {
    if (typeof row.district_id !== 'string' || !/^[A-Z]{2}-.+/.test(row.district_id) || ids.has(row.district_id)
      || typeof row.name !== 'string' || !row.name.trim() || typeof row.state !== 'string' || !row.state.trim()
      || row.state_id !== row.district_id.slice(0, 2)) throw new Error('District registry identities are invalid.');
    ids.add(row.district_id);
  }
  return value;
}

/** Scores enrich registered identities; absent scores never remove a district. */
export function mergeDistrictScores(districts, scores = []) {
  const byId = new Map(scores.map(row => [row.district_id, row]));
  return districts.map(district => {
    const evidence = byId.get(district.district_id) || {};
    const score = Number.isFinite(evidence.score) ? evidence.score : null;
    return { ...evidence, ...district, score, tier: score === null ? null : evidence.tier };
  });
}

export function validateHomeForecastSummary(value) {
  validateStatesSummary(value);
  const counts = value.evidence_tier_counts;
  const total = value.states.reduce((sum, row) => sum + row.total_districts, 0);
  if (value.model_version !== '3.0-state-tiered' || value.districts_total !== total || value.districts_forecast !== total
    || !counts || Object.entries(counts).some(([tier, count]) => !['A','B','C','D'].includes(tier) || !Number.isInteger(count) || count < 0)
    || Object.values(counts).reduce((a,b) => a+b,0) !== total) throw new Error('Forecast coverage is incomplete.');
  for (const tier of ['A','B','C','D']) {
    if ((counts[tier] || 0) !== value.states.reduce((sum, state) => sum + (state.evidence_tier_counts[tier] || 0), 0)) {
      throw new Error('Forecast evidence counts differ from state summaries.');
    }
  }
  return value;
}
