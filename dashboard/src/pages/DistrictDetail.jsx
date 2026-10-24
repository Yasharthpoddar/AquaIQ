import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import { fetchDistrict, fetchHistory } from '../api';
import DistrictForecastGraph from '../components/DistrictForecastGraph';
import { recordedHistoryRows, recordedHistoryGuideValue, recordedHistoryObservationSegments, recordedHistoryGapSegments } from '../components/recordedHistory.js';

const COLORS = { Safe:'#22c55e', Watch:'#eab308', Warning:'#f97316', Crisis:'#ef4444' };

export function HistoryTooltip({ active = false, label, rows = [] }) {
  if (!active) return null;
  const row = rows.find(item => item.month === String(label));
  if (!row) return null;
  const observed = Number.isFinite(row.observed);
  const filled = Number.isFinite(row.filled);
  const value = observed ? row.observed : filled ? row.filled : null;
  const month = new Date(`${row.month}-01T00:00:00Z`).toLocaleDateString('en', {month:'long',year:'numeric',timeZone:'UTC'});
  return <div role="tooltip" aria-label="Groundwater history details" className="history-tooltip" style={{background:'#fff',border:'1px solid #cbd5e1',borderRadius:10,padding:'.75rem .9rem',boxShadow:'0 4px 12px #0f172a15',maxWidth:260,fontSize:'.82rem',lineHeight:1.5}}>
    <strong>{month}</strong>
    {value !== null ? <><p style={{color:observed ? '#2563eb' : '#64748b',marginTop:'.25rem'}}>{observed ? 'Source-marked observation' : 'Forward-filled value'}</p><strong>{value.toFixed(2)} m below ground</strong>{filled && !observed && <p>Not a new measurement.</p>}</> : <><p style={{marginTop:'.25rem'}}>No recorded value for this month.</p><p>Dashed connection is a visual guide only.</p></>}
  </div>;
}

