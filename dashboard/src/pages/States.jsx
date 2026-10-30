import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import StateMapComponent from '../components/StateMapComponent';
import { StateMedianForecastView, StateMedianCoverageCard, useStateMedianHistory } from '../components/StateMedianForecast';
import StateSummaryTable from '../components/StateMedianSummaryTable';
import { fetchPrimaryStates, fetchPrimaryStatesSummary, fetchPrimaryStatePredict } from '../api';
import { validateMedianStatesRegistry, validateMedianStatesSummary, validateStateMedianForecast, medianStateDetails, medianMethodLabel, referenceAgeMonths } from '../components/stateMedianForecastContract.js';
import { defaultStateId } from '../components/stateForecastContract.js';
import { searchStates, stateSelectionId } from '../stateMap.js';
import LegacyStates, { StateSelector, StateSearchResults } from './LegacyStates';
import './States.css';

export { StateSelector, StateSearchResults, StateSummaryTable };
const depth = value => Number.isFinite(value) ? `${value.toFixed(2)} m bgl` : 'Unavailable';
const change = value => Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${value.toFixed(2)} m` : 'Unavailable';

export function MedianStates() {
  const { id } = useParams(), navigate = useNavigate();
  const [registry, setRegistry] = useState(null), [registryError, setRegistryError] = useState(null), [registryRetry, setRegistryRetry] = useState(0);
  const [summary, setSummary] = useState(null), [summaryError, setSummaryError] = useState(null), [summaryLoading, setSummaryLoading] = useState(true), [summaryRetry, setSummaryRetry] = useState(0);
  const [read, setRead] = useState(null), [forecastRetry, setForecastRetry] = useState(0);
  const [metric, setMetric] = useState('depth'), [filter, setFilter] = useState('');
  const asOf = summary?.as_of ?? null, generationId = summary?.generation_id ?? null;
  const states = useMemo(() => summary?.states.map(row => ({ ...row, model_version: summary.model_version, reference_age_months: referenceAgeMonths({ ...row, as_of: summary.as_of }) })) || registry?.states.map(row => ({ ...row, status: summaryError ? 'summary_error' : 'pending' })) || [], [summary, registry, summaryError]);
  const selectedId = id ? id.toUpperCase() : defaultStateId(registry?.states || []);
  const registeredState = registry?.states.find(row => row.state_id === selectedId);
  const selected = states.find(row => row.state_id === selectedId);
  const selectedExists = Boolean(registeredState);
  useEffect(() => {
    let cancelled = false;
    setRegistry(null); setRegistryError(null);
    fetchPrimaryStates().then(validateMedianStatesRegistry).then(value => { if (!cancelled) setRegistry(value); })
      .catch(error => { if (!cancelled) setRegistryError(error.message || 'State registry unavailable.'); });
    return () => { cancelled = true; };
  }, [registryRetry]);
  useEffect(() => {
    if (!registry) return;
    let cancelled = false;
    setSummaryLoading(true); setSummaryError(null); setSummary(null);
    fetchPrimaryStatesSummary().then(value => validateMedianStatesSummary(value, registry)).then(value => {
      if (!cancelled) { setSummary(value); setSummaryLoading(false); }
    }).catch(error => { if (!cancelled) { setSummaryError(error.message || 'State median summary unavailable.'); setSummaryLoading(false); } });
    return () => { cancelled = true; };
  }, [registry, summaryRetry]);
  useEffect(() => {
    if (!selectedId || !selectedExists) return;
    let cancelled = false;
    setRead({ id: selectedId, asOf, generationId, loading: true, value: null, error: null });
    fetchPrimaryStatePredict(selectedId, asOf, generationId).then(value => validateStateMedianForecast(value, selectedId, asOf, generationId))
      .then(value => { if (!cancelled) setRead({ id: selectedId, asOf, generationId, loading: false, value, error: null }); })
      .catch(error => { if (!cancelled) setRead({ id: selectedId, asOf, generationId, loading: false, value: null, error: error.message || 'State median forecast unavailable.' }); });
    return () => { cancelled = true; };
  }, [selectedId, selectedExists, asOf, generationId, forecastRetry]);
  const onSelect = useCallback(candidate => {
    const code = stateSelectionId(registry?.states || [], candidate);
    if (code) navigate(`/states/${code}`);
  }, [registry, navigate]);
  const current = read?.id === selectedId && read?.asOf === asOf && read?.generationId === generationId ? read : null;
  const forecast = current?.value;
  const historyRead = useStateMedianHistory(forecast);
  const details = forecast ? medianStateDetails(forecast) : selected;
  const pending = Boolean(selected && !forecast && !summary && !current?.error);
  const vintage = forecast?.as_of || asOf;
  return <div className="page states-page">
    <header className="page-heading state-page-heading"><div><h1>State-wise Groundwater Forecasts</h1><p className="subtitle">State-level groundwater depth forecasts.</p></div></header>
    {registryError ? <div className="inline-state error-state" role="alert"><h2>State registry unavailable</h2><p>{registryError}</p><button className="button button-secondary" type="button" onClick={() => setRegistryRetry(value => value + 1)}>Retry state registry</button></div>
      : !registry ? <div className="state-loading card" role="status"><span className="loading-spinner" />Loading state registry…</div>
        : <>
          <div className="state-stats">
            <StateMedianCoverageCard summary={summary} loading={summaryLoading} />
            <article className="card"><span>Selected State Median</span><strong>{pending ? 'Loading…' : depth(details?.last_observed_gwl_m_bgl)}</strong><small>{details?.historical_reference_date || 'No genuine reference'}{Number.isInteger(details?.reference_age_months) ? ` · ${details.reference_age_months}mo old` : ''}</small></article>
            <article className="card"><span>Historical Coverage</span><strong>{pending ? 'Loading…' : Number.isInteger(details?.contributing_districts_count) ? `${details.contributing_districts_count} / ${details.total_districts_in_state}` : 'Unavailable'}</strong><small>{Number.isFinite(details?.district_coverage_pct) ? `${details.district_coverage_pct.toFixed(1)}% of registered districts` : 'Coverage unavailable'}</small></article>
            <article className="card"><span>Forecast Horizon</span><strong>12 months</strong><small>{vintage ? `Vintage ${vintage}` : 'No published vintage'}</small></article>
          </div>
          {summary && <p className="forecast-note">{summary.publication_status === 'staged_preview_only' ? 'Staged preview' : 'Published'}: {summary.artifact_release || summary.model_version} · vintage {summary.as_of}.</p>}
          <section className="card state-explorer"><div className="state-explorer-controls"><StateSelector states={states} selectedId={selectedId} onSelect={onSelect} /><fieldset className="state-metric-control"><legend>Map display</legend><button type="button" aria-pressed={metric === 'depth'} onClick={() => setMetric('depth')}>Last observed median</button><button type="button" aria-pressed={metric === 'delta'} onClick={() => setMetric('delta')}>M+12 vs reference</button></fieldset></div>
            <div className="state-explorer-grid"><div className="state-map-panel"><h2>India state map</h2><p className="muted">{summaryLoading ? 'Loading summary…' : summaryError ? 'Summary unavailable.' : 'Select a state to view its forecast.'}</p><StateMapComponent states={states} selectedStateId={selectedId} onSelectState={onSelect} metric={metric} mode="median" /></div>
              <div className="state-selected-panel"><header><p className="eyebrow">Selected state / union territory</p><h2>{selected?.state_name || 'State not found'}</h2><p className="muted">{selectedId || 'No state selected'}</p></header>
                {selected ? <><dl className="state-facts"><div><dt>Forecast method</dt><dd>{pending ? 'Loading…' : medianMethodLabel(details)}</dd></div><div><dt>M+12 median estimate</dt><dd>{pending ? 'Loading…' : depth(details?.forecast_12m_gwl_m_bgl)}</dd></div><div><dt>Change from reference</dt><dd>{pending ? 'Loading…' : change(details?.projected_change_12m_m)}</dd></div><div><dt>Reference month</dt><dd>{details?.historical_reference_date?.slice(0, 7) || 'Unavailable'}{Number.isInteger(details?.reference_age_months) ? ` · ${details.reference_age_months}mo old` : ''}</dd></div></dl></> : <p className="inline-state" role="status">This state ID is not present in the canonical registry. Select a registered state using the map or selector.</p>}
              </div>
            </div>
          </section>
          {selected && <StateMedianForecastView value={forecast} loading={!current || current.loading} error={current?.error} onRetry={() => setForecastRetry(value => value + 1)} fullHistory={historyRead.value} historyLoading={historyRead.loading} historyError={historyRead.error} onHistoryRetry={historyRead.onRetry} />}
          {registeredState && <section className="card state-district-card"><header className="section-heading"><div><h2>Districts in {registeredState.state_name}</h2><p className="muted">{registeredState.districts.length} registered districts</p></div></header><div className="state-district-grid">{registeredState.districts.map(districtId => <Link key={districtId} to={`/district/${encodeURIComponent(districtId)}#forecast-graph`}><strong>{districtId.slice(districtId.indexOf('-') + 1).replaceAll('_', ' ')}</strong><span>{districtId}</span><small>Open district forecast</small></Link>)}</div></section>}
          <section className="card state-comparison"><header className="section-heading"><div><h2>State comparison</h2><p className="muted">Median estimates by method and coverage.</p></div><label className="state-table-filter">Filter states<input type="search" value={filter} onChange={event => setFilter(event.target.value)} placeholder="State name or code" disabled={!summary} /></label></header>{summaryLoading ? <p className="inline-state" role="status">Loading state median summary…</p> : summaryError ? <div className="inline-state error-state" role="alert"><h3>State comparison unavailable</h3><p>{summaryError}</p><button className="button button-secondary" type="button" onClick={() => setSummaryRetry(value => value + 1)}>Retry state summary</button></div> : <StateSummaryTable states={searchStates(summary ? states : [], filter)} selectedId={selectedId} onSelect={onSelect} />}</section>
        </>}
  </div>;
}

export const stateForecastMode = value => value === 'legacy' ? 'legacy' : 'median';
export default function States() {
  return stateForecastMode(import.meta.env?.VITE_STATE_FORECAST_MODE) === 'legacy' ? <LegacyStates /> : <MedianStates />;
}
