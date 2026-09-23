import { useParams, Link } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';

/**
 * District detail page — score badge, forecast chart, feature breakdown.
 * Route: /district/:id
 */

// Mock 6-month forecast data
const MOCK_FORECAST = [
  { month: "Jan '27", gwl: 8.2, predicted: 8.5 },
  { month: "Feb '27", gwl: 8.5, predicted: 8.9 },
  { month: "Mar '27", gwl: 9.1, predicted: 9.4 },
  { month: "Apr '27", gwl: null, predicted: 10.1 },
  { month: "May '27", gwl: null, predicted: 10.8 },
  { month: "Jun '27", gwl: null, predicted: 11.2 },
];

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
  const info = DISTRICT_NAMES[id] || { name: id, state: "", score: 72, tier: "Warning" };
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
      <div className="chart-container">
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={MOCK_FORECAST}>
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

      <p className="chart-note">Mock data — connects to /history and /predict API in Week 9</p>
    </div>
  );
}

export default DistrictDetail;
