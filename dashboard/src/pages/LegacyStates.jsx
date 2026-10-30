import { useState, useEffect, useCallback, useMemo, useId } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import StateMapComponent from '../components/StateMapComponent';
import StateForecastGraph from '../components/StateForecastGraph';
import { fetchStates, fetchStatesSummary, fetchStatePredict } from '../api';
import { defaultStateId, validateStatesRegistry, validateStatesSummary, validateStateForecast } from '../components/stateForecastContract.js';
import { searchStates, stateSelectionId } from '../stateMap.js';
import './States.css';

const depth = value => Number.isFinite(value) ? `${value.toFixed(2)} m bgl` : 'Unavailable';
const change = value => Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${value.toFixed(2)} m` : 'Unavailable';
const availability = row => row.status === 'pending' ? 'Summary loading' : row.status === 'summary_error' ? 'Summary unavailable' : row.status === 'available' ? 'Forecast available' : 'Forecast unavailable';

export function StateSearchResults({ id, matches, activeIndex, onSelect }) {
  return <ul className="state-search-results" id={`${id}-results`} role="listbox" aria-label="Matching states">{matches.map((row, i) => <li key={row.state_id} role="none"><button type="button" role="option" id={`${id}-option-${i}`} aria-selected={activeIndex === i} tabIndex={-1} onMouseDown={event => event.preventDefault()} onClick={() => onSelect(row.state_id)}><span>{row.state_name}</span><small>{row.state_id} · {availability(row)}</small></button></li>)}</ul>;
}

export function StateSelector({ states, selectedId, onSelect, disabled = false }) {
  const id = useId();
  const selected = states.find(row => row.state_id === selectedId);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [message, setMessage] = useState('');
  const matches = searchStates(states, query).slice(0, 8);
  const choose = candidate => { const code = stateSelectionId(states, candidate); if (code) { onSelect(code); setOpen(false); setQuery(''); setMessage(''); } };
  const submit = () => {
    if (active >= 0 && matches[active]) choose(matches[active].state_id);
    else { const exact = states.filter(row => [row.state_id, row.state_name].some(value => value.toLowerCase() === query.trim().toLowerCase()));
      if (exact.length === 1) choose(exact[0].state_id); else if (matches.length === 1 && query.trim()) choose(matches[0].state_id);
      else { setOpen(true); setMessage(matches.length ? 'Choose a matching state below.' : 'No matching state. Try its name or code.'); } }
  };
  return <div className="state-selector" role="search" aria-label="Select state" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) { setOpen(false); setActive(-1); } }}>
    <label htmlFor={`${id}-search`}>Search and select a state or union territory</label>
    <div className="state-search-input"><input id={`${id}-search`} type="search" role="combobox" aria-autocomplete="list" aria-expanded={open && matches.length > 0} aria-controls={open ? `${id}-results` : undefined} aria-activedescendant={open && active >= 0 ? `${id}-option-${active}` : undefined} placeholder={selected ? `${selected.state_name} (${selected.state_id})` : 'State name or code'} value={query} disabled={disabled} autoComplete="off" onFocus={() => setOpen(true)} onChange={event => { setQuery(event.target.value); setOpen(true); setActive(-1); setMessage(''); }} onKeyDown={event => { if (event.key === 'Escape') { setOpen(false); setActive(-1); } if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setOpen(true); setActive(current => matches.length ? (current + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length : -1); } if (event.key === 'Enter') { event.preventDefault(); submit(); } }} /><button className="button button-secondary" type="button" disabled={disabled || !query.trim()} onClick={submit}>Select</button></div>
    {open && matches.length > 0 && <StateSearchResults id={id} matches={matches} activeIndex={active} onSelect={choose} />}
    {(message || (open && !matches.length)) && <p role="status" className="state-search-status">{message || 'No matching state. Try its name or code.'}</p>}
  </div>;
}

export function StateSummaryTable({ states, selectedId, onSelect }) {
  return <div className="table-scroll state-summary-scroll" role="region" aria-label="State comparison table" tabIndex={0}><table className="data-table"><caption>Latest state summaries · equal district weights · m bgl</caption><thead><tr><th scope="col">State / UT</th><th scope="col">Forecast panel</th><th scope="col">Estimated current depth</th><th scope="col">M+12 estimate</th><th scope="col">Change (m)</th><th scope="col">Status</th></tr></thead><tbody>{states.map(row => <tr key={row.state_id} aria-selected={row.state_id === selectedId}><th scope="row"><button type="button" className="state-name-button" onClick={() => onSelect(row.state_id)}>{row.state_name}<small>{row.state_id}</small></button></th><td>{row.contributing_districts} / {row.total_districts} districts<br /><small>{row.district_coverage_pct}% coverage</small>{row.evidence_tier_counts && <small>{Object.entries(row.evidence_tier_counts).map(([tier,count]) => `${tier}: ${count}`).join(' · ')}</small>}</td><td>{depth(row.estimated_current_gwl_m_bgl ?? row.current_gwl_m_bgl)}</td><td>{depth(row.forecast_12m_gwl_m_bgl)}</td><td>{change(row.projected_change_12m_m)}</td><td><span className={`state-status ${row.status === 'available' ? 'available' : ''}`}>{row.status === 'available' ? 'Available' : 'Unavailable'}</span></td></tr>)}</tbody></table>{!states.length && <p className="inline-state" role="status">No states match this filter.</p>}</div>;
}

export default function LegacyStates() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [registry, setRegistry] = useState(null), [registryError, setRegistryError] = useState(null), [registryRetry, setRegistryRetry] = useState(0);
  const [summary, setSummary] = useState(null), [summaryError, setSummaryError] = useState(null), [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryRetry, setSummaryRetry] = useState(0), [forecastRetry, setForecastRetry] = useState(0), [read, setRead] = useState(null);
  const [metric, setMetric] = useState('depth'), [filter, setFilter] = useState('');
  const asOf = registry?.as_of;
  const currentSummary = summary?.as_of === asOf ? summary : null;
  const states = useMemo(() => currentSummary?.states || registry?.states.map(row => ({ ...row, status: summaryError ? 'summary_error' : 'pending' })) || [], [currentSummary, registry, summaryError]);
  const selectedId = id ? id.toUpperCase() : defaultStateId(registry?.states || []);
  const selected = states.find(row => row.state_id === selectedId);
  const selectedExists = Boolean(selected);
  useEffect(() => {
    let cancelled = false;
    setRegistry(null); setRegistryError(null);
    fetchStates().then(validateStatesRegistry).then(value => { if (!cancelled) setRegistry(value); })
      .catch(error => { if (!cancelled) setRegistryError(error.message || 'State registry unavailable.'); });
    return () => { cancelled = true; };
  }, [registryRetry]);
  useEffect(() => {
    if (!registry) return;
    let cancelled = false;
    setSummaryLoading(true); setSummaryError(null); setSummary(null);
    fetchStatesSummary(12, registry.as_of).then(value => validateStatesSummary(value, registry.as_of, registry)).then(value => { if (!cancelled) { setSummary(value); setSummaryLoading(false); } })
      .catch(error => { if (!cancelled) { setSummaryError(error.message || 'State summary unavailable.'); setSummaryLoading(false); } });
    return () => { cancelled = true; };
  }, [registry, summaryRetry]);
  useEffect(() => {
    if (!selectedId || !asOf || !selectedExists) return;
    let cancelled = false;
    setRead({ id: selectedId, asOf, loading: true, value: null, error: null });
    fetchStatePredict(selectedId, 12, asOf).then(value => validateStateForecast(value, selectedId, asOf))
      .then(value => { if (!cancelled) setRead({ id: selectedId, asOf, value, loading: false, error: null }); })
      .catch(error => { if (!cancelled) setRead({ id: selectedId, asOf, loading: false, value: null, error: error.message || 'State forecast unavailable.' }); });
    return () => { cancelled = true; };
  }, [selectedId, asOf, selectedExists, forecastRetry]);
  const onSelect = useCallback(candidate => { const code = stateSelectionId(registry?.states || [], candidate); if (code) navigate(`/states/${code}`); }, [registry, navigate]);
  // Never render a previous state's result, including the frame before its effect runs.
  const currentRead = read && read.id === selectedId && read.asOf === asOf ? read : null;
  const forecast = currentRead?.value;
  // Detail may finish before the nationwide summary. Display only its returned values.
  const selectedDetails = forecast ? { ...selected, estimated_current_gwl_m_bgl: forecast.estimated_current_gwl_m_bgl,
    contributing_districts: forecast.contributing_districts_count, district_coverage_pct: forecast.district_coverage_pct,
    forecast_12m_gwl_m_bgl: forecast.forecast.at(-1)?.predicted_gwl,
    projected_change_12m_m: forecast.forecast.at(-1)?.delta_from_current_m, last_observed_date: forecast.last_observed_date } : selected;
  const selectedPending = selected && !forecast && !currentSummary && !currentRead?.error;
  const visibleStates = searchStates(currentSummary?.states || [], filter);
  const contributors = new Set(forecast?.contributing_district_ids || []);
  const districts = forecast?.districts || [];
  return <div className="page states-page">
    <header className="page-heading state-page-heading"><div><h1>State-wise Groundwater Forecasts</h1><p className="subtitle">Explore state evidence and the next 12 months of forecasts and reference estimates.</p></div><span className="experimental-badge">Research prototype</span></header>
    <p className="state-science-note">Depth is measured in metres below ground. A higher depth means a lower water level; average depth does not measure the volume of groundwater. Current state forecasts remain unverified for operational use.</p>
    {registryError ? <div className="inline-state error-state" role="alert"><h2>State registry unavailable</h2><p>{registryError}</p><button className="button button-secondary" type="button" onClick={() => setRegistryRetry(value => value + 1)}>Retry state registry</button></div>
      : !registry ? <div className="state-loading card" role="status"><span className="loading-spinner" />Loading state registry…</div>
      : <>
        <div className="state-stats"><article className="card"><span>States with forecast outputs</span><strong>{currentSummary ? <>{currentSummary.available_states_count} <small>/ {currentSummary.total_states}</small></> : summaryLoading ? 'Loading…' : 'Unavailable'}</strong><small>Availability does not establish accuracy</small></article><article className="card"><span>Selected estimated current depth</span><strong>{selectedPending ? 'Loading…' : depth(selectedDetails?.estimated_current_gwl_m_bgl ?? selectedDetails?.current_gwl_m_bgl)}</strong><small>{selected?.state_name || 'Select a state'} · estimated district inputs</small></article><article className="card"><span>Selected forecast panel</span><strong>{selectedPending ? 'Loading…' : Number.isInteger(selectedDetails?.contributing_districts) ? `${selectedDetails.contributing_districts} / ${selected.total_districts}` : 'Unavailable'}</strong><small>{Number.isFinite(selectedDetails?.district_coverage_pct) ? `${selectedDetails.district_coverage_pct}% of registered districts` : selected ? 'Coverage is being checked' : 'No matching state'}</small></article><article className="card"><span>Forecast period</span><strong>12 months</strong><small>As of {asOf}</small></article></div>
        <section className="card state-explorer"><div className="state-explorer-controls"><StateSelector states={states} selectedId={selectedId} onSelect={onSelect} /><fieldset className="state-metric-control"><legend>Map display</legend><button type="button" aria-pressed={metric === 'depth'} onClick={() => setMetric('depth')}>Estimated depth</button><button type="button" aria-pressed={metric === 'delta'} onClick={() => setMetric('delta')}>M+12 change</button></fieldset></div><div className="state-explorer-grid"><div className="state-map-panel"><h2>India state map</h2><p className="muted">Select a boundary or use the searchable selector. {summaryLoading ? 'Nationwide summary is loading; individual states can be opened now.' : summaryError ? 'Nationwide summary is unavailable; individual state requests remain available.' : ''}</p><StateMapComponent states={states} selectedStateId={selectedId} onSelectState={onSelect} metric={metric} /></div><div className="state-selected-panel"><header><p className="eyebrow">Selected state / union territory</p><h2>{selected?.state_name || 'State not found'}</h2><p className="muted">{selectedId || 'No state selected'}</p></header>{selected ? <><dl className="state-facts"><div><dt>M+12 estimate depth</dt><dd>{selectedPending ? 'Loading…' : depth(selectedDetails.forecast_12m_gwl_m_bgl)}</dd></div><div><dt>Change from estimated current depth</dt><dd>{selectedPending ? 'Loading…' : change(selectedDetails.projected_change_12m_m)}</dd></div><div><dt>Latest source-marked observation month</dt><dd>{selectedPending ? 'Loading…' : selectedDetails.last_observed_date?.slice(0, 7) || 'Unknown'}</dd></div></dl><p className="forecast-note">Every registered district contributes equally. Tier A uses XGBoost; B and D hold the last genuine depth constant; C uses a regional or global reference without local history. The evidence mix matters when interpreting the mean.</p></> : <p className="inline-state" role="status">This state ID is not present in the API registry. Use the map or selector to choose a registered state.</p>}</div></div></section>
        {selected && <StateForecastGraph key={selectedId} forecastData={forecast} loading={!currentRead || currentRead.loading} error={currentRead?.error} onRetry={() => setForecastRetry(value => value + 1)} />}
        {selected && <section className="card state-district-card"><header className="section-heading"><div><h2>Districts in {selected.state_name}</h2><p className="muted">Open a district for its source history, method, uncertainty and evidence tier.</p></div></header>{!forecast ? <p className="inline-state" role="status">{currentRead?.loading || !currentRead ? 'Loading district membership…' : 'District membership is unavailable for this request.'}</p> : <><p className="forecast-note">{contributors.size} contributing districts / {districts.length} registered. Forecast composition is fixed across all 12 months.</p><div className="state-district-grid">{districts.map(districtId => <Link key={districtId} to={`/district/${encodeURIComponent(districtId)}#forecast-graph`}><strong>{districtId.slice(districtId.indexOf('-') + 1).replaceAll('_', ' ')}</strong><span>{districtId}</span><small>{forecast.district_evidence?.[districtId] ? `Tier ${forecast.district_evidence[districtId].tier} · ${forecast.district_evidence[districtId].method.replaceAll('_', ' ')}` : contributors.has(districtId) ? 'Contributes to forecast panel' : 'Excluded from forecast panel'}</small></Link>)}</div>{forecast.excluded_districts?.length > 0 && <details className="technical-details"><summary>Excluded district evidence</summary><ul>{forecast.excluded_districts.map((row, index) => <li key={row.district_id || index}>{row.district_id || 'District'}: {row.reason || row.message || 'Not eligible for the fixed XGBoost panel.'}</li>)}</ul></details>}</>}</section>}
        <section className="card state-comparison"><header className="section-heading"><div><h2>State comparison</h2><p className="muted">Compare model estimates with their district coverage.</p></div><label className="state-table-filter">Filter states<input type="search" value={filter} onChange={event => setFilter(event.target.value)} placeholder="State name or code" disabled={!currentSummary} /></label></header>{summaryLoading ? <p className="inline-state" role="status">Loading nationwide forecast summary… The selected state can load independently.</p> : summaryError ? <div className="inline-state error-state" role="alert"><h3>State comparison unavailable</h3><p>{summaryError}</p><button className="button button-secondary" type="button" onClick={() => setSummaryRetry(value => value + 1)}>Retry state summary</button></div> : <StateSummaryTable states={visibleStates} selectedId={selectedId} onSelect={onSelect} />}</section>
      </>}
  </div>;
}
