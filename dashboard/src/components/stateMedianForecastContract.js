export const STATE_MEDIAN_VERSION = '1.0-state-median-xgboost';
export const STATE_MEDIAN_TIERED_VERSION = '2.0-state-median-tiered';
export const STATE_MEDIAN_POLICY_VERSION = '1.0-state-median-coverage';
export const STATE_MEDIAN_PRODUCT = 'state_median_groundwater_12m_forecast';
const fail = reason => { throw new Error(`Invalid state median forecast: ${reason}`); };
const date = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
  && Number.isFinite(Date.parse(`${value}T00:00:00Z`))
  && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
const depth = value => Number.isFinite(value) && value >= 0;
const count = value => Number.isInteger(value) && value >= 0;
const tiered = value => value?.model_version === STATE_MEDIAN_TIERED_VERSION;
const modelIdentity = value => tiered(value)
  ? value.model_name === 'state_median_tiered' && value.policy_version === STATE_MEDIAN_POLICY_VERSION
  : value?.model_version === STATE_MEDIAN_VERSION && value.model_name === 'state_median_xgboost';
const monthAge = (asOf, observed) => (Number(asOf.slice(0, 4)) - Number(observed.slice(0, 4))) * 12 + Number(asOf.slice(5, 7)) - Number(observed.slice(5, 7));
export const referenceAgeMonths = value => count(value?.reference_age_months) ? value.reference_age_months
  : date(value?.as_of) && date(value?.historical_reference_date) && value.historical_reference_date <= value.as_of ? monthAge(value.as_of, value.historical_reference_date) : null;

export const medianForecastMethod = value => value?.forecast_method || (value?.model_version === STATE_MEDIAN_VERSION ? 'state_median_xgboost' : null);
export function medianMethodLabel(value) {
  const method = medianForecastMethod(value);
  return method === 'persistence_fallback' ? 'Persistence fallback' : method === 'state_median_xgboost' ? 'State median XGBoost' : method === 'no_observations' ? 'No usable observations' : 'Method unavailable';
}

function validatePolicyEvidence(value, asOf, status) {
  if (status === 'model_unavailable' && value.forecast_method === null && value.genuine_observed_months === null
    && value.genuine_observation_count === null && value.latest_observation_date === null && value.observation_age_months === null) return;
  if (!['state_median_xgboost', 'persistence_fallback', 'no_observations'].includes(value.forecast_method)
    || !count(value.genuine_observed_months) || !count(value.genuine_observation_count)) fail('missing policy method or genuine observation counts');
  const observed = value.genuine_observed_months > 0;
  if (observed !== (value.genuine_observation_count > 0)) fail('inconsistent genuine observation counts');
  if (observed) {
    if (!date(value.latest_observation_date) || value.latest_observation_date > asOf
      || !count(value.observation_age_months) || value.observation_age_months !== monthAge(asOf, value.latest_observation_date)) fail('invalid latest observation date or age');
  } else if (value.latest_observation_date !== null || value.observation_age_months !== null) fail('no-observation state contains an observation date');
  if (value.forecast_method === 'no_observations') {
    if (observed || !['insufficient_data', 'model_unavailable'].includes(status)) fail('no-observations status requires zero genuine observations');
  } else if (status !== 'model_unavailable' && !observed) fail('forecast method requires genuine observations');
  if (value.historical_reference_date !== null && value.historical_reference_date !== undefined) {
    if (!date(value.historical_reference_date) || value.historical_reference_date > asOf
      || !count(value.reference_age_months) || value.reference_age_months !== monthAge(asOf, value.historical_reference_date)
      || typeof value.reference_training_eligible !== 'boolean') fail('invalid historical reference age or quality');
  }
}

function validateCoverage(row) {
  if (!count(row.contributing_districts_count) || !count(row.total_districts_in_state)
    || row.contributing_districts_count > row.total_districts_in_state
    || !Number.isFinite(row.district_coverage_pct) || row.district_coverage_pct < 0 || row.district_coverage_pct > 100) fail('invalid district coverage');
  const expected = row.total_districts_in_state ? 100 * row.contributing_districts_count / row.total_districts_in_state : 0;
  if (Math.abs(row.district_coverage_pct - expected) > .11) fail('inconsistent district coverage');
}

