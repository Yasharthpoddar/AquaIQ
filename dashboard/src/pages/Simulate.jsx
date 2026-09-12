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

  const handleSimulate = () => {
    // Mock simulation — replaced with POST /simulate API call in Week 9
    const baselineScore = 72;
    const delta = (rainfallChange * -0.3) + (extractionChange * 0.5);
    const simulated = Math.max(0, Math.min(100, baselineScore + delta));
    setResult({
      baseline: baselineScore,
      simulated: Math.round(simulated),
    });
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

      <p className="chart-note">Mock simulation — connects to POST /simulate API in Week 9</p>
    </div>
  );
}

export default Simulate;
