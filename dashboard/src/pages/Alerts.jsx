import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

/**
 * Alerts page — lists all districts in Warning or Crisis tier.
 * Route: /alerts
 * Wired to Flask API.
 */

const TIER_COLORS = {
  Warning: "#f97316",
  Crisis: "#ef4444",
};

function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://localhost:5000/api/alerts')
      .then(res => res.json())
      .then(data => {
        setAlerts(data.alerts.filter(a => a.tier === "Warning" || a.tier === "Crisis") || []);
        setLoading(false);
      })
      .catch(err => {
        console.error("Error fetching alerts:", err);
        setLoading(false);
      });
  }, []);

  return (
    <div className="page">
      <h1>Active Alerts</h1>
      <p className="subtitle">Districts requiring immediate policy intervention</p>

      {loading ? (
        <p>Loading active alerts...</p>
      ) : alerts.length === 0 ? (
        <div className="empty-state">
          <p style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>✓</p>
          No active alerts. All districts are Safe or Watch.
        </div>
      ) : (
        <div className="alert-list">
          {alerts.map(alert => (
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

    </div>
  );
}

export default Alerts;
