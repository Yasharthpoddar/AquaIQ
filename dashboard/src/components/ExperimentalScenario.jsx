import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import { fetchExperimentalScenario } from '../api.js';
import { scenarioChartRows, validateExperimentalScenario } from './experimentalScenarioContract.js';
import ClimateInputs from './ClimateInputs.jsx';

const formatMonth = value => {
  const [year, month] = value.split('-').map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString('en', { month: 'short', year: 'numeric' });
};
const formatDepth = value => Number.isFinite(value) ? `${value.toFixed(2)} m` : 'Unavailable';

export function scenarioPlot(value, dimensions = {}) {
  return <LineChart {...dimensions} data={scenarioChartRows(value)} margin={{top:16,right:20,bottom:8,left:0}} accessibilityLayer>
    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
    <XAxis dataKey="month" tickFormatter={formatMonth} minTickGap={26} tickLine={false} />
    <YAxis width={54} tickLine={false} axisLine={false} />
    <Tooltip labelFormatter={formatMonth} formatter={depth => [formatDepth(depth), 'Experimental estimate']} /><Legend />
    <Line dataKey="projected" name="Experimental estimate" stroke="#2563eb" strokeWidth={2.5} dot={{r:3}} activeDot={{r:5}} isAnimationActive={false} connectNulls={false} />
  </LineChart>;
}

export function ScenarioView({ value = null, loading = false, error = null, onRetry = () => {} }) {
  const rows = scenarioChartRows(value);
  const source = value?.source || {};
  const method = value?.method || {};
  return <section id="forecast-graph" tabIndex={-1} className="card forecast-card" aria-label="Next twelve months groundwater estimates">
    <header className="section-heading"><div><h2>Next 12 months</h2><p className="muted">Groundwater depth · metres below ground</p></div><span className="experimental-badge">Experimental estimate</span></header>
    <p className="forecast-note">Unvalidated seasonal/trend scenario, not current measurements or a validated real-time forecast.</p>
    {loading && <div role="status" className="forecast-placeholder"><span className="loading-spinner" />Loading this district’s monthly estimates…</div>}
    {error && <div className="inline-state error-state" role="alert"><p>{error}</p><button className="button button-secondary" type="button" onClick={onRetry}>Retry scenario</button></div>}
    {value && <>
      <div className="forecast-context"><span>{source.district_name ? `${source.district_name}${source.state_name ? `, ${source.state_name}` : ''} (${value.district_id})` : value.district_id}</span><span>As of {value.as_of} · Asia/Kolkata</span></div>
      {value.status === 'scenario' && <>
        <div className="forecast-facts"><div><span>Latest source-marked observation</span><strong>{formatMonth(source.last_observed_month)} · {formatDepth(source.last_observed_gwl)}</strong><small>{source.data_age_months} calendar months before the scenario month</small></div><div><span>Estimated current depth</span><strong>{formatDepth(value.estimated_current_gwl)}</strong><small>The observation gap is estimated from trend and seasonality.</small></div></div>
        <div className="chart-caption"><span>{formatMonth(value.forecast_start)}–{formatMonth(value.forecast_end)}</span><span>Higher depth = lower water level</span></div>
        <div className="forecast-chart"><ResponsiveContainer width="100%" height={300}>{scenarioPlot(value)}</ResponsiveContainer></div>
        <details className="monthly-values"><summary>View all 12 monthly values</summary>
          <div className="table-scroll"><table className="data-table"><caption>Experimental depth estimates, not observed measurements</caption>
            <thead><tr><th scope="col">Month</th><th scope="col">Depth (m below ground)</th></tr></thead>
            <tbody>{rows.map(row => <tr key={row.month}><th scope="row">{formatMonth(row.month)}</th><td>{row.projected.toFixed(2)}</td></tr>)}</tbody>
          </table></div>
        </details>
      </>}
      {value.status === 'unavailable' && <div className="inline-state" role="status"><h3>Monthly estimates unavailable</h3><p>No other district, historical origin or model has been substituted.</p></div>}
      {value.unavailable_reasons.map(reason => <p key={reason} className="availability-reason" role="status">{reason}</p>)}
      <details className="technical-details"><summary>Details</summary>
        <p><strong>Source:</strong> {source.name || 'Unavailable'}. Only this district’s own observed history is used; imputed rows and other districts are excluded.</p>
        {source.units_qualification && <p><strong>Unit and datum qualification:</strong> {source.units_qualification}</p>}
        {value.status === 'scenario' && <>
          <p>In-memory seasonal/trend fit: {method.observed_month_count} source-marked observed months, {method.history_start}–{method.history_end}; {method.annual_seasonality ? 'annual seasonality assumed' : 'damped trend only'}. Contributing calendar months: {method.observed_calendar_months.join(', ')}.</p>
          {method.unobserved_calendar_months?.length > 0 && <p>Calendar phases without observed history: {method.unobserved_calendar_months.join(', ')}. Their scenario values rely on the assumed function; they are not monthly measurements.</p>}
          <p>Latest contributing well count: {source.well_count ?? 'unknown'}. Well identities, panel continuity and datum continuity are unverified. First availability and actual acquisition times remain unknown.</p>
        </>}
        <p>This scenario excludes future weather and extraction inputs and is not a climate model. Registry coverage does not establish observation coverage or nationwide forecasting accuracy.</p>
        <h3>Assumptions</h3><ul>{value.assumptions.map(item => <li key={item}>{item}</li>)}</ul>
        <h3>Provenance</h3>
        <p>Calculated: {value.computed_at}. No prospective validation record has been issued.</p>
        <p className="hash-details">Source snapshot SHA-256: {source.source_snapshot_sha256 || 'unavailable'}<br />Method SHA-256: {method.method_sha256 || 'unavailable'}<br />Configuration SHA-256: {method.configuration_sha256 || 'unavailable'}</p>
        <ul>{value.limitations.map(item => <li key={item}>{item}</li>)}</ul>
      </details>
    </>}
  </section>;
}

export default function ExperimentalScenario({ districtId }) {
  const [value, setValue] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retry, setRetry] = useState(0);
  const location = useLocation();
  useEffect(() => {
    let cancelled = false;
    setValue(null); setLoading(true); setError(null);
    fetchExperimentalScenario(districtId).then(result => validateExperimentalScenario(result, districtId)).then(result => {
      if (!cancelled) { setValue(result); setLoading(false); }
    }).catch(err => { if (!cancelled) { setError(err.message || 'Scenario unavailable.'); setLoading(false); } });
    return () => { cancelled = true; };
  }, [districtId, retry]);
  useEffect(() => {
    if (location.hash === '#forecast-graph') {
      const graph = document.getElementById('forecast-graph');
      graph?.focus({preventScroll:true}); graph?.scrollIntoView({block:'start'});
    }
  }, [location.hash, districtId]);
  return <><ScenarioView value={value} loading={loading} error={error} onRetry={() => setRetry(count => count + 1)} />
    {value && <ClimateInputs key={`${districtId}:${value.as_of}`} districtId={districtId} asOf={value.as_of} />}
  </>;
}
