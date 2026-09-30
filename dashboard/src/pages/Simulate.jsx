import { useState } from 'react';

/**
 * Policy Simulator page — what-if analysis.
 * Route: /simulate
 * 3 sliders + Simulate button → before/after score comparison.
 */

function Simulate() {
  const [districtId, setDistrictId] = useState('RJ-Jaipur');
  const [rainfallChange, setRainfallChange] = useState(0);
  const [extractionChange, setExtractionChange] = useState(0);
  const [result, setResult] = useState(null);

  const handleSimulate = async () => {
    try {
      const res = await fetch('http://localhost:5000/api/simulate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          district_id: districtId,
          rainfall_change_pct: rainfallChange,
          extraction_change_pct: extractionChange
        })
      });
      const data = await res.json();
      setResult({
        baseline: data.baseline_score,
        simulated: data.simulated_score,
      });
    } catch (err) {
      console.error("Simulation error:", err);
    }
  };

  return (
    <div className="page">
      <h1>Policy Simulator</h1>
      <p className="subtitle">What-if analysis: how would policy changes affect crisis scores?</p>

      <div className="simulator-form">
        <div className="form-group">
          <label>District</label>
          <select value={districtId} onChange={e => setDistrictId(e.target.value)}>
            <option value="RJ-Jaipur">Jaipur, Rajasthan</option>
            <option value="GJ-Mehsana">Mehsana, Gujarat</option>
            <option value="MH-Pune">Pune, Maharashtra</option>
            <option value="HR-Kurukshetra">Kurukshetra, Haryana</option>
          </select>
        </div>

        <div className="form-group">
          <label>Rainfall change: {rainfallChange > 0 ? '+' : ''}{rainfallChange}%</label>
          <input
            type="range" min={-50} max={50} value={rainfallChange}
            onChange={e => setRainfallChange(Number(e.target.value))}
          />
        </div>

        <div className="form-group">
          <label>Extraction change: {extractionChange > 0 ? '+' : ''}{extractionChange}%</label>
          <input
            type="range" min={-50} max={50} value={extractionChange}
            onChange={e => setExtractionChange(Number(e.target.value))}
          />
        </div>

        <button className="simulate-btn" onClick={handleSimulate}>
          Simulate
        </button>
      </div>

      {result && (
        <div className="simulation-result">
          <div className="result-card">
            <div className="result-label">Baseline Score</div>
            <div className="result-value">{result.baseline}</div>
          </div>
          <div className="result-arrow">→</div>
          <div className="result-card">
            <div className="result-label">Simulated Score</div>
            <div className="result-value" style={{
              color: result.simulated > result.baseline ? '#dc2626' : '#22c55e'
            }}>
              {result.simulated}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default Simulate;
