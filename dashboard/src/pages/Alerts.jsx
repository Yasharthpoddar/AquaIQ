import { Link } from 'react-router-dom';

/**
 * Alerts page — lists all districts in Warning or Crisis tier.
 * Route: /alerts
 */

const MOCK_ALERTS = [
  { district_id: "GJ-Mehsana", name: "Mehsana", state: "Gujarat", score: 88, tier: "Crisis",
    action: "Declare water-stressed zone — emergency conservation and supply measures." },
  { district_id: "HR-Kurukshetra", name: "Kurukshetra", state: "Haryana", score: 91, tier: "Crisis",
    action: "Declare water-stressed zone — emergency conservation and supply measures." },
  { district_id: "RJ-Jaipur", name: "Jaipur", state: "Rajasthan", score: 72, tier: "Warning",
    action: "Restrict new extraction permits and enforce conservation measures." },
];

const TIER_COLORS = {
  Warning: "#ef4444",
  Crisis: "#dc2626",
};

function Alerts() {
  return (
    <div className="page">
      <h1>Active Alerts</h1>
      <p className="subtitle">Districts requiring immediate attention</p>

      {MOCK_ALERTS.length === 0 ? (
        <div className="empty-state">No active alerts. All districts are Safe or Watch.</div>
      ) : (
        <div className="alert-list">
          {MOCK_ALERTS.map(alert => (
            <div key={alert.district_id} className="alert-card" style={{ borderLeftColor: TIER_COLORS[alert.tier] }}>
              <div className="alert-header">
                <Link to={`/district/${alert.district_id}`} className="alert-district">
                  {alert.name}, {alert.state}
                </Link>
                <span className="alert-badge" style={{ background: TIER_COLORS[alert.tier] }}>
                  {alert.score} — {alert.tier}
                </span>
              </div>
              <p className="alert-action">{alert.action}</p>
            </div>
          ))}
        </div>
      )}

      <p className="chart-note">Mock data — connects to /alerts API in Week 9</p>
    </div>
  );
}

export default Alerts;
