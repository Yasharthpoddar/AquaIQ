/** Search only canonical API records; map geometry is deliberately irrelevant. */
export function normalizeDistrictQuery(value) {
  return String(value ?? '').trim().toLocaleLowerCase().replace(/[\s,_-]+/gu, ' ');
}

export function districtSearchLabel(district) {
  if (!district) return '';
  return `${district.name || district.district_id}${district.state ? `, ${district.state}` : ''} (${district.district_id})`;
}

function canonicalDistricts(districts) {
  const ids = new Set();
  return (Array.isArray(districts) ? districts : []).filter(district => {
    if (typeof district?.district_id !== 'string' || !district.district_id.trim() || ids.has(district.district_id)) return false;
    ids.add(district.district_id);
    return true;
  });
}

function keys(district) {
  const id = normalizeDistrictQuery(district.district_id);
  const name = normalizeDistrictQuery(district.name);
  const state = normalizeDistrictQuery(district.state);
  return { id, name, state, together: normalizeDistrictQuery(`${name} ${state}`),
    label: normalizeDistrictQuery(districtSearchLabel(district)), reverse: normalizeDistrictQuery(`${state} ${name}`) };
}

function rank(district, query) {
  const value = keys(district);
  if (value.id === query) return 0;
  if (value.together === query || value.reverse === query || value.label === query) return 1;
  if (value.name === query) return 2;
  if (value.name.startsWith(query)) return 3;
  if (value.state === query) return 4;
  if (value.id.startsWith(query)) return 5;
  return 6;
}

export function searchDistricts(districts, query, limit = Infinity) {
  const normalized = normalizeDistrictQuery(query);
  if (!normalized) return [];
  const matches = canonicalDistricts(districts).filter(district => Object.values(keys(district))
    .some(value => value.includes(normalized)));
  matches.sort((left, right) => rank(left, normalized) - rank(right, normalized)
    || normalizeDistrictQuery(left.name).localeCompare(normalizeDistrictQuery(right.name))
    || normalizeDistrictQuery(left.state).localeCompare(normalizeDistrictQuery(right.state))
    || left.district_id.localeCompare(right.district_id));
  return matches.slice(0, Number.isFinite(limit) ? Math.max(0, Math.floor(limit)) : undefined);
}

export function resolveDistrictSearch(districts, query) {
  const normalized = normalizeDistrictQuery(query);
  if (!normalized) return { status: 'empty', district: null, matches: [] };
  const matches = searchDistricts(districts, query);
  // A unique canonical ID wins before a name, state or partial match.
  const exactId = matches.filter(district => keys(district).id === normalized);
  const exactLabel = matches.filter(district => {
    const value = keys(district);
    return value.together === normalized || value.reverse === normalized || value.label === normalized;
  });
  const exactName = matches.filter(district => keys(district).name === normalized);
  const candidates = exactId.length ? exactId : exactLabel.length ? exactLabel : exactName.length ? exactName : matches;
  if (candidates.length === 1) return { status: 'found', district: candidates[0], matches: candidates };
  return { status: candidates.length ? 'ambiguous' : 'not-found', district: null, matches: candidates };
}

/** The component and tests use the same keyboard decisions. No first-match guessing. */
export function districtSearchKeyAction(key, { districts, query, matches, activeIndex = -1, open = false }) {
  if (key === 'Escape') return { type: 'close' };
  if (key === 'ArrowDown' || key === 'ArrowUp') {
    if (!matches.length) return { type: 'open', activeIndex: -1 };
    const next = !open || activeIndex < 0 ? (key === 'ArrowDown' ? 0 : matches.length - 1)
      : (activeIndex + (key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length;
    return { type: 'open', activeIndex: next };
  }
  if (key === 'Enter') {
    const district = open && activeIndex >= 0 ? matches[activeIndex] : null;
    return { type: 'submit', result: district ? { status: 'found', district, matches: [district] }
      : resolveDistrictSearch(districts, query) };
  }
  return { type: 'ignore' };
}
