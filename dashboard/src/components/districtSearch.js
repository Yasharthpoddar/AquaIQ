/**
 * Shared, canonical district search for the dashboard and map.
 * Match by ID, district name, state, or "district, state" text.
 */
const normalize = value => String(value ?? '').trim().toLocaleLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ');

export function searchDistricts(districts, query, limit = 8) {
  const q = normalize(query);
  if (!q || q.length < 2) return [];
  return (districts || [])
    .filter(district => {
      const id = normalize(district.district_id);
      const name = normalize(district.name);
      const state = normalize(district.state);
      return id.includes(q) || name.includes(q) || state.includes(q) || normalize(`${name}, ${state}`).includes(q);
    })
    .sort((a, b) => {
      const left = normalize(a.name); const right = normalize(b.name);
      const leftExact = left === q || normalize(a.district_id) === q ? 0 : left.startsWith(q) ? 1 : 2;
      const rightExact = right === q || normalize(b.district_id) === q ? 0 : right.startsWith(q) ? 1 : 2;
      return leftExact - rightExact || left.localeCompare(right) || normalize(a.state).localeCompare(normalize(b.state));
    })
    .slice(0, Math.max(1, limit));
}

export function resolveDistrictSearch(districts, query) {
  const q = normalize(query);
  if (!q) return { status: 'empty', district: null, matches: [] };
  const rows = districts || [];
  const exact = rows.filter(d => normalize(d.district_id) === q || normalize(d.name) === q
    || normalize(`${d.name}, ${d.state}`) === q);
  const candidates = exact.length ? exact : rows.filter(d => {
    const id = normalize(d.district_id);
    const name = normalize(d.name);
    const state = normalize(d.state);
    return id.includes(q) || name.includes(q) || state.includes(q) || normalize(`${name}, ${state}`).includes(q);
  });
  if (candidates.length === 1) return { status: 'found', district: candidates[0], matches: candidates };
  if (candidates.length > 1) return { status: 'ambiguous', district: null, matches: candidates.slice(0, 8) };
  return { status: 'not-found', district: null, matches: [] };
}
