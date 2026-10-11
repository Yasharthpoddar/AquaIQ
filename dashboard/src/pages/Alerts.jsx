import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

/**
 * Alerts page — lists all monitored districts grouped by tier.
 * Route: /alerts
 * Shows tabbed view with Crisis, Warning, Watch, Safe tabs.
 * Wired to Flask API.
 */

const TIER_COLORS = {
  Crisis: "#dc2626",
  Warning: "#ea580c",
  Watch: "#d97706",
  Safe: "#16a34a",
};

const TIER_GLOWS = {
  Crisis: "rgba(220, 38, 38, 0.12)",
  Warning: "rgba(234, 88, 12, 0.12)",
  Watch: "rgba(217, 119, 6, 0.12)",
  Safe: "rgba(22, 163, 74, 0.12)",
};

const TIER_ICONS = {
  Crisis: "🚨",
  Warning: "⚠️",
  Watch: "👁️",
  Safe: "🛡️",
};

function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("All");

  useEffect(() => {
    fetch('http://localhost:5000/api/alerts')
      .then(res => res.json())
      .then(data => {
        setAlerts(data.alerts || []);
        setLoading(false);
      })
      .catch(err => {
        console.error("Error fetching alerts:", err);
        setLoading(false);
      });
  }, []);

  const tierCounts = {
    All: alerts.length,
    Crisis: alerts.filter(a => a.tier === "Crisis").length,
    Warning: alerts.filter(a => a.tier === "Warning").length,
    Watch: alerts.filter(a => a.tier === "Watch").length,
    Safe: alerts.filter(a => a.tier === "Safe").length,
  };

  const filteredAlerts = activeTab === "All"
    ? alerts
    : alerts.filter(a => a.tier === activeTab);

  return (
    <div className="page">
      <h1>Monitoring Alerts</h1>
      <p className="subtitle">Real-time groundwater crisis monitoring across all tracked districts</p>

      {/* Tier filter tabs */}
      <div className="alert-tabs">
        {["All", "Crisis", "Warning", "Watch", "Safe"].map(tab => (
          <button
            key={tab}
            className={`alert-tab ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
            style={activeTab === tab && tab !== "All" ? {
              background: `${TIER_COLORS[tab]}15`,
              borderColor: TIER_COLORS[tab],
              color: TIER_COLORS[tab],
            } : {}}
          >
            {tab !== "All" && <span>{TIER_ICONS[tab]} </span>}
            {tab}
            <span className="tab-count">{tierCounts[tab]}</span>
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading-container">
          <div className="loading-spinner" />
          <div className="loading-text">Loading alerts...</div>
        </div>
      ) : filteredAlerts.length === 0 ? (
        <div className="empty-state">
          <p style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>✓</p>
          No alerts in this category.
        </div>
      ) : (
        <div className="alerts-grid">
          {filteredAlerts.map((alert, i) => (
            <div
              key={alert.district_id}
              className={`alert-card fade-in`}
              style={{
                borderLeftColor: TIER_COLORS[alert.tier],
                '--card-glow': TIER_GLOWS[alert.tier],
                animationDelay: `${i * 0.06}s`,
              }}
            >
              <div className="alert-header">
                <Link to={`/district/${alert.district_id}`} className="alert-district">
                  {TIER_ICONS[alert.tier]} {alert.name}, {alert.state}
                </Link>
                <span className="alert-badge" style={{ background: TIER_COLORS[alert.tier] }}>
                  {alert.score} — {alert.tier}
                </span>
              </div>
              {alert.recommendation && (
                <p className="alert-recommendation">
                  {alert.recommendation}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Alerts;
