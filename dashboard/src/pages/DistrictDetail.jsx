import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import { fetchDistrict, fetchHistory } from '../api';
import ForecastGraphPanel from '../components/DistrictForecastGraph';

const COLORS = { Safe:'#22c55e', Watch:'#eab308', Warning:'#f97316', Crisis:'#ef4444' };

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
  if (loading) return <div className="page"><Link to="/" className="back-link">← Back to dashboard</Link><div className="loading-container"><div className="loading-spinner" />Loading groundwater evidence…</div><ForecastGraphPanel key={id} districtId={id} /></div>;
  if (error) return <div className="page"><Link to="/" className="back-link">← Back to dashboard</Link><div className="empty-state" role="alert"><p>{error}</p><button type="button" onClick={() => setDistrictRetry(value => value + 1)}>Retry district</button></div><ForecastGraphPanel key={id} districtId={id} /></div>;
  const district = data;
  const prediction = district;
  const score = prediction.crisis_score;
  const available = Number.isFinite(score);
  const color = COLORS[prediction.tier] || '#64748b';
  const historyChart = history.filter(row => row.gwl != null && Number.isFinite(row.gwl)).map(row => ({
    month:row.month, observed:row.is_observed ? row.gwl : null, filled:row.is_imputed ? row.gwl : null,
  })).sort((a,b) => a.month.localeCompare(b.month));
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
      <div className="score-label">{historical ? 'Historical project risk index (0–100)' : 'Project risk index (0–100)'}</div>
      <div className="score-tier" style={{color}}>{available ? `${prediction.tier} Tier` : 'Insufficient evidence for this model'}</div>
      <p><strong>Source-backed month label:</strong> {prediction.last_observed_date || 'Unavailable'}{prediction.data_age_months != null ? ` (${prediction.data_age_months} months old)` : ''}{isZone ? ' (zone evidence)' : ''}{scoreTargetMonth && <> · <strong>Score model target:</strong> {scoreTargetMonth}</>}</p>
    </div>
    <p>The crisis score combines groundwater depth, changes in depth, and rainfall and drought conditions. The direction of the plotted line alone does not determine the score.</p>
    {prediction.weights_status === 'initial_uncalibrated' && <p role="status">This project score uses initial component weights that have not been calibrated against independent crisis outcomes. It is not an accuracy or confidence percentage.</p>}
    {historical && <p style={{color:'#b45309'}}>This score describes the historical observation period. The twelve-month research graph below does not update this historical score.</p>}
    {prediction.zone_fallback_reason && <p>{prediction.zone_fallback_reason}</p>}
    {prediction.message && <p role="status">{prediction.message}</p>}
    <ForecastGraphPanel key={id} districtId={id} />
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
          <Line dataKey="observed" name="Source-marked monthly mean" stroke="#2563eb" dot={{r:3}} connectNulls isAnimationActive={false} />
          <Line dataKey="filled" name="Forward-filled history" stroke="#94a3b8" dot={{r:2}} strokeDasharray="3 3" isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <p>Source-marked monthly means and bounded forward fills are shown separately; fills are not new measurements. Dates are month labels, not certified acquisition days. Freshness, stable well panels and datum continuity remain unverified.</p>
      </>}
      {!historyLoading && !historyError && !historyChart.length && <p className="empty-state">No groundwater observations are available for this district.</p>}
    </div>
  </div>;
}
