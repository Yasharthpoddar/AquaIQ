import { useState, useEffect } from 'react';
import { fetchScores, postSimulate } from '../api';

/**
 * Policy Simulator page — what-if analysis.
 * Route: /simulate
 * Uses Option A: perturbs rainfall features, executes physical XGBoost model
 * inference, applies a labelled extraction sensitivity heuristic.
 */

const TIER_COLORS = {
  Safe: "#22c55e",
  Watch: "#eab308",
  Warning: "#f97316",
  Crisis: "#ef4444",
};

function Simulate() {
  const [districts, setDistricts] = useState([]);
  const [districtId, setDistrictId] = useState('');
  const [rainfallChange, setRainfallChange] = useState(0);
  const [extractionChange, setExtractionChange] = useState(0);
  const [result, setResult] = useState(null);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState(null);

  // Load districts from batch scores API
  useEffect(() => {
    let cancelled = false;
    fetchScores()
      .then(data => {
        if (cancelled) return;
        if (data.status === 'awaiting_complete_scoring_run') {
          setError('District estimates are being rebuilt. Reload after the scoring run completes.');
          return;
        }
        const allDistricts = (data.districts || []).map(d => ({
          id: d.district_id,
          name: d.name,
          state: d.state,
          score: d.score,
          tier: d.tier,
        }));
        setDistricts(allDistricts);
        if (allDistricts.length > 0) {
          // Default to Jaipur or first district
          const jaipur = allDistricts.find(d => d.id === 'RJ-Jaipur');
          setDistrictId(jaipur ? jaipur.id : allDistricts[0].id);
        }
      })
      .catch(err => { if (!cancelled) setError(err.message || 'District evidence is unavailable.'); });
    return () => { cancelled = true; };
  }, []);

  const handleSimulate = async () => {
    setSimulating(true);
    setError(null);
    setResult(null);
    try {
      const data = await postSimulate({
        district_id: districtId,
        rainfall_change_pct: rainfallChange,
        extraction_change_pct: extractionChange,
      });

      setResult({
        baseline: data.baseline_score,
        simulated: data.simulated_score,
        delta: data.delta,
        baselineTier: data.baseline_tier,
        simulatedTier: data.simulated_tier,
        extractionHeuristicApplied: data.extraction_heuristic_applied,
        details: data.simulation_details || {},
        observationDate: data.last_observed_date,
        estimateType: data.estimate_type,
        status: data.status,
      });
    } catch (err) {
      setError(err.message || 'This scenario is unavailable.');
    } finally {
      setSimulating(false);
    }
  };

  return (
    <div className="page">
      <h1>Hydrological Policy Simulator</h1>
      <p className="subtitle">Explore sensitivity using the available historical evidence. Extraction effects are a project heuristic, not a measured causal forecast.</p>
      {error && <p role="alert">{error}</p>}
      {result && result.baseline == null && <p role="status">This scenario is unavailable because the baseline has insufficient model evidence.</p>}

      <div className="simulator-layout">
        {/* Left: Form */}
        <div className="simulator-form fade-in">
          <div className="form-group">
            <label>Select Target District</label>
            <select value={districtId} disabled={simulating} onChange={e => { setDistrictId(e.target.value); setResult(null); setError(null); }}>
              {districts.map(d => (
                <option key={d.id} value={d.id}>
                  {d.name}, {d.state} — Score: {d.score ?? 'N/A'} ({d.tier ?? 'Unrated'})
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>
              🌧️ Monsoon Rainfall Variation:
              <span className="slider-value" style={{
                color: rainfallChange > 0 ? '#16a34a' : rainfallChange < 0 ? '#dc2626' : '#94a3b8'
              }}>
                {rainfallChange > 0 ? '+' : ''}{rainfallChange}%
              </span>
            </label>
            <input
              type="range" min={-50} max={50} value={rainfallChange}
              disabled={simulating}
              onChange={e => { setRainfallChange(Number(e.target.value)); setResult(null); }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#64748b', marginTop: '4px' }}>
              <span>−50% (Severe Drought)</span>
              <span>+50% (Excess Monsoon)</span>
            </div>
          </div>

          <div className="form-group">
            <label>
              ⛏️ Groundwater Extraction Policy:
              <span className="slider-value" style={{
                color: extractionChange > 0 ? '#dc2626' : extractionChange < 0 ? '#16a34a' : '#94a3b8'
              }}>
                {extractionChange > 0 ? '+' : ''}{extractionChange}%
              </span>
            </label>
            <input
              type="range" min={-50} max={50} value={extractionChange}
              disabled={simulating}
              onChange={e => { setExtractionChange(Number(e.target.value)); setResult(null); }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#64748b', marginTop: '4px' }}>
              <span>−50% (Aggressive Moratorium)</span>
              <span>+50% (Unregulated Pumping)</span>
            </div>
          </div>

          <button className="simulate-btn" onClick={handleSimulate} disabled={simulating || !districtId}>
            {simulating ? (
              <>
                <div className="loading-spinner" style={{ width: '18px', height: '18px', borderWidth: '2px' }} />
                Simulating...
              </>
            ) : (
              <>🔬 Run Simulation</>
            )}
          </button>
        </div>

        {/* Right: Results */}
        <div className="simulation-result fade-in fade-in-delay-2">
          {!result ? (
            <div className="empty-state" style={{ padding: '3rem 2rem' }}>
              <p style={{ fontSize: '3rem', marginBottom: '0.5rem' }}>🧪</p>
              <p style={{ fontWeight: 600, marginBottom: '0.5rem' }}>No policy scenario simulated yet</p>
              <p style={{ fontSize: '0.85rem' }}>Adjust rainfall and extraction parameters, then execute the simulation to evaluate projected changes.</p>
            </div>
          ) : (
            <>
              {/* Baseline */}
              <div className="result-card baseline">
                <div className="result-label">Baseline Status</div>
                <div className="result-value" style={{ color: TIER_COLORS[result.baselineTier] || '#64748b' }}>
                  {result.baseline ?? 'Unavailable'}
                </div>
                <div className="result-tier" style={{ color: TIER_COLORS[result.baselineTier] || '#64748b' }}>
                  {result.baselineTier ? `${result.baselineTier} Tier` : 'No risk tier'}
                </div>
              </div>

              {/* Delta */}
              <div className={`result-delta ${result.delta < 0 ? 'improved' : result.delta > 0 ? 'worsened' : 'neutral'}`}>
                {result.delta == null ? 'Unavailable' : result.delta < 0 ? '↓' : result.delta > 0 ? '↑' : '→'}
                {' '}
                {result.delta == null ? 'No valid baseline estimate' : result.delta === 0
                  ? 'No change under baseline inputs'
                  : `${Math.abs(result.delta)} point ${result.delta < 0 ? 'decrease in estimated score' : 'increase in estimated score'}`
                }
              </div>

              {/* Simulated */}
              <div className={`result-card ${result.delta < 0 ? 'improved' : result.delta > 0 ? 'worsened' : 'simulated'}`}>
                <div className="result-label">Simulated Status</div>
                <div className="result-value" style={{ color: TIER_COLORS[result.simulatedTier] || '#64748b' }}>
                  {result.simulated ?? 'Unavailable'}
                </div>
                <div className="result-tier" style={{ color: TIER_COLORS[result.simulatedTier] || '#64748b' }}>
                  {result.simulatedTier ? `${result.simulatedTier} Tier` : 'No risk tier'}
                  {result.baselineTier !== result.simulatedTier && (
                    <span style={{ fontSize: '0.8rem', marginLeft: '8px', opacity: 0.8 }}>
                      (shifted from {result.baselineTier})
                    </span>
                  )}
                </div>
              </div>

              {/* Methodology details */}
              <div style={{ marginTop: '1rem', padding: '0.75rem', borderRadius: '8px', background: 'rgba(0,0,0,0.03)', fontSize: '0.78rem', color: '#64748b' }}>
                <div><strong>Last observation:</strong> {result.observationDate || 'Unavailable'}{result.estimateType === 'zone_fallback' ? ' (zone evidence)' : ''}</div>
                {result.status === 'historical_forecast' && <div>This scenario uses historical groundwater evidence.</div>}
                <div><strong>Inference Mode:</strong> {result.details.xgb_inference_used ? 'Model sensitivity on observed evidence' : 'Unchanged baseline or unavailable evidence'}</div>
                {result.extractionHeuristicApplied && (
                  <div><strong>Extraction sensitivity:</strong> Project heuristic; the causal effect has not been calibrated.</div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default Simulate;