export function validateStateMedianForecast(value, expectedId, expectedAsOf = null, expectedGeneration = null) {
  if (!value || value.product !== STATE_MEDIAN_PRODUCT || !modelIdentity(value) || value.promotion_status !== 'experimental'
    || !/^[A-Z]{2}$/.test(value.state_id || '') || value.state_id !== expectedId || value.units !== 'm_bgl'
    || value.horizon_months !== 12 || !date(value.as_of) || (expectedAsOf !== null && value.as_of !== expectedAsOf)
    || !date(value.forecast_origin) || !value.forecast_origin.endsWith('-01')
    || value.forecast_origin.slice(0, 7) !== value.as_of.slice(0, 7) || value.forecast_origin > value.as_of
    || !/(Z|[+-]\d{2}:\d{2})$/.test(value.computed_at || '') || !Number.isFinite(Date.parse(value.computed_at))
    || !['forecast', 'insufficient_data', 'model_unavailable'].includes(value.status)
    || !Array.isArray(value.history) || !Array.isArray(value.forecast)) fail('incompatible identity, model, dates or status');
  if (expectedGeneration !== null && value.generation_id !== expectedGeneration) fail('forecast generation differs from summary');
  if (value.training_cutoff != null && (!date(value.training_cutoff) || value.training_cutoff > value.as_of)) fail('invalid training cutoff');
  validateCoverage(value);
  if (tiered(value)) validatePolicyEvidence(value, value.as_of, value.status);
  let previous = '';
  for (const row of value.history) {
    validateCoverage(row);
    if (!date(row.date) || !row.date.endsWith('-01') || row.date <= previous || row.date > value.forecast_origin
      || (row.gwl_m_bgl !== null && !depth(row.gwl_m_bgl)) || typeof row.training_eligible !== 'boolean'
      || !count(row.observation_count) || (row.training_eligible && row.gwl_m_bgl === null)
      || !Number.isFinite(row.coverage_ratio) || Math.abs(row.coverage_ratio * 100 - row.district_coverage_pct) > .11) fail('invalid historical observation');
    previous = row.date;
  }
  if (value.status !== 'forecast') {
    if (value.forecast.length || typeof value.message !== 'string' || !value.message.trim()) fail('unavailable forecast must be empty and explained');
  } else {
    const fallback = medianForecastMethod(value) === 'persistence_fallback';
    if ((!fallback && !date(value.training_cutoff)) || value.forecast.length !== 12) fail('missing training cutoff or monthly predictions');
    if (fallback) {
      const reference = value.reference_observation;
      if (value.training_cutoff !== null || value.model_sha256 !== null || !reference || !depth(reference.gwl_m_bgl)
        || reference.date !== value.historical_reference_date || reference.gwl_m_bgl !== value.last_observed_gwl_m_bgl
        || !count(reference.contributing_districts_count) || reference.contributing_districts_count < 1
        || reference.training_eligible !== value.reference_training_eligible
        || typeof value.fallback_reason !== 'string' || !value.fallback_reason.trim()
        || !Array.isArray(value.features) || value.features.length !== 1 || value.features[0] !== 'latest_genuine_state_median') fail('invalid persistence fallback provenance');
      validateCoverage(reference);
    }
    const [year, month] = value.forecast_origin.split('-').map(Number);
    value.forecast.forEach((row, i) => {
      const target = new Date(Date.UTC(year, month + i, 1)).toISOString().slice(0, 10);
      if (row.horizon !== i + 1 || row.target_date !== target || !depth(row.predicted_gwl)
        || row.is_forecast !== true || row.is_observed !== false) fail('invalid forecast calendar, values or provenance');
      if (fallback && Math.abs(row.predicted_gwl - value.last_observed_gwl_m_bgl) > 1e-8) fail('persistence path must equal its genuine reference');
    });
  }
  const evaluation = value.evaluation;
  if (!evaluation || typeof evaluation.status !== 'string' || !count(evaluation.n)) fail('missing evaluation metadata');
  if (medianForecastMethod(value) === 'persistence_fallback'
    && (evaluation.n !== 0 || evaluation.status !== 'not_evaluated_for_fallback')) fail('fallback must not inherit XGBoost evaluation');
  if (evaluation.n > 0) {
    if (!depth(evaluation.mae_m) || !depth(evaluation.rmse_m) || !date(evaluation.period_start)
      || !date(evaluation.period_end) || evaluation.period_start > evaluation.period_end
      || evaluation.period_end > value.as_of) fail('invalid held-out metrics or period');
  } else if (evaluation.mae_m != null || evaluation.rmse_m != null) fail('metrics require held-out observations');
  return value;
}

