import { useNavigate } from 'react-router-dom';
import MapComponent from '../components/MapComponent';
import '../App.css';

/**
 * Home page — India choropleth map + summary stats.
 * Uses the Leaflet MapComponent with GeoJSON boundaries.
 * Wired to mock data until the Flask API is live.
 */

// Mock crisis scores for demo (replaced with API data in Week 9)
const MOCK_SCORES = [
  { district_id: "RJ-Jaipur", name: "Jaipur", state: "Rajasthan", score: 72, tier: "Warning" },
  { district_id: "GJ-Mehsana", name: "Mehsana", state: "Gujarat", score: 88, tier: "Crisis" },
  { district_id: "MH-Pune", name: "Pune", state: "Maharashtra", score: 35, tier: "Watch" },
  { district_id: "TN-Chennai", name: "Chennai", state: "Tamil Nadu", score: 22, tier: "Safe" },
  { district_id: "HR-Kurukshetra", name: "Kurukshetra", state: "Haryana", score: 91, tier: "Crisis" },
  { district_id: "KA-Bangalore", name: "Bangalore Urban", state: "Karnataka", score: 45, tier: "Watch" },
  { district_id: "PB-Ludhiana", name: "Ludhiana", state: "Punjab", score: 67, tier: "Warning" },
  { district_id: "UP-Lucknow", name: "Lucknow", state: "Uttar Pradesh", score: 18, tier: "Safe" },
];

// GeoJSON path — served from public/ folder
const GEOJSON_URL = "/india_districts.geojson";

const TIER_COLORS = {
  Safe: "#22c55e",
  Watch: "#f59e0b",
  Warning: "#ef4444",
  Crisis: "#dc2626",
};

function Home() {
  const navigate = useNavigate();

  const crisisCounts = {
    Safe: MOCK_SCORES.filter(d => d.tier === "Safe").length,
    Watch: MOCK_SCORES.filter(d => d.tier === "Watch").length,
    Warning: MOCK_SCORES.filter(d => d.tier === "Warning").length,
    Crisis: MOCK_SCORES.filter(d => d.tier === "Crisis").length,
  };

  const handleDistrictClick = (districtId) => {
    navigate(`/district/${districtId}`);
  };

  return (
    <div className="page">
      <h1>Groundwater Crisis Dashboard</h1>
      <p className="subtitle">6-month forecast for India's districts</p>

      {/* Summary cards */}
      <div className="summary-cards">
        {Object.entries(crisisCounts).map(([tier, count]) => (
          <div key={tier} className="summary-card" style={{ borderColor: TIER_COLORS[tier] }}>
            <div className="card-count" style={{ color: TIER_COLORS[tier] }}>{count}</div>
            <div className="card-label">{tier}</div>
          </div>
        ))}
      </div>

      {/* Leaflet choropleth map */}
      <MapComponent
        scores={MOCK_SCORES}
        geojsonUrl={GEOJSON_URL}
        onDistrictClick={handleDistrictClick}
      />

      {/* District list */}
      <h2>Districts</h2>
      <div className="district-list">
        {MOCK_SCORES.map(d => (
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