export function recordedHistoryPlot(rows, dimensions = {}) {
  return <LineChart {...dimensions} data={rows} margin={{top:16,right:20,bottom:10,left:12}} accessibilityLayer>
    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
    <XAxis dataKey="month" allowDuplicatedCategory={false} minTickGap={45} tickLine={false} tick={{fontSize:12,fill:'#475569'}} />
    <YAxis width={66} tickLine={false} tick={{fontSize:12,fill:'#475569'}} label={{value:'Depth (m below ground)',angle:-90,position:'insideLeft',style:{textAnchor:'middle',fill:'#475569',fontSize:12}}} />
    <Tooltip trigger="hover" shared filterNull={false} content={<HistoryTooltip rows={rows} />} isAnimationActive={false} cursor={{stroke:'#64748b',strokeDasharray:'3 3'}} wrapperStyle={{zIndex:20,pointerEvents:'none'}} />
    <Legend itemSorter={item => item.value === 'Source-marked observation' ? 0 : 1} wrapperStyle={{fontSize:13,paddingTop:12}} />
    {recordedHistoryGapSegments(rows).map(segment => <Line key={`gap-${segment[0].month}`} className="history-gap-guide" dataKey={recordedHistoryGuideValue(segment)} name="Missing-period guide" type="linear" stroke="#2563eb" strokeWidth={1.2} strokeDasharray="5 5" strokeOpacity={0.65} dot={false} activeDot={false} legendType="none" tooltipType="none" connectNulls isAnimationActive={false} />)}
    {recordedHistoryObservationSegments(rows).map(segment => <Line key={segment[0].month} className="history-observation-guide" dataKey={recordedHistoryGuideValue(segment)} name="Observation guide" type="linear" stroke="#2563eb" strokeWidth={1.2} dot={false} activeDot={false} legendType="none" tooltipType="none" connectNulls isAnimationActive={false} />)}
    <Line dataKey="observed" name="Source-marked observation" stroke="#2563eb" strokeWidth={1.2} dot={{r:3,fill:'#fff',strokeWidth:1.2}} activeDot={{r:5,fill:'#fff'}} connectNulls={false} isAnimationActive={false} />
    <Line dataKey="filled" name="Forward-filled history" stroke="#94a3b8" strokeWidth={1} dot={{r:1.8,fill:'#fff',strokeWidth:1}} connectNulls={false} strokeDasharray="3 3" isAnimationActive={false} />
  </LineChart>;
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
  const district = data || {};
  const prediction = district;
  const score = prediction.crisis_score;
  const available = Number.isFinite(score);
  const color = COLORS[prediction.tier] || '#64748b';
  const historyChart = recordedHistoryRows(history);
  const hasHistory = historyChart.some(row => Number.isFinite(row.observed) || Number.isFinite(row.filled));
  const isZone = prediction.estimate_type === 'zone_fallback';
  const historical = prediction.status === 'historical_forecast';
  const scoreTargetMonth = prediction.forecast?.[0]?.month;
  return <div className="page">
    <Link to="/" className="back-link">← Back to dashboard</Link>
    <header className="district-heading">
      <div><p className="eyebrow">District overview</p><h1>{district.metadata?.name || id}{district.metadata?.state ? `, ${district.metadata.state}` : ''}</h1><p className="muted district-id">{id}</p></div>
      <div className="district-index"><span>Project risk index · uncalibrated</span><div><strong style={{color}}>{available ? score : '—'}</strong><span className="tier-label" style={{color}}>{available ? prediction.tier || 'Unclassified' : 'Unavailable'}</span></div><small>{historical ? 'Historical evidence · not a probability' : '0–100 · not a probability'}</small></div>
    </header>
    {loading && <p className="muted" role="status">Loading district evidence…</p>}
    {error && <div className="inline-state error-state" role="alert"><p>{error}</p><button className="button button-secondary" type="button" onClick={() => setDistrictRetry(value => value + 1)}>Retry district</button></div>}
    {data && <>
      <p className="source-line">Index source: {prediction.last_observed_date?.slice(0,7) || 'Unavailable'}{prediction.data_age_months != null ? ` · ${prediction.data_age_months} months old` : ''}{isZone ? ` · ${prediction.source_zone || 'Zone'} estimate` : ''}{scoreTargetMonth ? ` · Index target: ${scoreTargetMonth}` : ''}</p>
      {prediction.message && !available && <p className="availability-reason" role="status">{prediction.message}</p>}
    </>}
    <DistrictForecastGraph key={id} districtId={id} />
    <section className="card history-card">
      <header className="section-heading"><div><h2>Recorded history</h2><p className="muted">Depth in metres below ground. A rising line means deeper groundwater and a lower water level.</p></div></header>
      {historyLoading && <p role="status">Loading recorded groundwater history…</p>}
      {historyError && <div className="inline-state error-state" role="alert"><p>{historyError}</p><button className="button button-secondary" type="button" onClick={() => setHistoryRetry(value => value + 1)}>Retry history</button></div>}
      {!historyLoading && !historyError && hasHistory && <><ResponsiveContainer width="100%" height={360}>{recordedHistoryPlot(historyChart)}</ResponsiveContainer><p className="compact-note">Hover or tap the chart for monthly values. Blue lines join observations; dashed portions bridge missing periods as visual guides only. Grey points are forward fills, not new measurements.</p></>}
      {!historyLoading && !historyError && !hasHistory && <p className="inline-state">No groundwater observations are available for this district.</p>}
    </section>
    {data && <details className="technical-details district-details"><summary>About this index and source</summary><p>The 0–100 index and its tiers are project-defined, uncalibrated indicators, not official classifications or crisis probabilities. The monthly scenario does not update this historical index.</p><p>Month labels do not certify acquisition dates, fixed well panels or datum continuity.</p>{prediction.zone_fallback_reason && <p>{prediction.zone_fallback_reason}</p>}{prediction.message && <p>{prediction.message}</p>}</details>}
  </div>;
}
