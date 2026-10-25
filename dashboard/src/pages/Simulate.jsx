import { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { fetchDistrictCatalog, fetchScores, postSimulate } from '../api.js';
import { mergeDistrictScores, validateDistrictCatalog } from '../components/districtCatalog.js';
import DistrictSearch from '../components/DistrictSearch.jsx';
import {
  SIMULATION_PRESETS, INITIAL_SIMULATION_INPUTS, TIER_COLORS, availableSimulationEvidence, canExportComparison, comparisonCsv,
  createScenarioRunner, formatSimulationNumber, selectedSimulationPreset, simulationInputReducer,
  simulationTier, validSimulationInputs, validSimulationScore,
} from '../components/simulationComparison.js';

const TIER_TEXT_COLORS = { Safe: '#166534', Watch: '#854d0e', Warning: '#9a3412', Crisis: '#991b1b' };
const sourceMonth = value => typeof value === 'string' ? value.slice(0, 7) : null;

function RiskTier({ value }) {
  const tier = simulationTier(value);
  return <span className="sim-tier" style={{ color: TIER_TEXT_COLORS[tier] || 'var(--text-muted)' }}>{tier || 'Unavailable'}</span>;
}

export function SimulationControls({ districtControl, selectedDistrict = null, inputs = INITIAL_SIMULATION_INPUTS,
  busy = false, onInputChange = () => {}, onPreset = () => {}, onReset = () => {}, onRun = () => {}, onCompare = () => {} }) {
  const preset = selectedSimulationPreset(inputs);
  const canRun = Boolean(selectedDistrict?.district_id) && validSimulationInputs(inputs) && !busy;
  const baselineScore = validSimulationScore(selectedDistrict?.score) && availableSimulationEvidence(selectedDistrict?.status)
    ? selectedDistrict.score : null;
  return <form className="card sim-controls" aria-label="Scenario inputs" onSubmit={event => { event.preventDefault(); if (canRun) onRun(); }}>
    <h2>Scenario inputs</h2>
    {districtControl}
    <div className="sim-baseline" aria-live="polite">
      <span>Current baseline index</span>
      <strong>{formatSimulationNumber(baselineScore)} <small>/ 100</small></strong>
      <RiskTier value={baselineScore === null ? null : selectedDistrict?.tier} />
      {selectedDistrict && <small>Source month: {sourceMonth(selectedDistrict.last_observed_date) || 'Unavailable'}
        {selectedDistrict.status === 'historical_forecast' ? ' · Historical evidence' : ''}
        {selectedDistrict.estimate_type === 'zone_fallback' ? ' · Zone evidence' : ''}</small>}
    </div>
    <fieldset className="sim-fieldset" disabled={busy || !selectedDistrict}>
      <legend>Choose a starting point</legend>
      <div className="sim-presets">
        {SIMULATION_PRESETS.map(item => <button key={item.id} type="button" className="sim-preset"
          aria-pressed={preset?.id === item.id} onClick={() => onPreset(item.id)}>{item.label}</button>)}
      </div>
      <p className="sim-note">Presets are illustrative inputs. Adjust them before running.</p>
      <div className="form-group sim-input-row">
        <div className="sim-input-header">
          <label htmlFor="sim-rainfall">Rainfall variation</label>
          <output htmlFor="sim-rainfall" id="sim-rainfall-value">{formatSimulationNumber(inputs.rainfallChange, true)}%</output>
        </div>
        <input id="sim-rainfall" type="range" min={-50} max={50} step={1} value={inputs.rainfallChange}
          aria-describedby="sim-rainfall-value" aria-valuetext={`${formatSimulationNumber(inputs.rainfallChange, true)} percent rainfall change`}
          onChange={event => onInputChange('rainfallChange', Number(event.target.value))} />
        <div className="sim-range-labels" aria-hidden="true"><span>−50%</span><span>+50%</span></div>
      </div>
      <div className="form-group sim-input-row">
        <div className="sim-input-header">
          <label htmlFor="sim-extraction">Extraction sensitivity <small>(heuristic)</small></label>
          <output htmlFor="sim-extraction" id="sim-extraction-value">{formatSimulationNumber(inputs.extractionChange, true)}%</output>
        </div>
        <input id="sim-extraction" type="range" min={-50} max={50} step={1} value={inputs.extractionChange}
          aria-describedby="sim-extraction-value" aria-valuetext={`${formatSimulationNumber(inputs.extractionChange, true)} percent extraction change`}
          onChange={event => onInputChange('extractionChange', Number(event.target.value))} />
        <div className="sim-range-labels" aria-hidden="true"><span>−50%</span><span>+50%</span></div>
      </div>
      <button type="button" className="button button-secondary" disabled={busy || (inputs.rainfallChange === 0 && inputs.extractionChange === 0)} onClick={onReset}>Reset to zero</button>
    </fieldset>
    <div className="sim-actions">
      <button className="button button-primary" type="submit" disabled={!canRun}>Run scenario</button>
      <button className="button button-secondary" type="button" disabled={!canRun} onClick={() => { if (canRun) onCompare(); }}>Compare scenarios</button>
    </div>
    {busy && <p role="status">Evaluating scenarios…</p>}
  </form>;
}

export function ComparisonResults({ comparison = null, busy = false, selectedDistrictId = '', onExport = () => {} }) {
  const rows = comparison?.rows || [];
  const district = comparison?.district;
  const available = rows.filter(row => row.status === 'available').length;
  const observedMonths = [...new Set(rows.map(row => sourceMonth(row.observedDate)).filter(Boolean))];
  return <section className="card sim-results" aria-labelledby="sim-results-title" aria-busy={busy}>
    <div className="sim-result-heading">
      <div><h2 id="sim-results-title">Scenario comparison</h2>
        {district && <p>{district.name || district.district_id}{district.state ? `, ${district.state}` : ''} <small>({district.district_id})</small></p>}
      </div>
      <button type="button" className="button button-secondary" disabled={busy || !canExportComparison(comparison)} onClick={onExport}>Export CSV</button>
    </div>
    {district && district.district_id !== selectedDistrictId && <p className="sim-note" role="status">These results belong to {district.name || district.district_id}. Run again to compare the newly selected district.</p>}
    {!rows.length ? <div className="sim-empty" role="status">
      <h3>{busy ? 'Preparing your comparison' : 'Explore a scenario'}</h3>
      <p>{busy ? 'Results appear as each scenario completes.' : 'Choose a district, then run custom inputs or compare all six presets.'}</p>
      {!busy && <p className="sim-note">Run a scenario or comparison to enable CSV export.</p>}
    </div> : <>
      <p className="sim-note" role="status">{busy ? `${rows.length} scenarios evaluated so far` : `${rows.length} scenarios evaluated`} · {available} available</p>
      <ul className="sim-bars" aria-label="Scenario project indices on a scale of 0 to 100">
        {rows.map(row => <li key={row.id} className="sim-bar-row">
          <div className="sim-bar-label"><strong>{row.label}</strong><span>{formatSimulationNumber(row.rainfallChange, true)}% rain · {formatSimulationNumber(row.extractionChange, true)}% extraction</span></div>
          {row.status === 'available' ? <>
            <div className="sim-bar-track" aria-hidden="true"><span className="sim-bar-fill" style={{ width: `${row.scenarioScore}%`, backgroundColor: TIER_COLORS[row.scenarioTier] || '#64748b' }} /></div>
            <div className="sim-bar-value"><strong>{formatSimulationNumber(row.scenarioScore)}</strong><RiskTier value={row.scenarioTier} /><span>{formatSimulationNumber(row.delta, true)} points vs baseline</span></div>
          </> : <div className="sim-bar-unavailable">Unavailable</div>}
        </li>)}
      </ul>
      <div className="sim-table-scroll" role="region" aria-label="Scenario comparison table" tabIndex={0}>
        <table className="sim-table">
          <caption>Inputs and project indices for {district?.name || district?.district_id}</caption>
          <thead><tr><th scope="col">Scenario</th><th scope="col">Rainfall</th><th scope="col">Extraction</th>
            <th scope="col">Baseline</th><th scope="col">Baseline tier</th><th scope="col">Scenario index</th>
            <th scope="col">Scenario tier</th><th scope="col">Change</th><th scope="col">Status</th></tr></thead>
          <tbody>{rows.map(row => <tr key={row.id}>
            <th scope="row">{row.label}</th><td>{formatSimulationNumber(row.rainfallChange, true)}%</td><td>{formatSimulationNumber(row.extractionChange, true)}%</td>
            <td>{formatSimulationNumber(row.baselineScore)}</td><td><RiskTier value={row.baselineTier} /></td>
            <td>{formatSimulationNumber(row.scenarioScore)}</td><td><RiskTier value={row.scenarioTier} /></td>
            <td>{formatSimulationNumber(row.delta, true)}</td><td>{row.status === 'available' ? 'Available' : <><strong>{row.status === 'error' ? 'Request failed' : 'Unavailable'}</strong><span className="sim-status-detail">{row.message}</span></>}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <p className="sim-note">Source month: {observedMonths.length ? observedMonths.join(', ') : 'Unavailable'}{rows.some(row => row.sourceStatus === 'historical_forecast') ? ' · Uses historical source evidence.' : ''}</p>
    </>}
  </section>;
}

export default function Simulate() {
  const [districts, setDistricts] = useState([]);
  const [scoreRecords, setScoreRecords] = useState([]);
  const [districtId, setDistrictId] = useState('');
  const [districtLoading, setDistrictLoading] = useState(true);
  const [districtError, setDistrictError] = useState(null);
  const [districtRetry, setDistrictRetry] = useState(0);
  const [inputs, dispatch] = useReducer(simulationInputReducer, INITIAL_SIMULATION_INPUTS);
  const [comparison, setComparison] = useState(null);
  const [busy, setBusy] = useState(false);
  const [runError, setRunError] = useState(null);
  const alive = useRef(true);
  const running = useRef(false);
  const sequence = useRef(0);
  const runner = useRef(null);
  if (!runner.current) runner.current = createScenarioRunner(postSimulate);
  const catalogWithScores = useMemo(() => mergeDistrictScores(districts, scoreRecords), [districts, scoreRecords]);
  const selectedDistrict = catalogWithScores.find(district => district.district_id === districtId) || null;

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setDistrictLoading(true); setDistrictError(null);
    fetchDistrictCatalog().then(validateDistrictCatalog).then(data => {
      if (cancelled) return;
      const records = Array.isArray(data.districts)
        ? data.districts.filter(district => typeof district?.district_id === 'string' && district.district_id) : [];
      if (!records.length) throw new Error('No districts are available. Retry the district list.');
      setDistricts(records);
      setDistrictId(previous => records.some(district => district.district_id === previous) ? previous
        : (records.find(district => district.district_id === 'RJ-Jaipur') || records[0]).district_id);
    }).catch(error => {
      if (!cancelled) { setDistricts([]); setDistrictId(''); setDistrictError(error.message || 'Districts could not be loaded.'); }
    }).finally(() => { if (!cancelled) setDistrictLoading(false); });
    return () => { cancelled = true; };
  }, [districtRetry]);

  useEffect(() => {
    let cancelled = false;
    fetchScores().then(data => { if (!cancelled) setScoreRecords(Array.isArray(data.districts) ? data.districts : []); })
      .catch(() => { if (!cancelled) setScoreRecords([]); });
    return () => { cancelled = true; };
  }, [districtRetry]);

  const runScenarios = async scenarios => {
    if (running.current || districtLoading || !selectedDistrict || !validSimulationInputs(inputs)) return;
    running.current = true;
    const runId = ++sequence.current;
    // Keep the district label and input values from the moment this run was submitted.
    const district = { district_id: selectedDistrict.district_id, name: selectedDistrict.name, state: selectedDistrict.state };
    setBusy(true); setRunError(null);
    setComparison({ runId, district, rows: [], completed: false });
    try {
      const rows = await runner.current({ districtId: district.district_id, scenarios,
        shouldContinue: () => alive.current && runId === sequence.current,
        onResult: completedRows => setComparison(current => current?.runId === runId ? { ...current, rows: completedRows } : current),
      });
      if (alive.current && rows !== null) setComparison(current => current?.runId === runId ? { ...current, rows, completed: true } : current);
    } catch (error) {
      if (alive.current) setRunError(error.message || 'This comparison could not be started.');
    } finally {
      running.current = false;
      if (alive.current) setBusy(false);
    }
  };

  const exportComparison = () => {
    const csv = comparisonCsv(comparison);
    if (busy || !csv) return;
    const url = URL.createObjectURL(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `aquaiq-scenarios-${comparison.district.district_id.replace(/[^a-z0-9_-]/gi, '_')}.csv`;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const districtControl = <DistrictSearch districts={districts} selectedId={districtId} label="Simulation district"
    loading={districtLoading} error={districtError} disabled={busy} onRetry={() => setDistrictRetry(value => value + 1)}
    onQueryChange={() => { setDistrictId(''); setRunError(null); }}
    onSelect={district => { setDistrictId(district.district_id); setRunError(null); }} />;
  const preset = selectedSimulationPreset(inputs);

  return <div className="page">
    <h1>Scenario simulator</h1>
    <p className="subtitle">Compare rainfall and extraction inputs for a district’s project risk index.</p>
    <p className="sim-note">Illustrative sensitivity only. Extraction effects are heuristic and uncalibrated.</p>
    {runError && <p role="alert">{runError}</p>}
    <div className="sim-layout">
      <SimulationControls districtControl={districtControl} selectedDistrict={districtLoading ? null : selectedDistrict} inputs={inputs} busy={busy}
        onInputChange={(field, value) => dispatch({ type: 'change', field, value })}
        onPreset={id => dispatch({ type: 'preset', id })} onReset={() => dispatch({ type: 'reset' })}
        onRun={() => runScenarios([{ ...inputs, id: preset?.id || 'custom', label: preset?.label || 'Custom scenario' }])}
        onCompare={() => runScenarios(SIMULATION_PRESETS)} />
      <ComparisonResults comparison={comparison} busy={busy} selectedDistrictId={districtId} onExport={exportComparison} />
    </div>
    <details className="card sim-method"><summary>How it works</summary>
      <p>Rainfall inputs adjust rainfall-related features before the existing scoring pipeline runs. Extraction adds a project sensitivity adjustment. Baseline inputs (0%, 0%) return the unchanged baseline.</p>
      <p>These parameter scenarios do not predict groundwater depth or establish policy outcomes. A lower index alone does not demonstrate better groundwater outcomes. Historical or zone evidence may be used when identified by the service; missing evidence stays unavailable.</p>
      <p>Compare scenarios evaluates each preset sequentially through the existing simulation endpoint. Results remain on this page until the next run or page reload.</p>
    </details>
  </div>;
}
