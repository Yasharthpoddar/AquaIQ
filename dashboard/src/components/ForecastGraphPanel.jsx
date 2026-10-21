import { useEffect, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend, ReferenceDot } from 'recharts';
import { forecastChartRows } from './forecastGraph';
import { annualBaselineReference, loadRequestedForecastGraph, requestedOriginMonth } from './forecastGraphPresentation';

const depthGuide = 'The graph shows depth in metres below ground. A rising line means deeper groundwater and a lower water level; a falling line means shallower groundwater and a higher water level.';
const formatMonth = month => {
  const [year, number] = String(month).slice(0,7).split('-').map(Number);
  return new Date(year, number - 1, 1).toLocaleDateString('en', {month:'short', year:'numeric'});
};

// Returns the actual chart element used inside ResponsiveContainer. Fixed dimensions
// also permit offline SVG verification without changing the responsive application.
export function forecastPlot(projection, dimensions = {}) {
  const projectionChart = forecastChartRows(projection);
  const baseline = annualBaselineReference(projection);
  return <LineChart {...dimensions} data={projectionChart} margin={{top:15,right:25,bottom:15,left:15}}>
    <CartesianGrid strokeDasharray="3 3" />
    <XAxis dataKey="month" tickFormatter={formatMonth} minTickGap={20} />
    <YAxis label={{value:'Depth (m below ground)',angle:-90,position:'insideLeft'}} />
    <Tooltip labelFormatter={formatMonth} formatter={value => [`${Number(value).toFixed(2)} m`, 'M+12 research estimate']} /><Legend />
    <Line dataKey="predicted" name="M+12 research estimate" stroke="#ef4444" strokeWidth={2} dot={{r:5}} isAnimationActive={false} />
    {baseline && <ReferenceDot x={baseline.month} y={baseline.depth} r={5} fill="#2563eb" stroke="#2563eb" ifOverflow="extendDomain" label={{value:'Annual baseline (M+12)',position:'left',fill:'#2563eb'}} />}
  </LineChart>;
}

export function ForecastGraphView({ projection = null, loading = false, error = null, onRetry = () => {}, controls = null }) {
  const projectionChart = forecastChartRows(projection);
  const projectionAvailable = projectionChart.some(row => row.predicted != null);
  return <div id="forecast-graph" tabIndex={-1} className="card" style={{padding:'1.25rem',margin:'1.5rem 0',scrollMarginTop:'80px'}}>
    <h2>Monthly research projections</h2>
    {controls}
    {loading && <p role="status">Preparing twelve-month research graph…</p>}
    {error && <div role="alert"><p>{error}</p><button type="button" onClick={onRetry}>Retry prediction</button></div>}
    {projection && <>
      <p><strong>Observed origin:</strong> {projection.origin_month || 'Unavailable'} · <strong>Twelve-month target:</strong> {projection.target_month || 'Unavailable'}. The graph starts with the next full calendar month.</p>
      <p>Only the direct M+12 research artifact is available. Months 1–11 remain gaps; the graph does not interpolate missing ML values or extend the six-month model.</p>
    </>}
    {projectionChart.length === 12 ? <>
      <p>{depthGuide}</p>
      <p>Red: M+12 ML estimate when available. Blue marker: annual baseline at M+12, separate from ML; no monthly baseline curve is implied.</p>
      <ResponsiveContainer width="100%" height={380}>{forecastPlot(projection)}</ResponsiveContainer>
    </> : <div role="status" style={{height:380,display:'flex',alignItems:'center',justifyContent:'center'}}>
      {loading ? 'Loading the twelve-month graph…' : error ? 'Graph unavailable. Retry or select an observed origin month.' : 'Graph unavailable: no source-backed origin month is available. No calendar months or values have been invented.'}
    </div>}
    {projection && <>
      {!projectionAvailable && <p role="status">Twelve-month ML is unavailable for this district or origin. No replacement ML value has been plotted.</p>}
      <p><strong>Annual baseline at {projection.target_month || 'M+12'}:</strong> {Number.isFinite(projection.annual_baseline_m) ? `${projection.annual_baseline_m.toFixed(2)} m below ground` : 'Unavailable'}. Persistence and annual seasonal naive are the same reference at M+12; this is not an ML estimate or a monthly curve.</p>
      <p><strong>Source-marked history through month:</strong> {projection.source?.latest_observed_month || 'Unavailable'} · {projection.source?.name || 'Source unavailable'}.</p>
      <p><strong>Model scope:</strong> {projection.scope?.description || 'Unavailable'}. {projection.output_kind === 'historical_research' ? 'Historical research output.' : 'Current-vintage research output.'} No prospective forecast has been issued.</p>
      {projection.unavailable_reasons.map(message => <p key={message} role="status">{message}</p>)}
      <p style={{color:'#b45309'}}>Dates are reported month labels; availability, well continuity and datum remain unverified. Twelve calendar months does not establish twelve full months of operational lead. This artifact has not demonstrated superiority to the annual baseline.</p>
      <details><summary>Forecast provenance</summary>
        <p>Observed origin: {projection.source?.origin_is_observed === true ? 'yes' : 'unavailable'}; imputed origin: {projection.source?.origin_is_imputed === true ? 'yes' : projection.source?.origin_is_imputed === false ? 'no' : 'unknown'}. Training-target cutoff: {projection.model?.train_target_cutoff || 'Unavailable'}.</p>
        {projection.source?.input_flags?.map((flag, index) => <p key={`${flag.feature}-${index}`}>{flag.feature}: {String(flag.status || 'unknown').replaceAll('_', ' ')}; source month {flag.source_month || 'unknown'}; age {flag.age_months ?? 'unknown'} months.</p>)}
        <p style={{overflowWrap:'anywhere'}}>Artifact SHA-256: {projection.model?.model_sha256 || 'Unavailable'}</p>
      </details>
      {projection.limitations?.map(message => <p key={message} role="status">{message}</p>)}
    </>}
  </div>;
}

