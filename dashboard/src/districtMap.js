const STATE_TO_ABBREV = {
  "andhra pradesh": "AP",
  "arunachal pradesh": "AR",
  "assam": "AS",
  "bihar": "BR",
  "chhattisgarh": "CG",
  "goa": "GA",
  "gujarat": "GJ",
  "haryana": "HR",
  "himachal pradesh": "HP",
  "jharkhand": "JH",
  "karnataka": "KA",
  "kerala": "KL",
  "madhya pradesh": "MP",
  "maharashtra": "MH",
  "manipur": "MN",
  "meghalaya": "ML",
  "mizoram": "MZ",
  "nagaland": "NL",
  "odisha": "OD",
  "punjab": "PB",
  "rajasthan": "RJ",
  "sikkim": "SK",
  "tamil nadu": "TN",
  "telangana": "TS",
  "tripura": "TR",
  "uttar pradesh": "UP",
  "uttarakhand": "UK",
  "west bengal": "WB",
  "delhi": "DL",
  "nct of delhi": "DL",
  "jammu & kashmir": "JK",
  "jammu and kashmir": "JK",
  "ladakh": "LA",
  "puducherry": "PY",
  "chandigarh": "CH",
  "andaman and nicobar islands": "AN",
  "andaman and nicobar": "AN",
  "dadra and nagar haveli and daman and diu": "DD",
  "daman and diu": "DD",
  "dadra and nagar haveli": "DN",
  "lakshadweep": "LD",
};

export function districtName(properties = {}) {
  return String(properties.district || properties.DISTRICT || properties.name || '').trim();
}

export function districtBoundaries(geojson) {
  if (!Array.isArray(geojson?.features)) throw new Error('Boundary response has no features.');
  // The source also contains state polygons. They must not cover district fills.
  return { ...geojson, features: geojson.features.filter(feature => districtName(feature.properties)) };
}

export function buildScoreLookup(scores) {
  const lookup = {};
  scores.forEach(score => {
    if (score.district_id) lookup[score.district_id.toLowerCase()] = score;
    if (score.state && score.name) {
      const key = `${score.state.toLowerCase().trim()}__${score.name.toLowerCase().trim().replace(/\s+/g, '_')}`;
      lookup[key] = Object.hasOwn(lookup, key) ? null : score;
    }
  });
  return lookup;
}

export function matchDistrict(properties = {}, lookup) {
  const name = districtName(properties).replace(/\s+/g, '_').toLowerCase();
  const state = String(properties.st_nm || properties.state || properties.ST_NM || '').trim().toLowerCase();
  const abbreviation = STATE_TO_ABBREV[state]?.toLowerCase();
  const explicit = String(properties.district_id || '').toLowerCase();
  if (explicit && (!abbreviation || explicit.startsWith(`${abbreviation}-`)) && lookup[explicit]) return lookup[explicit];
  if (abbreviation && lookup[`${abbreviation}-${name}`]) return lookup[`${abbreviation}-${name}`];
  return lookup[`${state}__${name}`] || null;
}

export function boundaryCoverage(geojson, scores, lookup = buildScoreLookup(scores)) {
  const mapped = new Set(geojson.features.map(feature => matchDistrict(feature.properties, lookup)?.district_id).filter(Boolean));
  return { mapped: mapped.size, missing: scores.filter(score => !mapped.has(score.district_id)) };
}
