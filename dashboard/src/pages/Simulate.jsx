import { useState, useEffect } from 'react';

/**
 * Policy Simulator page — what-if analysis.
 * Route: /simulate
 * Dynamically loads districts from API. 3 sliders + Simulate button → before/after.
 */

const TIER_COLORS = {
  Safe: "#16a34a",
  Watch: "#d97706",
  Warning: "#ea580c",
  Crisis: "#dc2626",
};

function getTierFromScore(score) {
  if (score >= 44) return "Crisis";
  if (score >= 38) return "Warning";
  if (score >= 26) return "Watch";
  return "Safe";
}

function Simulate() {
  const [districts, setDistricts] = useState([]);
  const [districtId, setDistrictId] = useState('');
  const [rainfallChange, setRainfallChange] = useState(0);
  const [extractionChange, setExtractionChange] = useState(0);
  const [result, setResult] = useState(null);
  const [simulating, setSimulating] = useState(false);

  // Load districts from alerts API
  useEffect(() => {
    fetch('http://localhost:5000/api/alerts')
      .then(res => res.json())
      .then(data => {
        const alertDistricts = (data.alerts || []).map(a => ({
          id: a.district_id,
          name: a.name,
          state: a.state,
          score: a.score,
          tier: a.tier,
        }));
        setDistricts(alertDistricts);
        if (alertDistricts.length > 0) {
          setDistrictId(alertDistricts[0].id);
        }
      })
      .catch(err => console.error("Error loading districts:", err));
  }, []);

  const selectedDistrict = districts.find(d => d.id === districtId) || {};

  const handleSimulate = async () => {
    setSimulating(true);
    try {
      const res = await fetch('http://localhost:5000/api/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          district_id: districtId,
          rainfall_change_pct: rainfallChange,
          extraction_change_pct: extractionChange,
        }),
      });
      const data = await res.json();
      const baseline = data.baseline_score;
      const simulated = data.simulated_score;
      const delta = simulated - baseline;

      setResult({
        baseline,
        simulated,
        delta,
        baselineTier: getTierFromScore(baseline),
        simulatedTier: getTierFromScore(simulated),
      });
    } catch (err) {
      console.error("Simulation error:", err);
    } finally {
      setSimulating(false);
    }
  };

  return (
    <div className="page">
      <h1>Policy Simulator</h1>
      <p className="subtitle">What-if analysis: model how policy changes would affect groundwater crisis scores</p>

      <div className="simulator-layout">
        {/* Left: Form */}
        <div className="simulator-form fade-in">
          <div className="form-group">
            <label>Select District</label>
            <select value={districtId} onChange={e => setDistrictId(e.target.value)}>
              {districts.map(d => (
                <option key={d.id} value={d.id}>
                  {d.name}, {d.state} — Score: {d.score} ({d.tier})
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>
              🌧️ Rainfall change:
              <span className="slider-value" style={{
                color: rainfallChange > 0 ? '#16a34a' : rainfallChange < 0 ? '#dc2626' : '#94a3b8'
              }}>
                {rainfallChange > 0 ? '+' : ''}{rainfallChange}%
              </span>
            </label>
            <input
              type="range" min={-50} max={50} value={rainfallChange}
              onChange={e => setRainfallChange(Number(e.target.value))}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#64748b', marginTop: '4px' }}>
              <span>−50% (Drought)</span>
              <span>+50% (Surplus)</span>
            </div>
          </div>

          <div className="form-group">
            <label>
              ⛏️ Extraction change:
              <span className="slider-value" style={{
                color: extractionChange > 0 ? '#dc2626' : extractionChange < 0 ? '#16a34a' : '#94a3b8'
              }}>
                {extractionChange > 0 ? '+' : ''}{extractionChange}%
              </span>
            </label>
            <input
              type="range" min={-50} max={50} value={extractionChange}
              onChange={e => setExtractionChange(Number(e.target.value))}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#64748b', marginTop: '4px' }}>
              <span>−50% (Conservation)</span>
              <span>+50% (Increased)</span>
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
              <p style={{ fontWeight: 600, marginBottom: '0.5rem' }}>No simulation yet</p>
              <p style={{ fontSize: '0.85rem' }}>Adjust the sliders and click "Run Simulation" to see how policy changes would impact this district's crisis score.</p>
            </div>
          ) : (
            <>
              {/* Baseline */}
              <div className="result-card baseline">
                <div className="result-label">Baseline Score</div>
                <div className="result-value" style={{ color: TIER_COLORS[result.baselineTier] }}>
                  {result.baseline}
                </div>
                <div className="result-tier" style={{ color: TIER_COLORS[result.baselineTier] }}>
                  {result.baselineTier}
                </div>
              </div>

              {/* Delta */}
              <div className={`result-delta ${result.delta < 0 ? 'improved' : result.delta > 0 ? 'worsened' : 'neutral'}`}>
                {result.delta < 0 ? '↓' : result.delta > 0 ? '↑' : '→'}
                {' '}
                {result.delta === 0
                  ? 'No change'
                  : `${Math.abs(result.delta)} point ${result.delta < 0 ? 'improvement' : 'increase'}`
                }
              </div>

              {/* Simulated */}
              <div className={`result-card ${result.delta < 0 ? 'improved' : result.delta > 0 ? 'worsened' : 'simulated'}`}>
                <div className="result-label">Simulated Score</div>
                <div className="result-value" style={{ color: TIER_COLORS[result.simulatedTier] }}>
                  {result.simulated}
                </div>
                <div className="result-tier" style={{ color: TIER_COLORS[result.simulatedTier] }}>
                  {result.simulatedTier}
                  {result.baselineTier !== result.simulatedTier && (
                    <span style={{ fontSize: '0.8rem', marginLeft: '8px', opacity: 0.7 }}>
                      (was {result.baselineTier})
                    </span>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default Simulate;