/** File-only graph reads remain independent of legacy scoring/database availability. */
export default function ForecastGraphPanel({ districtId }) {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const originMonth = requestedOriginMonth(searchParams);
  const [draftOrigin, setDraftOrigin] = useState(originMonth || '');
  const [projection, setProjection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null); setProjection(null);
    loadRequestedForecastGraph(districtId, originMonth).then(result => {
      if (!cancelled) { setProjection(result); setDraftOrigin(result.origin_month || originMonth || ''); setLoading(false); }
    }).catch(err => { if (!cancelled) { setError(err.message || 'The monthly prediction is unavailable.'); setLoading(false); } });
    return () => { cancelled = true; };
  }, [districtId, originMonth, retry]);

  useEffect(() => {
    if (location.hash !== '#forecast-graph') return;
    const card = document.getElementById('forecast-graph');
    card?.focus({preventScroll:true});
    card?.scrollIntoView({block:'start'});
  }, [location.hash, districtId]);

  const setOrigin = value => {
    setSearchParams(previous => {
      const updated = new URLSearchParams(previous);
      if (value) updated.set('origin_month', value); else updated.delete('origin_month');
      return updated;
    });
    setRetry(previous => previous + 1);
  };
  const controls = <form onSubmit={event => { event.preventDefault(); setOrigin(draftOrigin || null); }} style={{margin:'1rem 0'}}>
    <label htmlFor="forecast-origin-month">Observed origin month: </label>
    <input id="forecast-origin-month" type="month" value={draftOrigin} onChange={event => setDraftOrigin(event.target.value)} />{' '}
    <button type="submit">Apply</button>{' '}
    <button type="button" onClick={() => { setDraftOrigin(''); setOrigin(null); }}>Latest observed origin</button>
    <p>Defaults to the latest observed origin. Historical months are shown only when explicitly selected; missing current inputs never trigger an older origin automatically.</p>
  </form>;
  return <ForecastGraphView projection={projection} loading={loading} error={error} controls={controls} onRetry={() => setRetry(previous => previous + 1)} />;
}
