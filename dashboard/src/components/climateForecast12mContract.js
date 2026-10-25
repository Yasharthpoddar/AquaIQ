/** Validate the district XGBoost output and its exact twelve calendar months. */
const realDate = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
  && Number.isFinite(Date.parse(`${value}T00:00:00Z`))
  && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
const depth = value => Number.isFinite(value) && value >= 0;
function nextMonths(asOf) {
  const [year, month] = asOf.split('-').map(Number);
  return Array.from({ length: 12 }, (_, i) => new Date(Date.UTC(year, month + i, 1)).toISOString().slice(0, 7));
}

export function validateClimate12mForecast(value, expectedDistrict = null) {
  const invalid = (reason) => {
    throw new Error(`Invalid 12-month climate forecast: ${reason || 'Incompatible payload'}`);
  };

  if (!value || typeof value !== 'object' || Array.isArray(value)) invalid('Payload must be an object');
  if (typeof value.district_id !== 'string' || !value.district_id) invalid('Missing district_id');
  if (expectedDistrict !== null && value.district_id !== expectedDistrict
    && !(value.requested_id === expectedDistrict && value.resolved_id === value.district_id)) {
    invalid(`District mismatch: expected ${expectedDistrict}, got ${value.district_id}`);
  }
  if (value.product !== 'climate_informed_12m_forecast') {
    invalid(`Expected product climate_informed_12m_forecast, got ${value.product}`);
  }
  const reference = value.model_version === '1.0-reference-12m';
  if (!['1.0-climate-conditioned-12m-xgb', '2.0-climatology-12m-xgb', '1.0-reference-12m'].includes(value.model_version)) {
    invalid(`Expected model_version 1.0-climate-conditioned-12m-xgb or 2.0-climatology-12m-xgb, got ${value.model_version}`);
  }
  if (value.horizon_months !== 12) {
    invalid(`Expected horizon_months 12, got ${value.horizon_months}`);
  }
  if (value.units !== 'm_bgl') {
    invalid(`Expected units m_bgl, got ${value.units}`);
  }
  if (reference) {
    if (!['B', 'C', 'D'].includes(value.evidence_tier) || !Number.isInteger(value.observation_count) || value.observation_count < 0
      || (value.evidence_tier === 'C') !== (value.observation_count === 0)
      || value.projection_method !== (value.evidence_tier === 'C' ? 'regional_seasonal_reference' : 'local_persistence')
      || typeof value.warning !== 'string' || !value.warning.trim()) invalid('Invalid reference evidence or method');
  } else if (value.projection_method !== 'climate_conditioned_xgboost_12m') invalid('Expected the twelve-month XGBoost method');
  if (!['forecast', 'insufficient_data', 'model_unavailable'].includes(value.status)) {
    invalid(`Unexpected status: ${value.status}`);
  }
  if (!realDate(value.as_of)) invalid('Invalid as_of date');
  if (!realDate(value.forecast_origin) || value.forecast_origin > value.as_of
    || value.forecast_origin.slice(0, 7) !== value.as_of.slice(0, 7)) invalid('Invalid forecast_origin');
  if (value.timezone !== 'Asia/Kolkata') invalid('Expected timezone Asia/Kolkata');
  if (!Array.isArray(value.forecast)) invalid('Forecast must be an array');
  if (value.status !== 'forecast') {
    if (value.forecast.length || value.estimated_current_gwl !== null
      || typeof value.message !== 'string' || !value.message.trim()) invalid('Unavailable response must explain its empty forecast');
    return value;
  }

  if (value.status === 'forecast') {
    if (!Array.isArray(value.forecast) || value.forecast.length !== 12) {
      invalid(`Forecast array must contain exactly 12 items, found ${value.forecast?.length}`);
    }
    if (!Number.isFinite(value.estimated_current_gwl) || value.estimated_current_gwl < 0) {
      invalid(`estimated_current_gwl must be a nonnegative finite number`);
    }
    if (value.estimate_type !== undefined && !['district_level', 'zone_fallback', 'regional_reference'].includes(value.estimate_type)) invalid('Missing evidence scope');
    if (value.estimate_type === 'zone_fallback' && (value.source_zone == null || String(value.source_zone).trim() === ''
      || typeof value.zone_fallback_reason !== 'string' || !value.zone_fallback_reason.trim())) invalid('Missing zone fallback provenance');
    const months = nextMonths(value.as_of);

    value.forecast.forEach((row, i) => {
      const expectedHorizon = i + 1;
      if (!row || typeof row !== 'object') invalid(`Forecast item ${i} is not an object`);
      if (row.horizon !== expectedHorizon) {
        invalid(`Forecast item ${i} horizon mismatch: expected ${expectedHorizon}, got ${row.horizon}`);
      }
      if (row.month !== months[i] || row.date !== `${months[i]}-01`) {
        invalid(`Forecast item ${i} month/date mismatch`);
      }
      if (!Number.isFinite(row.predicted_gwl) || row.predicted_gwl < 0) {
        invalid(`Forecast item ${i} has invalid predicted_gwl: ${row.predicted_gwl}`);
      }
      if (!Number.isFinite(row.delta_from_current_m)
        || Math.abs(row.delta_from_current_m - (row.predicted_gwl - value.estimated_current_gwl)) > .001) invalid(`Forecast item ${i} has invalid delta_from_current_m`);
      const weather = row.weather;
      if (!weather || typeof weather !== 'object') {
        invalid(`Forecast item ${i} missing weather object`);
      }
      for (const field of ['rainfall_mm', 'temperature_c', 'evapotranspiration_mm']) {
        if (reference ? weather[field] !== null : !Number.isFinite(weather[field])) {
          invalid(`Forecast item ${i} weather ${field} is not finite`);
        }
      }
      if (row.lower_gwl !== undefined && (!depth(row.lower_gwl) || !depth(row.upper_gwl)
        || row.lower_gwl > row.predicted_gwl || row.upper_gwl < row.predicted_gwl)) invalid('Invalid prediction range');
      if (weather.rainfall_mm < 0 || weather.evapotranspiration_mm < 0) invalid(`Forecast item ${i} has negative rainfall or evapotranspiration`);
      // Preserve validation of optional scientific references even though the product does not render them.
      if (row.baselines !== undefined) {
        const baseline = row.baselines;
        if (!baseline || typeof baseline !== 'object') invalid(`Forecast item ${i} invalid baselines`);
        for (const field of ['persistence', 'seasonal']) {
          if (baseline[field] !== null && !depth(baseline[field])) invalid(`Forecast item ${i} invalid ${field} baseline`);
        }
        if (baseline.persistence !== null && Math.abs(baseline.persistence - value.estimated_current_gwl) > .001) invalid(`Forecast item ${i} persistence anchor mismatch`);
        const previousYear = `${Number(months[i].slice(0, 4)) - 1}${months[i].slice(4)}-01`;
        if (baseline.seasonal === null ? baseline.seasonal_reference_date !== null
          : (!realDate(baseline.seasonal_reference_date) || baseline.seasonal_reference_date !== previousYear
            || baseline.seasonal_reference_date > value.as_of)) invalid(`Forecast item ${i} invalid seasonal reference date`);
      }
    });

    if (value.forecast_start !== months[0] || value.forecast_end !== months[11]) {
      invalid(`Start/End mismatch: start=${value.forecast_start}, end=${value.forecast_end}`);
    }
  }

  return value;
}

export function climate12mChartRows(value) {
  if (value?.status !== 'forecast' || !Array.isArray(value.forecast)) return [];
  return value.forecast.map(row => ({
    month: row.month,
    date: row.date,
    horizon: row.horizon,
    predicted: row.predicted_gwl,
    delta: row.delta_from_current_m,
    rainfall: row.weather?.rainfall_mm,
    temperature: row.weather?.temperature_c,
    evapotranspiration: row.weather?.evapotranspiration_mm,
    lower: row.lower_gwl,
    upper: row.upper_gwl,
    method: value.forecast_method || value.projection_method,
    evidenceTier: value.evidence_tier,
  }));
}
