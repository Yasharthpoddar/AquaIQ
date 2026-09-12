import { useParams, Link } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

/**
 * District detail page — score badge, forecast chart, feature breakdown.
 * Route: /district/:id
 */

// Mock 6-month forecast data
const MOCK_FORECAST = [
  { month: "2027-01", gwl: 8.2, predicted: 8.5 },
  { month: "2027-02", gwl: 8.5, predicted: 8.9 },
  { month: "2027-03", gwl: 9.1, predicted: 9.4 },
  { month: "2027-04", gwl: null, predicted: 10.1 },
  { month: "2027-05", gwl: null, predicted: 10.8 },
  { month: "2027-06", gwl: null, predicted: 11.2 },
];

function DistrictDetail() {
  const { id } = useParams();

  return (
    <div className="page">
      <Link to="/" className="back-link">← Back to map</Link>
      <h1>District: {id}</h1>

      {/* Score badge */}
      <div className="score-badge warning">
        <div className="score-value">72</div>
        <div className="score-label">Crisis Score</div>
        <div className="score-tier">Warning</div>
      </div>

      {/* 6-month forecast chart */}
      <h2>6-Month GWL Forecast</h2>
      <div className="chart-container">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={MOCK_FORECAST}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" />
            <YAxis label={{ value: "GWL (m bgl)", angle: -90, position: "insideLeft" }} />
            <Tooltip />
            <Line type="monotone" dataKey="gwl" stroke="#3b82f6" name="Observed" strokeWidth={2} />
            <Line type="monotone" dataKey="predicted" stroke="#ef4444" name="Predicted" strokeDasharray="5 5" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <p className="chart-note">Mock data — connects to /history and /predict API in Week 9</p>
    </div>
  );
}

export default DistrictDetail;
