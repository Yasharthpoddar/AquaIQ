import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import { fetchClimate12mForecast } from '../api.js';
import { climate12mChartRows, validateClimate12mForecast } from './climateForecast12mContract.js';

const formatMonth = value => {
  if (!value || typeof value !== 'string') return '';
  const [year, month] = value.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, 1)).toLocaleDateString('en', { month: 'short', year: 'numeric', timeZone: 'UTC' });
};

const formatDepth = value => Number.isFinite(value) ? `${value.toFixed(2)} m` : 'Unavailable';

export function Forecast12mTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const month = formatMonth(row.month);
  const depth = formatDepth(row.predicted);
  const delta = row.delta != null ? `${row.delta >= 0 ? '+' : ''}${row.delta.toFixed(2)} m` : null;
  return (
    <div role="tooltip" className="forecast-tooltip" style={{ background: '#fff', border: '1px solid #cbd5e1', borderRadius: 8, padding: '0.65rem 0.85rem', boxShadow: '0 4px 12px rgba(15,23,42,0.12)', fontSize: '0.82rem', lineHeight: 1.45 }}>
      <strong>{month} (M+{row.horizon})</strong>
      <div style={{ color: '#2563eb', fontWeight: 600, marginTop: '0.25rem' }}>
        Depth: {depth}
      </div>
      {delta && <div style={{ color: '#64748b', fontSize: '0.78rem' }}>Change from current: {delta}</div>}
      <div style={{ marginTop: '0.35rem', paddingTop: '0.35rem', borderTop: '1px solid #f1f5f9', color: '#475569', fontSize: '0.75rem' }}>
        <div>Rainfall: {Number.isFinite(row.rainfall) ? `${row.rainfall.toFixed(1)} mm` : '—'}</div>
        <div>Temp: {Number.isFinite(row.temperature) ? `${row.temperature.toFixed(1)} °C` : '—'}</div>
        <div>ET: {Number.isFinite(row.evapotranspiration) ? `${row.evapotranspiration.toFixed(1)} mm` : '—'}</div>
      </div>
    </div>
  );
}

export function forecast12mPlot(value, dimensions = {}) {
  const rows = climate12mChartRows(value);
  return (
    <LineChart {...dimensions} data={rows} margin={{ top: 16, right: 20, bottom: 8, left: 0 }} accessibilityLayer>
      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
      <XAxis dataKey="month" tickFormatter={formatMonth} minTickGap={26} tickLine={false} />
      <YAxis width={54} tickLine={false} axisLine={false} />
      <Tooltip content={<Forecast12mTooltip />} />
      <Legend />
      <Line
        dataKey="predicted"
        name="12-month climate forecast"
        stroke="#2563eb"
        strokeWidth={2.5}
        dot={{ r: 3, fill: '#fff', strokeWidth: 2 }}
        activeDot={{ r: 5 }}
        isAnimationActive={false}
        connectNulls={false}
      />
    </LineChart>
  );
}

