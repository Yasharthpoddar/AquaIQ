import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import { fetchExperimentalScenario } from '../api.js';
import { scenarioChartRows, validateExperimentalScenario } from './experimentalScenarioContract.js';

const formatMonth = value => {
  const [year, month] = value.split('-').map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString('en', { month: 'short', year: 'numeric' });
};

export function scenarioPlot(value, dimensions = {}) {
  return <LineChart {...dimensions} data={scenarioChartRows(value)} margin={{top:15,right:25,bottom:15,left:15}}>
    <CartesianGrid strokeDasharray="3 3" />
    <XAxis dataKey="month" tickFormatter={formatMonth} minTickGap={20} />
    <YAxis label={{value:'Depth (m below ground)',angle:-90,position:'insideLeft'}} />
    <Tooltip labelFormatter={formatMonth} formatter={depth => [`${Number(depth).toFixed(2)} m`, 'Experimental scenario']} /><Legend />
    <Line dataKey="projected" name="Experimental scenario" stroke="#ef4444" strokeWidth={2} dot={{r:5}} isAnimationActive={false} />
  </LineChart>;
}

export function ScenarioView({ value = null, loading = false, error = null, onRetry = () => {} }) {
  const districtName = value?.source?.district_name;
  const stateName = value?.source?.state_name;
  return <div id="forecast-graph" tabIndex={-1} className="card" style={{padding:'1.25rem',margin:'1.5rem 0',scrollMarginTop:'80px'}}>
    <h2>Next 12 months from today — experimental scenario</h2>
    <p style={{color:'#b45309'}}><strong>Unvalidated projection.</strong> These are assumption-based depth estimates, not current measurements or a validated real-time forecast.</p>
    <p>This scenario is available for registered districts with sufficient own source-marked observed history. Registry coverage does not establish observation coverage or nationwide forecasting accuracy.</p>
    {loading && <p role="status">Calculating the next twelve calendar months from local history…</p>}
    {error && <div role="alert"><p>{error}</p><button type="button" onClick={onRetry}>Retry scenario</button></div>}
    {value && <>
      <p><strong>Selected district:</strong> {districtName ? `${districtName}${stateName ? `, ${stateName}` : ''} (${value.district_id})` : value.district_id}.</p>
      <p><strong>Scenario date:</strong> {value.as_of} (Asia/Kolkata). The horizon begins with the next full calendar month.</p>
      {value.status === 'scenario' && <>
        <p><strong>Source:</strong> {value.source.name}. Only this district’s own observed history is used; imputed rows and other districts are excluded.</p>
        <p><strong>Unit and datum qualification:</strong> {value.source.units_qualification}</p>
        <p><strong>Monthly outlook:</strong> {formatMonth(value.forecast_start)}–{formatMonth(value.forecast_end)}.</p>
        <p><strong>Latest source-marked observation:</strong> {value.source.last_observed_month}, {value.source.last_observed_gwl.toFixed(2)} m below ground — {value.source.data_age_months} calendar months before the scenario month. <strong>Estimated depth for the scenario month:</strong> {value.estimated_current_gwl.toFixed(2)} m below ground.</p>
        <p>The graph shows depth in metres below ground. Rising values mean deeper groundwater and a lower water level; falling values mean shallower groundwater. The gap to today is estimated from historical trend and seasonality.</p>
        <ResponsiveContainer width="100%" height={380}>
          {scenarioPlot(value)}
        </ResponsiveContainer>
        <details><summary>View all 12 monthly estimates</summary>
          <table style={{width:'100%',textAlign:'left'}}><caption>Experimental depth estimates, not observed measurements</caption>
            <thead><tr><th scope="col">Month</th><th scope="col">Depth (m below ground)</th></tr></thead>
            <tbody>{value.forecast.map(row => <tr key={row.month}><th scope="row">{formatMonth(row.month)}</th><td>{row.projected_gwl.toFixed(2)}</td></tr>)}</tbody>
          </table>
        </details>
        <p>In-memory seasonal/trend fit: {value.method.observed_month_count} source-marked observed months, {value.method.history_start}–{value.method.history_end}; {value.method.annual_seasonality ? 'annual seasonality assumed' : 'seasonality not estimable; damped trend only'}. Contributing calendar months: {value.method.observed_calendar_months.join(', ')}.</p>
        {value.method.unobserved_calendar_months?.length > 0 && <p style={{color:'#b45309'}}>Calendar phases without observed history: {value.method.unobserved_calendar_months.join(', ')}. Their scenario values rely on the assumed seasonal/trend function; they are not monthly measurements.</p>}
        <p>Latest contributing well count: {value.source.well_count ?? 'unknown'}. Well identities, panel continuity and datum continuity are unverified. First availability and actual acquisition times remain unknown.</p>
      </>}
      {value.unavailable_reasons.map(reason => <p key={reason} role="status">{reason}</p>)}
      {value.status === 'unavailable' && <div style={{minHeight:'180px',display:'grid',alignContent:'center'}} role="status"><p>No scenario values are available for this district. No other district, historical origin or model has been substituted.</p></div>}
      <p>This seasonal/trend scenario does not use future weather or extraction inputs and is not a climate model.</p>
      <p><strong>Assumptions</strong></p>{value.assumptions.map(item => <p key={item}>{item}</p>)}
      <details><summary>Scenario provenance and limitations</summary>
        <p>Calculated: {value.computed_at}. No prospective validation record has been issued.</p>
        <p style={{overflowWrap:'anywhere'}}>Source snapshot SHA-256: {value.source.source_snapshot_sha256 || 'unavailable'}<br />Method SHA-256: {value.method.method_sha256 || 'unavailable'}<br />Configuration SHA-256: {value.method.configuration_sha256 || 'unavailable'}</p>
        {value.limitations.map(item => <p key={item}>{item}</p>)}
      </details>
    </>}
  </div>;
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
  return <ScenarioView value={value} loading={loading} error={error} onRetry={() => setRetry(count => count + 1)} />;
}
