import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import { fetchDistrict, fetchHistory, fetchPredict } from '../api';

const COLORS = { Safe:'#22c55e', Watch:'#eab308', Warning:'#f97316', Crisis:'#ef4444' };

function validateMonthlyProjection(result) {
  const unsupported = () => { throw new Error('A six-month prediction with rainfall and weather inputs is currently unavailable. Please retry.'); };
  if (!result || !Array.isArray(result.forecast)) unsupported();
  if (result.status === 'insufficient_data' && result.forecast.length === 0) return result;
  if (result.status !== 'projection' || result.projection_method !== 'climate_conditioned_xgboost_monthly' || result.forecast.length !== 6 || !/^\d{4}-\d{2}-\d{2}$/.test(result.as_of || '')) unsupported();
  const asOf = new Date(`${result.as_of}T00:00:00Z`);
  if (!Number.isFinite(asOf.getTime()) || asOf.toISOString().slice(0,10) !== result.as_of) unsupported();
  const valid = result.forecast.every((row, index) => {
    const expectedMonth = new Date(Date.UTC(asOf.getUTCFullYear(), asOf.getUTCMonth() + index + 1, 1)).toISOString().slice(0,7);
    const weather = row?.weather;
    return row?.month === expectedMonth && Number.isFinite(row.predicted_gwl)
      && Number.isFinite(weather?.rainfall_mm) && weather.rainfall_mm >= 0
      && Number.isFinite(weather?.temperature_c)
      && Number.isFinite(weather?.evapotranspiration_mm) && weather.evapotranspiration_mm >= 0;
  });
  if (!valid) unsupported();
  return result;
}

