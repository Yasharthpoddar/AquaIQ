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
  Safe: "#10b981",
  Watch: "#f59e0b",
  Warning: "#f97316",
  Crisis: "#ef4444",
};

const TIER_ICONS = {
  Safe: "✓",
  Watch: "⚡",
  Warning: "⚠",
  Crisis: "🔴",
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
        {Object.entries(crisisCounts).map(([tier, count]) => (
          <div
            key={tier}
            className="summary-card"
            style={{
              borderColor: TIER_COLORS[tier],
              '--card-color': TIER_COLORS[tier],
            }}
          >
            <div style={{
              position: 'absolute', top: 0, left: 0, right: 0, height: '3px',
              background: TIER_COLORS[tier],
              borderRadius: '16px 16px 0 0'
            }} />
            <div className="card-count" style={{ color: TIER_COLORS[tier] }}>
              {TIER_ICONS[tier]} {count}
            </div>
            <div className="card-label">{tier}</div>
          </div>
        ))}
      </div>

      {/* Leaflet choropleth map */}
      {loading ? <p>Loading map data...</p> : (
        <MapComponent
          scores={scores}
          geojsonUrl={GEOJSON_URL}
          onDistrictClick={handleDistrictClick}
        />
      )}

      {/* District list */}
      <h2>Monitored Districts</h2>
      <div className="district-list">
        {loading ? <p>Loading districts...</p> : scores.sort((a, b) => b.score - a.score).map(d => (
          <div
            key={d.district_id}
            className="district-row"
            onClick={() => navigate(`/district/${d.district_id}`)}
          >
            <span className="district-name">{d.name}, {d.state}</span>
            <span className="district-score" style={{ background: TIER_COLORS[d.tier] }}>
              {d.score} — {d.tier}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Home;