export function ClimateForecast12mView({ value = null, loading = false, error = null, onRetry = () => {} }) {
  const rows = climate12mChartRows(value);
  const weatherBasis = value?.weather_basis || {};
  const isForecast = value?.status === 'forecast';

  return (
    <section id="forecast-graph" tabIndex={-1} className="card forecast-card" aria-label="Next twelve months climate-informed groundwater forecast">
      <header className="section-heading">
        <div>
          <h2>Next 12 months</h2>
          <p className="muted">Groundwater depth · metres below ground · climate-conditioned XGBoost</p>
        </div>
        <span className="experimental-badge">Experimental forecast</span>
      </header>
      <p className="forecast-note">
        Experimental climate-conditioned XGBoost forecast conditioned on rainfall, temperature and evapotranspiration; not a validated operational prediction.
      </p>

      {loading && (
        <div role="status" className="forecast-placeholder">
          <span className="loading-spinner" />Loading this district’s 12-month climate forecast…
        </div>
      )}

      {error && (
        <div className="inline-state error-state" role="alert">
          <p>{error}</p>
          <button className="button button-secondary" type="button" onClick={onRetry}>Retry forecast</button>
        </div>
      )}

      {value && !loading && !error && (
        <>
          <div className="forecast-context">
            <span>District: {value.district_id}</span>
            <span>As of {value.as_of} · {value.timezone || 'Asia/Kolkata'}</span>
          </div>

          {isForecast && (
            <>
              <div className="forecast-facts">
                <div>
                  <span>Latest source-marked observation</span>
                  <strong>{formatMonth(value.last_observed_date?.slice(0, 7))} · {formatDepth(value.last_observed_gwl)}</strong>
                  <small>{value.data_age_months != null ? `${value.data_age_months} calendar months before forecast origin` : 'Observation date recorded'}</small>
                </div>
                <div>
                  <span>Estimated current depth</span>
                  <strong>{formatDepth(value.estimated_current_gwl)}</strong>
                  <small>{value.current_depth_basis === 'observed_month' ? 'Observed in the current month' : 'Estimated from trend and seasonality across observation gap'}</small>
                </div>
              </div>

              <div className="chart-caption">
                <span>{formatMonth(value.forecast_start)}–{formatMonth(value.forecast_end)}</span>
                <span>Higher depth = lower water level</span>
              </div>

              <div className="forecast-chart">
                <ResponsiveContainer width="100%" height={300}>
                  {forecast12mPlot(value)}
                </ResponsiveContainer>
              </div>

              <details className="monthly-values">
                <summary>View all 12 monthly predictions &amp; climate inputs</summary>
                <div className="table-scroll">
                  <table className="data-table">
                    <caption>12-month climate-conditioned predictions and explicit weather inputs</caption>
                    <thead>
                      <tr>
                        <th scope="col">Month</th>
                        <th scope="col">Horizon</th>
                        <th scope="col">Predicted depth (m bgl)</th>
                        <th scope="col">Change (m)</th>
                        <th scope="col">Rainfall (mm)</th>
                        <th scope="col">Temp (°C)</th>
                        <th scope="col">ET (mm)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map(row => (
                        <tr key={row.month}>
                          <th scope="row">{formatMonth(row.month)}</th>
                          <td>M+{row.horizon}</td>
                          <td>{Number.isFinite(row.predicted) ? row.predicted.toFixed(2) : '—'}</td>
                          <td>{row.delta != null ? `${row.delta >= 0 ? '+' : ''}${row.delta.toFixed(2)}` : '—'}</td>
                          <td>{Number.isFinite(row.rainfall) ? row.rainfall.toFixed(1) : '—'}</td>
                          <td>{Number.isFinite(row.temperature) ? row.temperature.toFixed(1) : '—'}</td>
                          <td>{Number.isFinite(row.evapotranspiration) ? row.evapotranspiration.toFixed(1) : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </>
          )}

          {value.status === 'insufficient_data' && (
            <div className="inline-state" role="status">
              <h3>12-month forecast unavailable</h3>
              <p>{value.message || 'Not enough historical observations or weather history to produce a 12-month forecast.'}</p>
            </div>
          )}

          {value.status === 'model_unavailable' && (
            <div className="inline-state" role="status">
              <h3>Model artifact unavailable</h3>
              <p>{value.message || '12-month climate model checkpoint is unavailable.'}</p>
            </div>
          )}

          <details className="technical-details">
            <summary>Model &amp; climate provenance details</summary>
            <p><strong>Model:</strong> {value.model_version} ({value.product})</p>
            <p><strong>Projection method:</strong> {value.projection_method}</p>
            {value.model_sha256 && <p><strong>Model SHA-256:</strong> <code>{value.model_sha256}</code></p>}
            {value.model_train_target_cutoff && <p><strong>Training cutoff:</strong> {value.model_train_target_cutoff}</p>}
            <p><strong>Weather input policy:</strong> {weatherBasis.description || 'Historical same-month climatology available at forecast origin.'}</p>
            {weatherBasis.latest_usable_weather_date && (
              <p><strong>Latest usable historical weather date:</strong> {weatherBasis.latest_usable_weather_date}</p>
            )}
            <p><strong>Evaluation status:</strong> Holdout testing with a 12-month embargo demonstrates that persistence and seasonal-naive baselines match or outperform XGBoost at multiple horizons. This model is published as an experimental research artifact and is not approved for operational water management decisions.</p>
            {Array.isArray(value.limitations) && value.limitations.length > 0 && (
              <>
                <h3>Limitations</h3>
                <ul>
                  {value.limitations.map((lim, i) => <li key={i}>{lim}</li>)}
                </ul>
              </>
            )}
          </details>
        </>
      )}
    </section>
  );
}

export function ClimateForecast12m({ districtId }) {
  const [value, setValue] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retry, setRetry] = useState(0);
  const location = useLocation();

  useEffect(() => {
    let cancelled = false;
    setValue(null);
    setLoading(true);
    setError(null);
    fetchClimate12mForecast(districtId)
      .then(result => validateClimate12mForecast(result, districtId))
      .then(result => {
        if (!cancelled) {
          setValue(result);
          setLoading(false);
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err.message || '12-month forecast unavailable.');
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [districtId, retry]);

  useEffect(() => {
    if (location.hash === '#forecast-graph') {
      const graph = document.getElementById('forecast-graph');
      graph?.focus({ preventScroll: true });
      graph?.scrollIntoView({ block: 'start' });
    }
  }, [location.hash, districtId]);

  return (
    <ClimateForecast12mView
      value={value}
      loading={loading}
      error={error}
      onRetry={() => setRetry(count => count + 1)}
    />
  );
}

export default function DistrictForecastGraph({ districtId }) {
  return <ClimateForecast12m key={districtId} districtId={districtId} />;
}