export default function DistrictDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [districtRetry, setDistrictRetry] = useState(0);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState(null);
  const [historyRetry, setHistoryRetry] = useState(0);
  const [projection, setProjection] = useState(null);
  const [projectionLoading, setProjectionLoading] = useState(true);
  const [projectionError, setProjectionError] = useState(null);
  const [projectionRetry, setProjectionRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null); setData(null);
    fetchDistrict(id)
      .then(district => {
        // The district endpoint already includes its score, model endpoint and metadata.
        if (!cancelled) { setData(district); setLoading(false); }
      }).catch(err => { if (!cancelled) { setError(err.message || 'District data is unavailable.'); setLoading(false); } });
    return () => { cancelled = true; };
  }, [id, districtRetry]);
  useEffect(() => {
    let cancelled = false;
    setHistory([]); setHistoryError(null); setHistoryLoading(true);
    fetchHistory(id, '2002-01', new Date().toISOString().slice(0,7))
      .then(result => { if (!cancelled) { setHistory(result.data || []); setHistoryLoading(false); } })
      .catch(err => { if (!cancelled) { setHistoryError(err.message || 'Groundwater history is unavailable.'); setHistoryLoading(false); } });
    return () => { cancelled = true; };
  }, [id, historyRetry]);
  useEffect(() => {
    let cancelled = false;
    setProjection(null); setProjectionError(null); setProjectionLoading(true);
    fetchPredict(id, { window:'next_six_months' })
      .then(validateMonthlyProjection)
      .then(result => { if (!cancelled) { setProjection(result); setProjectionLoading(false); } })
      .catch(err => { if (!cancelled) { setProjectionError(err.message || 'The monthly prediction is unavailable.'); setProjectionLoading(false); } });
    return () => { cancelled = true; };
  }, [id, projectionRetry]);
  if (loading) return <div className="page"><Link to="/" className="back-link">← Back to dashboard</Link><div className="loading-container"><div className="loading-spinner" />Loading groundwater evidence…</div></div>;
  if (error) return <div className="page"><Link to="/" className="back-link">← Back to dashboard</Link><div className="empty-state" role="alert"><p>{error}</p><button type="button" onClick={() => setDistrictRetry(value => value + 1)}>Retry district</button></div></div>;
  const district = data;
  const prediction = district;
  const score = prediction.crisis_score;
  const available = Number.isFinite(score);
  const color = COLORS[prediction.tier] || '#64748b';
  const historyChart = history.filter(row => row.gwl != null && Number.isFinite(row.gwl)).map(row => ({
    month:row.month, observed:row.is_observed ? row.gwl : null, filled:row.is_imputed ? row.gwl : null,
  })).sort((a,b) => a.month.localeCompare(b.month));
  const projectionChart = (projection?.forecast || []).map(row => ({
    month:row.month, predicted:Number.isFinite(row.predicted_gwl) ? row.predicted_gwl : null,
  })).sort((a,b) => a.month.localeCompare(b.month));
  const projectionAvailable = projectionChart.some(row => row.predicted != null);
  const formatMonth = month => {
    const [year, number] = String(month).slice(0,7).split('-').map(Number);
    return new Date(year, number - 1, 1).toLocaleDateString('en', {month:'short', year:'numeric'});
  };
  const isZone = prediction.estimate_type === 'zone_fallback';
  const historical = prediction.status === 'historical_forecast';
  const scoreTargetMonth = prediction.forecast?.[0]?.month;
  const depthGuide = 'The graph shows depth in metres below ground. A rising line means deeper groundwater and a lower water level; a falling line means shallower groundwater and a higher water level.';
  return <div className="page">
    <Link to="/" className="back-link">← Back to dashboard</Link>
    <h1>{district.metadata?.name || id}, {district.metadata?.state || ''}</h1>
    <p className="subtitle">{isZone ? `Estimate from the ${prediction.source_zone} zone` : 'District groundwater evidence'}</p>
    <div className={`score-badge ${prediction.tier === 'Crisis' ? 'crisis' : ''}`}>
      <div className="score-value" style={{color}}>{available ? score : 'Unavailable'}</div>
      <div className="score-label">{historical ? 'Historical crisis score (0–100)' : 'AquaIQ Crisis Score (0–100)'}</div>
      <div className="score-tier" style={{color}}>{available ? `${prediction.tier} Tier` : 'Insufficient evidence for this model'}</div>
      <p><strong>Observation used:</strong> {prediction.last_observed_date || 'Unavailable'}{prediction.data_age_months != null ? ` (${prediction.data_age_months} months old)` : ''}{isZone ? ' (zone evidence)' : ''}{scoreTargetMonth && <> · <strong>Score model target:</strong> {scoreTargetMonth}</>}</p>
    </div>
    <p>The crisis score combines groundwater depth, changes in depth, and rainfall and drought conditions. The direction of the plotted line alone does not determine the score.</p>
    {prediction.weights_status === 'initial_uncalibrated' && <p role="status">This project score uses initial component weights that have not been calibrated against independent crisis outcomes. It is not an accuracy or confidence percentage.</p>}
    {historical && <p style={{color:'#b45309'}}>This score describes the historical observation period. The next-six-month projection below does not update this historical score.</p>}
    {prediction.zone_fallback_reason && <p>{prediction.zone_fallback_reason}</p>}
    {prediction.message && <p role="status">{prediction.message}</p>}
    <div className="card" style={{padding:'1.25rem',margin:'1.5rem 0'}}>
      <h2>Prediction for the next six months</h2>
      {projectionLoading && <p role="status">Calculating monthly predictions from today…</p>}
      {projectionError && <div role="alert"><p>{projectionError}</p><button type="button" onClick={() => setProjectionRetry(value => value + 1)}>Retry prediction</button></div>}
      {projection && <>
        <p><strong>As of:</strong> {projection.as_of || projection.forecast_origin}. The graph starts with the next full calendar month.</p>
        {projectionAvailable && <>
          <p><strong>Rainfall and weather are model inputs.</strong> Monthly XGBoost predictions use rainfall, temperature, and evapotranspiration alongside estimated groundwater depth.</p>
          <p><strong>Weather assumptions:</strong> historical averages for each calendar month; no live weather forecast is used.</p>
          {projection.weather_basis?.latest_historical_weather_dates && <p><strong>Usable weather history through:</strong> {[
            ['rainfall', 'Rainfall'], ['temperature', 'Temperature'], ['evapotranspiration', 'Evapotranspiration'],
          ].map(([field, label]) => `${label}: ${projection.weather_basis.latest_historical_weather_dates[field] ? formatMonth(projection.weather_basis.latest_historical_weather_dates[field]) : 'Unavailable'}`).join(' · ')}.</p>}
          {projection.weather_basis?.weather_history_may_include_filled_values && <p>Usable weather history may include limited filled values. Its end dates do not establish the date of fresh measurements.</p>}
          <p>{depthGuide}</p>
          <ResponsiveContainer width="100%" height={380}>
            <LineChart data={projectionChart} margin={{top:15,right:25,bottom:15,left:15}}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" tickFormatter={formatMonth} minTickGap={20} />
              <YAxis label={{value:'Depth (m below ground)',angle:-90,position:'insideLeft'}} />
              <Tooltip labelFormatter={formatMonth} formatter={value => [`${Number(value).toFixed(2)} m`, 'Monthly projection']} /><Legend />
              <Line dataKey="predicted" name="Monthly projection" stroke="#ef4444" strokeWidth={2} dot={{r:5}} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
          <h3>Rainfall and weather used for these predictions</h3>
          <p>These are assumed future conditions from historical monthly averages. Rainfall and evapotranspiration are monthly totals.</p>
          <div style={{overflowX:'auto'}}>
            <table style={{width:'100%',borderCollapse:'collapse',textAlign:'left'}}>
              <caption style={{textAlign:'left',padding:'0.5rem 0'}}>Model inputs for the six projected months</caption>
              <thead><tr>
                <th scope="col" style={{padding:'0.5rem'}}>Month</th>
                <th scope="col" style={{padding:'0.5rem'}}>Rainfall (mm)</th>
                <th scope="col" style={{padding:'0.5rem'}}>Temperature (°C)</th>
                <th scope="col" style={{padding:'0.5rem'}}>Evapotranspiration (mm)</th>
              </tr></thead>
              <tbody>{projection.forecast.map(row => <tr key={row.month}>
                <th scope="row" style={{padding:'0.5rem',fontWeight:400}}>{formatMonth(row.month)}</th>
                <td style={{padding:'0.5rem'}}>{row.weather.rainfall_mm.toFixed(1)}</td>
                <td style={{padding:'0.5rem'}}>{row.weather.temperature_c.toFixed(1)}</td>
                <td style={{padding:'0.5rem'}}>{row.weather.evapotranspiration_mm.toFixed(1)}</td>
              </tr>)}</tbody>
            </table>
          </div>
        </>}
        {!projectionAvailable && <p role="status">{projection.message || 'There is insufficient observed history to estimate the next six months.'}</p>}
        {Number.isFinite(projection.estimated_current_gwl) && <p><strong>Estimated current depth:</strong> {projection.estimated_current_gwl.toFixed(2)} m below ground.</p>}
        {projection.last_observed_date && <p><strong>Based on actual observations through:</strong> {projection.last_observed_date}{projection.data_age_months != null ? ` (${projection.data_age_months} months old)` : ''}.</p>}
        {projection.estimate_type === 'zone_fallback' && <p>Monthly projection uses the {projection.source_zone} zone. {projection.zone_fallback_reason}</p>}
        {projectionAvailable && <p style={{color:'#b45309'}}>The current depth bridges the observation gap using historical seasonality and trend. Future depths depend on the assumed rainfall and weather above. Current-period accuracy has not been validated.</p>}
        {projection.limitations?.map(message => <p key={message} role="status">{message}</p>)}
      </>}
    </div>
    <div className="card" style={{padding:'1.25rem'}}>
      <h2>Recorded groundwater history</h2>
      {historyLoading && <p role="status">Loading recorded groundwater history…</p>}
      {historyError && <div role="alert"><p>{historyError}</p><button type="button" onClick={() => setHistoryRetry(value => value + 1)}>Retry history</button></div>}
      {!historyLoading && !historyError && historyChart.length > 0 && <>
      <p>{depthGuide}</p>
      <ResponsiveContainer width="100%" height={380}>
        <LineChart data={historyChart} margin={{top:15,right:25,bottom:15,left:15}}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="month" minTickGap={45} />
          <YAxis label={{value:'Depth (m below ground)',angle:-90,position:'insideLeft'}} />
          <Tooltip /><Legend />
          <Line dataKey="observed" name="Actual observation" stroke="#2563eb" dot={{r:3}} connectNulls isAnimationActive={false} />
          <Line dataKey="filled" name="Forward-filled history" stroke="#94a3b8" dot={{r:2}} strokeDasharray="3 3" isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <p>Filled values are identified separately from measurements.</p>
      </>}
      {!historyLoading && !historyError && !historyChart.length && <p className="empty-state">No groundwater observations are available for this district.</p>}
    </div>
  </div>;
}