export function validateMedianStatesRegistry(value) {
  if (!value || value.horizon_months !== 12 || (value.as_of !== null && !date(value.as_of))
    || !Array.isArray(value.states) || value.total !== value.states.length) fail('invalid state registry');
  const ids = new Set();
  for (const row of value.states) {
    if (!/^[A-Z]{2}$/.test(row.state_id || '') || ids.has(row.state_id) || typeof row.state_name !== 'string'
      || !row.state_name.trim() || !Array.isArray(row.districts) || row.total_districts !== row.districts.length
      || new Set(row.districts).size !== row.districts.length
      || row.districts.some(id => typeof id !== 'string' || !id.startsWith(`${row.state_id}-`))) fail('invalid canonical state membership');
    ids.add(row.state_id);
  }
  return value;
}

export function validateMedianStatesSummary(value, registry = null) {
  if (!value || value.product !== 'state_median_groundwater_summary' || !modelIdentity(value)
    || value.horizon_months !== 12 || !date(value.as_of)
    || typeof value.generation_id !== 'string' || !value.generation_id || !Array.isArray(value.states)
    || value.total_states !== value.states.length) fail('incompatible median summary');
  if (registry && (value.states.length !== registry.states.length
    || value.states.some(row => !registry.states.some(state => state.state_id === row.state_id
      && state.total_districts === row.total_districts_in_state)))) fail('summary differs from state registry');
  const ids = new Set();
  for (const row of value.states) {
    if (!/^[A-Z]{2}$/.test(row.state_id || '') || ids.has(row.state_id) || typeof row.state_name !== 'string'
      || !['available', 'insufficient_data', 'model_unavailable'].includes(row.status)) fail('invalid state summary identity or status');
    ids.add(row.state_id);
    validateCoverage(row);
    if (row.forecast_month_count !== undefined && (!count(row.forecast_month_count)
      || row.forecast_month_count !== (row.status === 'available' ? 12 : 0))) fail('state forecast record count differs from availability');
    if (tiered(value)) validatePolicyEvidence(row, value.as_of, row.status === 'available' ? 'forecast' : row.status);
    if (row.last_observed_gwl_m_bgl !== null && !depth(row.last_observed_gwl_m_bgl)) fail('invalid historical reference');
    if (row.historical_reference_date !== null && (!date(row.historical_reference_date) || row.historical_reference_date > value.as_of)) fail('invalid historical reference date');
    if (row.status === 'available') {
      if (!depth(row.last_observed_gwl_m_bgl) || !date(row.historical_reference_date)
        || !depth(row.forecast_12m_gwl_m_bgl) || !Number.isFinite(row.projected_change_12m_m)
        || Math.abs(row.forecast_12m_gwl_m_bgl - row.last_observed_gwl_m_bgl - row.projected_change_12m_m) > .001) fail('invalid median estimate or reference change');
    } else if (row.forecast_12m_gwl_m_bgl !== null || row.projected_change_12m_m !== null) fail('unavailable state contains forecasts');
  }
  const available = value.states.filter(row => row.status === 'available').length;
  if (value.available_states_count !== available || value.insufficient_data_states_count !== value.states.length - available) fail('summary counts differ from state statuses');
  if (tiered(value)) {
    const counts = value.counts_by_forecast_method;
    if (!counts || ['state_median_xgboost', 'persistence_fallback', 'no_observations'].some(method =>
      counts[method] !== value.states.filter(row => row.forecast_method === method).length)) fail('summary method counts differ from states');
  }
  if (value.forecast_month_count !== undefined) {
    const records = medianSummaryRecords(value);
    if (!records || value.forecast_month_count !== records.forecastMonths || value.available_states_count !== records.available
      || value.unavailable_states_count !== records.unavailable) fail('summary forecast counts differ from monthly records');
  }
  return value;
}

/** Counts are confirmed by complete monthly records, independently of observed history. */
export function medianSummaryRecords(value) {
  if (!value?.states?.every(row => count(row.forecast_month_count))) return null;
  const available = value.states.filter(row => row.status === 'available' && row.forecast_month_count === 12);
  return { available: available.length, unavailable: value.states.length - available.length,
    forecastMonths: value.states.reduce((sum, row) => sum + row.forecast_month_count, 0),
    xgboost: available.filter(row => medianForecastMethod({ ...row, model_version: value.model_version }) === 'state_median_xgboost').length,
    persistence: available.filter(row => medianForecastMethod(row) === 'persistence_fallback').length,
    noObservations: value.states.filter(row => row.forecast_method === 'no_observations').length };
}

