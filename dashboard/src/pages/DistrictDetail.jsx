import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';

/**
 * District detail page — score badge, forecast chart, feature breakdown.
 * Route: /district/:id
 */

const DISTRICT_NAMES = {
  "RJ-Jaipur": { name: "Jaipur", state: "Rajasthan", score: 72, tier: "Warning" },
  "GJ-Mehsana": { name: "Mehsana", state: "Gujarat", score: 88, tier: "Crisis" },
  "MH-Pune": { name: "Pune", state: "Maharashtra", score: 35, tier: "Watch" },
  "TN-Chennai": { name: "Chennai", state: "Tamil Nadu", score: 22, tier: "Safe" },
  "HR-Kurukshetra": { name: "Kurukshetra", state: "Haryana", score: 91, tier: "Crisis" },
  "KA-Bangalore": { name: "Bangalore Urban", state: "Karnataka", score: 45, tier: "Watch" },
  "PB-Ludhiana": { name: "Ludhiana", state: "Punjab", score: 67, tier: "Warning" },
  "UP-Lucknow": { name: "Lucknow", state: "Uttar Pradesh", score: 18, tier: "Safe" },
};

const TIER_COLORS = {
  Safe: "#10b981",
  Watch: "#f59e0b",
  Warning: "#f97316",
  Crisis: "#ef4444",
};

function DistrictDetail() {
  const { id } = useParams();
  
  const [info, setInfo] = useState({ name: id, state: "", score: 50, tier: "Watch" });
  const [chartData, setChartData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch district info, history, and forecast concurrently
    Promise.all([
      fetch(`http://localhost:5000/api/district/${id}`).then(res => res.json()),
      fetch(`http://localhost:5000/api/history/${id}?start=2024-07&end=2024-12`).then(res => res.json()),
      fetch(`http://localhost:5000/api/predict/${id}`).then(res => res.json())
    ]).then(([distData, histData, predData]) => {
      
      setInfo({
        name: distData.metadata?.name || id.split('-')[1] || id,
        state: distData.metadata?.state || id.split('-')[0] || "",
        score: distData.crisis_score || 50,
        tier: distData.tier || "Watch"
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
      setLoading(false);
    });
  }, [id]);

  const tierColor = TIER_COLORS[info.tier] || "#f97316";
  const badgeClass = info.tier === "Crisis" ? "crisis" : info.tier === "Warning" ? "warning" : "";

  return (
    <div className="page">
      <Link to="/" className="back-link">← Back to dashboard</Link>
      <h1>{info.name}, {info.state}</h1>
      <p className="subtitle">District ID: {id}</p>

      {/* Score badge */}
      <div className={`score-badge ${badgeClass}`}>
        <div className="score-value" style={{ color: tierColor }}>{info.score}</div>
        <div className="score-label">Crisis Score</div>
        <div className="score-tier" style={{ color: tierColor }}>{info.tier}</div>
      </div>

      {/* 6-month forecast chart */}
      <h2>6-Month GWL Forecast</h2>
      {loading ? <p>Loading chart data...</p> : (
      <div className="chart-container">
        <ResponsiveContainer width="100%" height={320}>
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
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
            <XAxis dataKey="month" stroke="#64748b" tick={{ fontSize: 12 }} />
            <YAxis
              label={{ value: "GWL (m bgl)", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 12 }}
              stroke="#64748b"
              tick={{ fontSize: 12 }}
            />
            <Tooltip
              contentStyle={{
                background: 'rgba(255, 255, 255, 0.95)',
                border: '1px solid rgba(0,0,0,0.1)',
                borderRadius: '8px',
                color: '#0f172a',
                fontSize: '13px'
              }}
            />
            <Area type="monotone" dataKey="gwl" stroke="#3b82f6" fill="url(#gradObserved)" name="Observed" strokeWidth={2.5} dot={{ r: 4 }} />
            <Area type="monotone" dataKey="predicted" stroke="#ef4444" fill="url(#gradPredicted)" name="Predicted" strokeDasharray="6 4" strokeWidth={2.5} dot={{ r: 4 }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      )}
    </div>
  );
}

export default DistrictDetail;
