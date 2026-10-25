export const STATE_XGB_VERSION = '2.0-state-district-xgboost';
const supportedVersion = value => [STATE_XGB_VERSION, '3.0-state-tiered'].includes(value);
function validateMix(value, total) {
  const counts = value.evidence_tier_counts;
  if (!counts || Object.entries(counts).some(([tier, count]) => !['A','B','C','D'].includes(tier) || !Number.isInteger(count) || count < 0)
    || Object.values(counts).reduce((a,b) => a+b,0) !== total) fail('invalid evidence tier counts');
  if (value.evidence_tier_proportions && ['A','B','C','D'].some(tier =>
    !Number.isFinite(value.evidence_tier_proportions[tier]) || Math.abs(value.evidence_tier_proportions[tier] - (counts[tier] || 0) / total) > .0001)) fail('invalid evidence proportions');
}
const finiteDepth = value => Number.isFinite(value) && value >= 0;
const integer = value => Number.isInteger(value) && value >= 0;
const date = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
  && Number.isFinite(Date.parse(`${value}T00:00:00Z`))
  && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
const validId = value => typeof value === 'string' && /^[A-Z]{2}$/.test(value);
const fail = reason => { throw new Error(`Invalid state XGBoost response: ${reason}`); };
const idList = (values, stateId) => Array.isArray(values) && new Set(values).size === values.length
  && values.every(value => typeof value === 'string' && value.startsWith(`${stateId}-`) && value.length > 3);

export function stateForecastMonths(asOf) {
  if (!date(asOf)) return null;
  const [year, month] = asOf.split('-').map(Number);
  return Array.from({ length: 12 }, (_, index) => new Date(Date.UTC(year, month + index, 1)).toISOString().slice(0, 7));
}

export function validateStatesRegistry(value) {
  if (!value || value.horizon_months !== 12 || !date(value.as_of) || !Array.isArray(value.states)
    || !integer(value.total) || value.total !== value.states.length) fail('incompatible registry or horizon');
  const ids = new Set();
  for (const row of value.states) {
    if (!validId(row.state_id) || ids.has(row.state_id) || typeof row.state_name !== 'string' || !row.state_name.trim()
      || !idList(row.districts, row.state_id) || row.total_districts !== row.districts.length) fail('invalid state registry');
    ids.add(row.state_id);
  }
  return value;
}

// A stable registry choice does not assume that this state has an available forecast.
export function defaultStateId(states) {
  return (states.find(row => row.state_type === 'State') || states[0])?.state_id;
}

export function validateStatesSummary(value, expectedAsOf = null, registry = null) {
  if (!value || value.product !== 'state_groundwater_summary' || !supportedVersion(value.model_version)
    || value.horizon_months !== 12 || !date(value.as_of) || !Array.isArray(value.states)
    || (expectedAsOf !== null && value.as_of !== expectedAsOf)
    || value.total_states !== value.states.length) fail('incompatible summary or horizon');
  if (registry && (value.states.length !== registry.states.length
    || value.states.some(row => !registry.states.some(state => state.state_id === row.state_id
      && state.total_districts === row.total_districts)))) fail('summary differs from state registry');
  const ids = new Set();
  for (const row of value.states) {
    if (value.model_version === '3.0-state-tiered') validateMix(row, row.total_districts);
    if (!validId(row.state_id) || ids.has(row.state_id) || typeof row.state_name !== 'string' || !row.state_name.trim()) fail('invalid or duplicate state');
    ids.add(row.state_id);
    if (!['available', 'insufficient_data', 'model_unavailable', 'unavailable'].includes(row.status)) fail('invalid state availability');
    if (!integer(row.total_districts) || !integer(row.contributing_districts) || row.contributing_districts > row.total_districts
      || !Number.isFinite(row.district_coverage_pct) || row.district_coverage_pct < 0 || row.district_coverage_pct > 100) fail('invalid summary coverage');
    const anchor = row.estimated_current_gwl_m_bgl ?? row.current_gwl_m_bgl;
    if (row.status === 'available') {
      if (!finiteDepth(anchor) || !finiteDepth(row.forecast_12m_gwl_m_bgl) || !Number.isFinite(row.projected_change_12m_m)) fail('invalid summary prediction');
    } else if (row.forecast_12m_gwl_m_bgl != null || row.projected_change_12m_m != null) fail('unavailable state contains predictions');
  }
  const available = value.states.filter(row => row.status === 'available').length;
  if (value.available_states_count !== available || value.insufficient_data_states_count !== value.states.length - available) fail('summary counts do not match state records');
  return value;
}

