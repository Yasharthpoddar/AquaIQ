import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';

/**
 * District detail page — score badge, forecast chart, feature breakdown.
 * Route: /district/:id
 * Fetches real data from Flask API.
 */

const TIER_COLORS = {
  Safe: "#16a34a",
  Watch: "#d97706",
  Warning: "#ea580c",
  Crisis: "#dc2626",
};

const TIER_ICONS = {
  Safe: "🛡️",
  Watch: "👁️",
  Warning: "⚠️",
  Crisis: "🚨",
};

const TIER_REC = {
  Safe: "Continue routine monitoring. Groundwater levels are within normal range.",
  Watch: "Increase monitoring frequency and promote rainwater harvesting initiatives.",
  Warning: "Restrict new extraction permits and enforce conservation measures immediately.",
  Crisis: "Declare water-stressed zone — implement emergency conservation and supply measures.",
};

function DistrictDetail() {
  const { id } = useParams();

  const [info, setInfo] = useState({ name: id, state: "", score: 0, tier: "Watch" });
  const [chartData, setChartData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);

    Promise.all([
      fetch(`http://localhost:5000/api/district/${id}`).then(res => res.json()),
      fetch(`http://localhost:5000/api/history/${id}?start=2024-07&end=2024-12`).then(res => res.json()),
      fetch(`http://localhost:5000/api/predict/${id}`).then(res => res.json()),
    ]).then(([distData, histData, predData]) => {
      setInfo({
        name: distData.metadata?.name || id,
        state: distData.metadata?.state || "",
        score: distData.crisis_score || 0,
        tier: distData.tier || "Watch",
        estimateType: distData.estimate_type || "district_level",
      });

      const combined = [];
      if (histData.data && Array.isArray(histData.data)) {
        histData.data.forEach(d => {
          combined.push({ month: d.month || d.date, gwl: d.gwl, predicted: null });
        });
      }

      if (predData.forecast && Array.isArray(predData.forecast)) {
        predData.forecast.forEach(d => {
          combined.push({ month: d.month, gwl: null, predicted: d.predicted_gwl });
        });
      }

      setChartData(combined);
      setLoading(false);
    }).catch(err => {
      console.error("Error fetching district detail:", err);
      setError("Failed to load district data. Please try again.");
      setLoading(false);
    });
  }, [id]);

  const tierColor = TIER_COLORS[info.tier] || "#f59e0b";
  const badgeClass = info.tier === "Crisis" ? "crisis" : info.tier === "Warning" ? "warning" : "";

  if (loading) {
    return (
      <div className="page">
        <Link to="/" className="back-link">← Back to dashboard</Link>
        <div className="loading-container">
          <div className="loading-spinner" />
          <div className="loading-text">Loading district data...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <Link to="/" className="back-link">← Back to dashboard</Link>
        <div className="empty-state">
          <p style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>⚠️</p>
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <Link to="/" className="back-link">← Back to dashboard</Link>

      <div className="fade-in">
        <h1>{TIER_ICONS[info.tier]} {info.name}, {info.state}</h1>
        <p className="subtitle">District ID: {id} · {info.estimateType === "zone_fallback" ? "Zone-level estimate" : "District-level data"}</p>
      </div>

      {/* Score badge */}
      <div className={`score-badge ${badgeClass} fade-in fade-in-delay-1`}>
        <div className="score-value" style={{ color: tierColor }}>{info.score}</div>
        <div className="score-label">Crisis Score</div>
        <div className="score-tier" style={{ color: tierColor }}>{info.tier}</div>
      </div>

      {/* Recommendation */}
      <div className="fade-in fade-in-delay-2" style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderLeft: `4px solid ${tierColor}`,
        borderRadius: 'var(--radius)',
        padding: '1.25rem 1.5rem',
        marginBottom: '1.5rem',
        backdropFilter: 'blur(16px)',
      }}>
        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: tierColor, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '6px' }}>
          Recommendation
        </div>
        <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.6 }}>
          {TIER_REC[info.tier]}
        </div>
      </div>

      {/* 6-month forecast chart */}
      <h2>6-Month GWL Forecast</h2>
      <div className="chart-container fade-in fade-in-delay-3">
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={360}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="gradObserved" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradPredicted" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0, 0, 0, 0.06)" />
              <XAxis dataKey="month" stroke="#94a3b8" tick={{ fontSize: 12, fill: '#64748b' }} />
              <YAxis
                label={{ value: "GWL (m bgl)", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 12 }}
                stroke="#94a3b8"
                tick={{ fontSize: 12, fill: '#64748b' }}
              />
              <Tooltip
                contentStyle={{
                  background: 'rgba(255, 255, 255, 0.95)',
                  border: '1px solid rgba(0, 0, 0, 0.08)',
                  borderRadius: '10px',
                  color: '#0f172a',
                  fontSize: '13px',
                  boxShadow: '0 4px 20px rgba(0, 0, 0, 0.08)',
                  backdropFilter: 'blur(12px)',
                }}
              />
              <Area type="monotone" dataKey="gwl" stroke="#3b82f6" fill="url(#gradObserved)" name="Observed" strokeWidth={2.5} dot={{ r: 4, fill: '#3b82f6' }} />
              <Area type="monotone" dataKey="predicted" stroke="#ef4444" fill="url(#gradPredicted)" name="Predicted" strokeDasharray="6 4" strokeWidth={2.5} dot={{ r: 4, fill: '#ef4444' }} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="empty-state" style={{ padding: '2rem' }}>
            No chart data available for this district.
          </div>
        )}
        <p className="chart-note">
          Blue = observed historical GWL · Red dashed = 6-month ensemble forecast
        </p>
      </div>
    </div>
  );
}

export default DistrictDetail;