export function validateStateMedianHistory(value, forecast) {
  if (value?.status === 'model_unavailable' && typeof value.message === 'string') throw new Error(value.message);
  if (!value || !forecast || value.product !== 'state_median_groundwater_history' || value.state_id !== forecast.state_id
    || value.units !== 'm_bgl' || value.as_of !== forecast.as_of || value.generation_id !== forecast.generation_id
    || value.model_version !== forecast.model_version || !Array.isArray(value.history)
    || !forecast.source_data_sha256 || value.source_data_sha256 !== forecast.source_data_sha256
    || !forecast.feature_generation || value.feature_generation !== forecast.feature_generation) fail('full history differs from selected state, generation or source');
  for (const field of ['artifact_release', 'release_manifest_sha256', 'registry_sha256', 'input_cutoff']) {
    if (value[field] != null && forecast[field] != null && value[field] !== forecast[field]) fail(`full history differs from forecast ${field}`);
  }
  let previous = '';
  for (const row of value.history) {
    validateCoverage(row);
    const expectedEligible = row.gwl_m_bgl !== null && row.is_observed === true
      && row.coverage_ratio >= (forecast.min_coverage ?? .5)
      && row.contributing_districts_count >= Math.min(2, row.total_districts_in_state);
    if (!date(row.date) || !row.date.endsWith('-01') || row.date <= previous || row.date > forecast.forecast_origin
      || (value.input_cutoff != null && row.date > value.input_cutoff)
      || typeof row.training_eligible !== 'boolean' || !count(row.observation_count)
      || !Number.isFinite(row.coverage_ratio) || Math.abs(row.coverage_ratio * 100 - row.district_coverage_pct) > .11
      || (row.gwl_m_bgl !== null && (!depth(row.gwl_m_bgl) || row.is_observed !== true || row.is_imputed === true || row.is_forecast === true))
      || row.training_eligible !== expectedEligible) fail('invalid full-history observation or provenance');
    if (previous) {
      const [year, month] = previous.split('-').map(Number);
      if (row.date !== new Date(Date.UTC(year, month, 1)).toISOString().slice(0, 10)) fail('full history must preserve consecutive missing calendar months');
    }
    previous = row.date;
  }
  for (const field of ['earliest_eligible_date', 'earliest_observation_date']) {
    if (value[field] != null && (!date(value[field]) || value[field] > forecast.forecast_origin)) fail('invalid earliest history month');
  }
  const earliestObserved = value.history.find(row => row.is_observed === true && depth(row.gwl_m_bgl))?.date ?? null;
  const earliestEligible = value.history.find(row => row.training_eligible)?.date ?? null;
  if (value.earliest_eligible_date !== undefined && value.earliest_eligible_date !== earliestEligible) fail('earliest eligible month differs from source history');
  if (value.earliest_observation_date !== undefined && value.earliest_observation_date !== earliestObserved) fail('earliest observation month differs from source history');
  return value;
}

export const stateHistoryKey = value => value?.generation_id ? JSON.stringify([value.state_id, value.as_of, value.generation_id, value.source_data_sha256, value.feature_generation]) : null;
export const currentStateHistoryRead = (read, forecast) => read?.key === stateHistoryKey(forecast) ? read : null;

export function medianStateDetails(value) {
  const reference = value.last_observed_gwl_m_bgl ?? null;
  const final = value.forecast.at(-1)?.predicted_gwl ?? null;
  return { state_id: value.state_id, state_name: value.state_name, status: value.status === 'forecast' ? 'available' : value.status,
    last_observed_gwl_m_bgl: reference, historical_reference_date: value.historical_reference_date ?? null,
    forecast_12m_gwl_m_bgl: final, projected_change_12m_m: final !== null && reference !== null ? final - reference : null,
    contributing_districts_count: value.contributing_districts_count, total_districts_in_state: value.total_districts_in_state,
    district_coverage_pct: value.district_coverage_pct, message: value.message,
    model_version: value.model_version, forecast_method: medianForecastMethod(value),
    reference_age_months: referenceAgeMonths(value), reference_training_eligible: value.reference_training_eligible,
    reference_is_stale: value.reference_is_stale,
    latest_observation_date: value.latest_observation_date, observation_age_months: value.observation_age_months,
    genuine_observed_months: value.genuine_observed_months, genuine_observation_count: value.genuine_observation_count };
}

