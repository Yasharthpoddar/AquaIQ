/** One canonical destination for Home's existing search, map and district links. */
export function districtForecastPath(districtId) {
  if (typeof districtId !== 'string' || !districtId.trim()) throw new Error('A canonical district ID is required.');
  return `/district/${encodeURIComponent(districtId)}#forecast-graph`;
}
