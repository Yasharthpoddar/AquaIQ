import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import MapComponent from '../components/MapComponent';
import '../App.css';

/**
 * Home page — India choropleth map + summary stats.
 * Uses the Leaflet MapComponent with GeoJSON boundaries.
 * Wired to Flask API.
 */

// GeoJSON path — served from public/ folder
const GEOJSON_URL = "/india_districts.geojson";

const TIER_COLORS = {
  Safe: "#16a34a",
  Watch: "#d97706",
  Warning: "#ea580c",
  Crisis: "#dc2626",
};

const TIER_GLOWS = {
  Safe: "rgba(22, 163, 74, 0.12)",
  Watch: "rgba(217, 119, 6, 0.12)",
  Warning: "rgba(234, 88, 12, 0.12)",
  Crisis: "rgba(220, 38, 38, 0.12)",
};

const TIER_ICONS = {
  Safe: "🛡️",
  Watch: "👁️",
  Warning: "⚠️",
  Crisis: "🚨",
};

const TIER_DESC = {
  Safe: "Routine monitoring",
  Watch: "Increased monitoring",
  Warning: "Active intervention",
  Crisis: "Emergency response",
};

function Home() {
  const navigate = useNavigate();
  const [scores, setScores] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://localhost:5000/api/alerts')
      .then(res => res.json())
      .then(data => {
        setScores(data.alerts || []);
        setLoading(false);
      })
      .catch(err => {
        console.error("Error fetching alerts:", err);
        setLoading(false);
      });
  }, []);

  const crisisCounts = {
    Safe: scores.filter(d => d.tier === "Safe").length,
    Watch: scores.filter(d => d.tier === "Watch").length,
    Warning: scores.filter(d => d.tier === "Warning").length,
    Crisis: scores.filter(d => d.tier === "Crisis").length,
  };

  const handleDistrictClick = (districtId) => {
    navigate(`/district/${districtId}`);
  };

  return (
    <div className="page">
      <h1>Groundwater Crisis Dashboard</h1>
      <p className="subtitle">Real-time 6-month groundwater level forecasts for 640+ Indian districts</p>

      {/* Summary cards */}
      <div className="summary-cards">
        {Object.entries(crisisCounts).map(([tier, count], i) => (
          <div
            key={tier}
            className={`summary-card fade-in fade-in-delay-${i + 1}`}
            style={{
              '--card-color': TIER_COLORS[tier],
              '--card-glow': TIER_GLOWS[tier],
            }}
          >
            <span className="card-icon">{TIER_ICONS[tier]}</span>
            <div className="card-count" style={{ color: TIER_COLORS[tier] }}>
              {loading ? '-' : count}
            </div>
            <div className="card-label">{tier}</div>
          </div>
        ))}
      </div>

      {/* Stats bar */}
      {!loading && (
        <div className="stats-bar fade-in">
          <div className="stat-item">
            <span>📊</span>
            <span>Total monitored:</span>
            <span className="stat-value">{scores.length}</span>
          </div>
          <div className="stat-item">
            <span>🎯</span>
            <span>Avg score:</span>
            <span className="stat-value">
              {scores.length > 0 ? Math.round(scores.reduce((a, b) => a + b.score, 0) / scores.length) : 0}
            </span>
          </div>
          <div className="stat-item">
            <span>⚡</span>
            <span>Highest risk:</span>
            <span className="stat-value">
              {scores.length > 0 ? scores.reduce((a, b) => a.score > b.score ? a : b).name : '—'}
            </span>
          </div>
        </div>
      )}

      {/* Leaflet choropleth map */}
      {loading ? (
        <div className="loading-container">
          <div className="loading-spinner" />
          <div className="loading-text">Loading map data...</div>
        </div>
      ) : (
        <div className="fade-in">
          <MapComponent
            scores={scores}
            geojsonUrl={GEOJSON_URL}
            onDistrictClick={handleDistrictClick}
          />
        </div>
      )}

      {/* District list */}
      <h2>Monitored Districts</h2>
      <div className="district-list">
        {loading ? (
          <>
            {[...Array(5)].map((_, i) => (
              <div key={i} className="skeleton-pulse" style={{ height: '56px', marginBottom: '8px' }} />
            ))}
          </>
        ) : (
          [...scores].sort((a, b) => b.score - a.score).map((d, i) => (
            <div
              key={d.district_id}
              className={`district-row fade-in`}
              style={{ animationDelay: `${i * 0.05}s` }}
              onClick={() => navigate(`/district/${d.district_id}`)}
            >
              <div>
                <span className="district-name">{d.name}, {d.state}</span>
                <div className="district-meta">
                  {TIER_DESC[d.tier]} · {d.estimate_type === "zone_fallback" ? "Zone estimate" : "District-level data"}
                </div>
              </div>
              <span className="district-score" style={{ background: TIER_COLORS[d.tier] }}>
                {TIER_ICONS[d.tier]} {d.score} — {d.tier}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default Home;