/** Retain missing calendar months and never connect a measurement to a forecast. */
export function stateMedianChartRows(value) {
  if (!value?.history?.length && !value?.forecast?.length) return [];
  const observed = new Map(value.history.map(row => [row.date.slice(0, 7), row]));
  const predicted = new Map(value.forecast.map(row => [row.target_date.slice(0, 7), row]));
  const firstObserved = value.history.find(row => depth(row.gwl_m_bgl) && row.is_observed !== false && row.is_imputed !== true && row.is_forecast !== true);
  const first = firstObserved?.date || value.forecast_origin;
  const last = value.forecast.at(-1)?.target_date || value.forecast_origin;
  const [year, month] = first.split('-').map(Number);
  const rows = [];
  for (let i = 0; i < 1200; i++) {
    const key = new Date(Date.UTC(year, month - 1 + i, 1)).toISOString().slice(0, 7);
    if (key > last.slice(0, 7)) break;
    const history = observed.get(key), forecast = predicted.get(key);
    const genuine = history && history.is_observed !== false && history.is_imputed !== true && history.is_forecast !== true;
    rows.push({ month: key, observed: genuine && history.training_eligible ? history.gwl_m_bgl : null,
      lowCoverage: genuine && !history.training_eligible ? history.gwl_m_bgl : null,
      predicted: forecast?.predicted_gwl ?? null, horizon: forecast?.horizon ?? null,
      coverage: history?.district_coverage_pct ?? null, districts: history?.contributing_districts_count ?? null,
      registered: history?.total_districts_in_state ?? null, observations: history?.observation_count ?? null,
      method: medianMethodLabel(value), stateName: value.state_name || value.state_id,
      referenceDate: value.historical_reference_date || null,
      latestObservationDate: value.latest_observation_date || value.historical_reference_date || null,
      referenceCoverage: value.district_coverage_pct ?? null, referenceDistricts: value.contributing_districts_count ?? null,
      referenceRegistered: value.total_districts_in_state ?? null });
  }
  return rows;
}

/** Build dedicated history rows for Recorded History plot across the full valid timeline. */
export function stateRecordedHistoryRows(history = [], stateName = '') {
  if (!Array.isArray(history) || !history.length) return [];
  const byMonth = new Map();
  for (const row of history) {
    const rawDate = row.date || row.month;
    if (!rawDate) continue;
    const month = String(rawDate).slice(0, 7);
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) continue;
    const val = Number.isFinite(row.gwl_m_bgl) ? row.gwl_m_bgl : Number.isFinite(row.gwl) ? row.gwl : null;
    const isObserved = row.is_observed === true && row.is_imputed !== true && row.is_forecast !== true && val !== null;
    const isFilled = (row.is_imputed === true || row.is_forward_filled_display === true) && val !== null;
    const isEligible = isObserved && row.training_eligible === true;
    const isLowCoverage = isObserved && row.training_eligible === false && !isFilled;

    byMonth.set(month, {
      month,
      observed: isEligible ? val : null,
      filled: isFilled ? val : null,
      lowCoverage: isLowCoverage ? val : null,
      is_observed: isObserved,
      is_imputed: isFilled,
      is_forward_filled_display: Boolean(row.is_forward_filled_display),
      training_eligible: Boolean(row.training_eligible),
      districts: row.contributing_districts_count ?? null,
      registered: row.total_districts_in_state ?? null,
      coverage: row.district_coverage_pct ?? null,
      observations: row.observation_count ?? null,
      stateName: stateName || row.stateName || null,
    });
  }

  const months = [...byMonth.keys()].sort();
  if (!months.length) return [];

  const firstDataMonth = months.find(m => {
    const r = byMonth.get(m);
    return r.observed !== null || r.filled !== null || r.lowCoverage !== null;
  });
  if (!firstDataMonth) return [];

  const lastDataMonth = months.at(-1);

  const ordinal = m => Number(m.slice(0, 4)) * 12 + Number(m.slice(5, 7)) - 1;
  const startIdx = ordinal(firstDataMonth);
  const endIdx = ordinal(lastDataMonth);

  const result = [];
  for (let idx = startIdx; idx <= endIdx; idx += 1) {
    const m = `${String(Math.floor(idx / 12)).padStart(4, '0')}-${String((idx % 12) + 1).padStart(2, '0')}`;
    result.push(byMonth.get(m) || {
      month: m,
      observed: null,
      filled: null,
      lowCoverage: null,
      is_observed: false,
      is_imputed: false,
      is_forward_filled_display: false,
      training_eligible: false,
      districts: null,
      registered: null,
      coverage: null,
      observations: null,
      stateName,
    });
  }
  return result;
}

/** Build dedicated forecast rows for 12-Month Groundwater Prediction plot. */
export function state12mPredictionRows(value) {
  if (!value || value.status !== 'forecast' || !Array.isArray(value.forecast)) return [];
  const fallback = medianForecastMethod(value) === 'persistence_fallback';
  return value.forecast.map(row => ({
    month: row.target_date.slice(0, 7),
    target_date: row.target_date,
    horizon: row.horizon,
    predicted: row.predicted_gwl,
    method: medianMethodLabel(value),
    isFallback: fallback,
    referenceDate: value.historical_reference_date || null,
    referenceAge: referenceAgeMonths(value),
    stateName: value.state_name || value.state_id,
  }));
}
