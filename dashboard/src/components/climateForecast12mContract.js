/**
 * Client-side validation contract for the climate-informed 12-month XGBoost forecast.
 */

export function validateClimate12mForecast(value, expectedDistrict = null) {
  const invalid = (reason) => {
    throw new Error(`Invalid 12-month climate forecast: ${reason || 'Incompatible payload'}`);
  };

  if (!value || typeof value !== 'object') invalid('Payload must be an object');
  if (typeof value.district_id !== 'string' || !value.district_id) invalid('Missing district_id');
  if (expectedDistrict !== null && value.district_id !== expectedDistrict && value.resolved_id !== expectedDistrict) {
    invalid(`District mismatch: expected ${expectedDistrict}, got ${value.district_id}`);
  }
  if (value.product !== 'climate_informed_12m_forecast') {
    invalid(`Expected product climate_informed_12m_forecast, got ${value.product}`);
  }
  if (value.model_version !== '1.0-climate-conditioned-12m-xgb') {
    invalid(`Expected model_version 1.0-climate-conditioned-12m-xgb, got ${value.model_version}`);
  }
  if (value.horizon_months !== 12) {
    invalid(`Expected horizon_months 12, got ${value.horizon_months}`);
  }
  if (value.units !== 'm_bgl') {
    invalid(`Expected units m_bgl, got ${value.units}`);
  }
  if (!['forecast', 'insufficient_data', 'model_unavailable'].includes(value.status)) {
    invalid(`Unexpected status: ${value.status}`);
  }

  if (value.status === 'forecast') {
    if (!Array.isArray(value.forecast) || value.forecast.length !== 12) {
      invalid(`Forecast array must contain exactly 12 items, found ${value.forecast?.length}`);
    }
    if (!Number.isFinite(value.estimated_current_gwl) || value.estimated_current_gwl < 0) {
      invalid(`estimated_current_gwl must be a nonnegative finite number`);
    }

    value.forecast.forEach((row, i) => {
      const expectedHorizon = i + 1;
      if (!row || typeof row !== 'object') invalid(`Forecast item ${i} is not an object`);
      if (row.horizon !== expectedHorizon) {
        invalid(`Forecast item ${i} horizon mismatch: expected ${expectedHorizon}, got ${row.horizon}`);
      }
      if (!/^\d{4}-\d{2}$/.test(row.month || '')) {
        invalid(`Forecast item ${i} has invalid month: ${row.month}`);
      }
      if (!Number.isFinite(row.predicted_gwl) || row.predicted_gwl < 0) {
        invalid(`Forecast item ${i} has invalid predicted_gwl: ${row.predicted_gwl}`);
      }
      const weather = row.weather;
      if (!weather || typeof weather !== 'object') {
        invalid(`Forecast item ${i} missing weather object`);
      }
      for (const field of ['rainfall_mm', 'temperature_c', 'evapotranspiration_mm']) {
        if (!Number.isFinite(weather[field])) {
          invalid(`Forecast item ${i} weather ${field} is not finite`);
        }
      }
    });

    if (value.forecast_start !== value.forecast[0].month || value.forecast_end !== value.forecast[11].month) {
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
  }));
}