export function validateStateForecast(value, expectedId, expectedAsOf = null) {
  if (!value || value.product !== 'state_groundwater_12m_forecast' || !supportedVersion(value.model_version)
    || value.model_name !== (value.model_version === '3.0-state-tiered' ? 'district_tiered_equal_weight' : 'district_xgboost_equal_weight') || !validId(value.state_id) || value.state_id !== expectedId
    || typeof value.state_name !== 'string' || !value.state_name.trim() || value.units !== 'm_bgl'
    || value.horizon_months !== 12 || !date(value.as_of) || (expectedAsOf !== null && value.as_of !== expectedAsOf)
    || !date(value.forecast_origin) || value.forecast_origin.slice(0, 7) !== value.as_of.slice(0, 7)
    || value.forecast_origin > value.as_of || !/(Z|[+-]\d{2}:\d{2})$/.test(value.computed_at || '')
    || !Number.isFinite(Date.parse(value.computed_at)) || !Array.isArray(value.forecast)) fail('incompatible state, model, dates or horizon');
  if (!['forecast', 'insufficient_data', 'model_unavailable', 'unavailable'].includes(value.status)) fail('invalid status');
  if (!idList(value.districts, value.state_id)) fail('invalid state district registry');
  if (value.status !== 'forecast') {
    if (value.forecast.length || typeof (value.message || value.unavailable_reason) !== 'string') fail('unavailable forecast must be empty and explained');
    return value;
  }
  if (!finiteDepth(value.estimated_current_gwl_m_bgl) || value.current_depth_basis !== 'estimated_district_inputs'
    || !idList(value.contributing_district_ids, value.state_id) || !value.contributing_district_ids.length
    || value.contributing_district_ids.some(id => !value.districts.includes(id))
    || value.contributing_districts_count !== value.contributing_district_ids.length
    || value.total_districts_in_state !== value.districts.length || !Array.isArray(value.excluded_districts)
    || typeof value.panel_id !== 'string' || !value.panel_id.trim()
    || typeof value.aggregation_method !== 'string' || !value.aggregation_method.trim()) fail('invalid fixed district panel or estimated anchor');
  const coverage = 100 * value.contributing_district_ids.length / value.districts.length;
  if (value.model_version === '3.0-state-tiered') {
    validateMix(value, value.districts.length);
    if (coverage !== 100 || value.aggregation_method !== 'equal_weight_all_registered_districts') fail('incomplete tiered state panel');
  }
  if (!Number.isFinite(value.district_coverage_pct) || Math.abs(value.district_coverage_pct - coverage) > .11
    || coverage < 50 || value.contributing_district_ids.length < Math.min(2, value.districts.length)) fail('insufficient or inconsistent panel coverage');
  const months = stateForecastMonths(value.as_of);
  if (value.forecast.length !== 12) fail('exactly twelve monthly predictions required');
  value.forecast.forEach((row, i) => {
    if (row.horizon !== i + 1 || row.target_date !== `${months[i]}-01` || !finiteDepth(row.predicted_gwl)
      || !Number.isFinite(row.delta_from_current_m)
      || Math.abs(row.delta_from_current_m - (row.predicted_gwl - value.estimated_current_gwl_m_bgl)) > .001) fail(`invalid horizon ${i + 1}`);
  });
  if (!Array.isArray(value.history)) fail('missing observed history');
  let previous = '';
  for (const row of value.history) {
    if (!date(row.date) || !row.date.endsWith('-01') || row.date <= previous || row.date > value.as_of || !finiteDepth(row.gwl_m_bgl)) fail('invalid observed history dates or values');
    previous = row.date;
  }
  return value;
}

/** Keep observations separate; no bridge from a stale observation to a forecast. */
export function stateChartRows(value) {
  if (value?.status !== 'forecast') return [];
  const observed = new Map(value.history.map(row => [row.date.slice(0, 7), row]));
  const predictions = new Map(value.forecast.map(row => [row.target_date.slice(0, 7), row]));
  const first = value.history.length ? value.history[0].date.slice(0, 7) : value.forecast[0].target_date.slice(0, 7);
  const last = value.forecast.at(-1).target_date.slice(0, 7);
  const [year, month] = first.split('-').map(Number);
  const rows = [];
  for (let i = 0; i < 1200; i++) {
    const key = new Date(Date.UTC(year, month - 1 + i, 1)).toISOString().slice(0, 7);
    if (key > last) break;
    const history = observed.get(key), forecast = predictions.get(key);
    rows.push({ month: key, observed: history?.gwl_m_bgl ?? null, predicted: forecast?.predicted_gwl ?? null,
      horizon: forecast?.horizon ?? null, delta: forecast?.delta_from_current_m ?? null,
      districts: history?.contributing_districts_count ?? null, coverage: history?.district_coverage_pct ?? null });
  }
  return rows;
}
