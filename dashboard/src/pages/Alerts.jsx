import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { fetchAlerts } from '../api';

/**
 * Alerts page — lists monitored districts grouped by tier.
 * Route: /alerts
 * Shows tabbed view with Crisis, Warning, Watch, Safe tabs.
 * Queries AquaIQ crisis_scores table via Flask API.
 */

const TIER_COLORS = {
  Crisis: "#ef4444",
  Warning: "#f97316",
  Watch: "#eab308",
  Safe: "#22c55e",
};

const TIER_GLOWS = {
  Crisis: "rgba(239, 68, 68, 0.12)",
  Warning: "rgba(249, 115, 22, 0.12)",
  Watch: "rgba(234, 179, 8, 0.12)",
  Safe: "rgba(34, 197, 94, 0.12)",
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
  const [error, setError] = useState(null);
  const [status, setStatus] = useState('loading');
  const [total, setTotal] = useState(0);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setAlerts([]);
    fetchAlerts(activeTab, 1000)
      .then(data => {
        if (cancelled) return;
        if (!Array.isArray(data.alerts)) throw new Error('The alerts response is incomplete.');
        setAlerts(data.alerts);
        setTotal(data.total ?? data.alerts.length);
        setStatus(data.status || 'success');
      })
      .catch(err => {
        if (cancelled) return;
        setError(`Alerts are unavailable. ${err.message}`);
        setStatus('error');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [activeTab, retry]);

  return (
    <div className="page">
      <h1>Research risk indicators</h1>
      <p className="subtitle">Districts ranked by the uncalibrated project index using available historical evidence. These are research indicators, not official advisories. Review source months and model target dates when interpreting them.</p>
      {!loading && !error && status === 'success' && <p role="status">Showing {alerts.length} of {total} districts in this category, including unavailable evidence.{total > alerts.length && ' The API result limit has been reached.'}</p>}

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
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading-container">
          <div className="loading-spinner" />
          <div className="loading-text">Loading alerts...</div>
        </div>
      ) : error ? (
        <div className="empty-state" role="alert">
          <p>{error}</p>
          <button className="alert-tab" onClick={() => setRetry(value => value + 1)}>Retry alerts</button>
        </div>
      ) : status === 'awaiting_complete_scoring_run' ? (
        <div className="empty-state" role="status">
          <p>Alerts are awaiting a complete scoring run for the current model and data. Risk tiers are unavailable.</p>
          <button className="alert-tab" onClick={() => setRetry(value => value + 1)}>Check again</button>
        </div>
      ) : alerts.length === 0 ? (
        <div className="empty-state">
          No scored districts in this category for the latest completed run.
        </div>
      ) : (
        <div className="alerts-grid">
          {alerts.map((alert, i) => (
            <div
              key={alert.district_id}
              className="alert-card fade-in"
              style={{
                borderLeftColor: TIER_COLORS[alert.tier] || '#64748b',
                '--card-glow': TIER_GLOWS[alert.tier] || 'rgba(0,0,0,0.05)',
                animationDelay: `${Math.min(i * 0.04, 0.4)}s`,
              }}
            >
              <div className="alert-header">
                <Link to={`/district/${alert.district_id}`} className="alert-district">
                  {TIER_ICONS[alert.tier] || '•'} {alert.name}, {alert.state}
                </Link>
                <span className="alert-badge" style={{ background: TIER_COLORS[alert.tier] || '#64748b' }}>
                  {Number.isFinite(alert.score) ? `${alert.score} — ${alert.tier || 'Unclassified'}` : 'Evidence unavailable'}
                </span>
              </div>
              {alert.last_observed_date && <p className="alert-recommendation">
                Source-backed month: {alert.last_observed_date}{alert.forecast_target && ` · Forecast target: ${alert.forecast_target}`}{alert.as_of && ` · Scored as of: ${alert.as_of}`}
                {alert.estimate_type === 'zone_fallback' && ' · Agro-climatic zone estimate'}
              </p>}
              {alert.recommendation && (
                <p className="alert-recommendation">
                  {alert.recommendation}
                </p>
              )}
              {alert.top_factors && alert.top_factors.length > 0 && (
                <div style={{ marginTop: '0.5rem', fontSize: '0.78rem', color: '#64748b' }}>
                  <strong>Model factors:</strong> {alert.top_factors.slice(0, 2).join(' · ')}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Alerts;
