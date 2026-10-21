import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import MapComponent from '../components/MapComponent';
import ResearchForecast from '../components/ResearchForecast';
import { fetchScores } from '../api';
import '../App.css';

/**
 * Home page — India choropleth map + summary stats.
 * Uses the Leaflet MapComponent with GeoJSON boundaries.
 * Loads 725 canonical Indian districts from AquaIQ batch scoring API.
 */

// GeoJSON path — served from public/ folder
const GEOJSON_URL = "/india_districts.geojson";

const TIER_COLORS = {
  Safe: "#22c55e",
  Watch: "#eab308",
  Warning: "#f97316",
  Crisis: "#ef4444",
};

const TIER_GLOWS = {
  Safe: "rgba(34, 197, 94, 0.12)",
  Watch: "rgba(234, 179, 8, 0.12)",
  Warning: "rgba(249, 115, 22, 0.12)",
  Crisis: "rgba(239, 68, 68, 0.12)",
};

const TIER_ICONS = {
  Safe: "🛡️",
  Watch: "👁️",
  Warning: "⚠️",
  Crisis: "🚨",
};

const TIER_DESC = {
  Safe: "Lower project index; review source history",
  Watch: "Watch band on the project index",
  Warning: "Warning band on the project index",
  Crisis: "Higher project index; review source history",
};

function Home() {
  const navigate = useNavigate();
  const [scores, setScores] = useState([]);
  const [tierCounts, setTierCounts] = useState({ Safe: 0, Watch: 0, Warning: 0, Crisis: 0 });
  const [estimateCounts, setEstimateCounts] = useState({ district_level: 0, zone_fallback: 0 });
  const [totalDistricts, setTotalDistricts] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState('loading');
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchScores()
      .then(data => {
        if (cancelled) return;
        if (!Array.isArray(data.districts)) throw new Error('The scores response is incomplete.');
        const rows = data.districts;
        setScores(rows);
        setTierCounts(Object.fromEntries(Object.keys(TIER_COLORS).map(tier => [
          tier, rows.filter(row => Number.isFinite(row.score) && row.tier === tier).length,
        ])));
        setEstimateCounts({
          district_level: rows.filter(row => Number.isFinite(row.score) && row.estimate_type === 'district_level').length,
          zone_fallback: rows.filter(row => Number.isFinite(row.score) && row.estimate_type === 'zone_fallback').length,
        });
        setTotalDistricts(rows.length);
        setStatus(rows.length ? (data.status || 'success') : 'awaiting_complete_scoring_run');
      })
      .catch(err => {
        if (cancelled) return;
        setError(`District scores are unavailable. ${err.message}`);
        setScores([]);
        setStatus('error');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [retry]);

  const handleDistrictClick = (districtId) => {
    navigate(`/district/${districtId}`);
  };

  const validScores = scores.filter(s => Number.isFinite(s.score));
  const avgScore = validScores.length > 0
    ? Math.round(validScores.reduce((acc, s) => acc + s.score, 0) / validScores.length)
    : null;
  const topRisk = validScores.length > 0
    ? [...validScores].sort((a, b) => b.score - a.score)[0]
    : null;
  const observations = validScores.map(row => row.last_observed_date).filter(Boolean).sort();
  const uncalibrated = scores.some(row => row.weights_status === 'initial_uncalibrated');
  const scoresReady = !loading && !error && status === 'success';

  return (
    <div className="page">
      <h1>12-Month Groundwater Research</h1>
      <p className="subtitle">Primary question: can a groundwater-depth estimate for calendar month M+12 improve on the observed origin depth used as an annual baseline?</p>
      <ResearchForecast />
      <h2>Secondary: legacy six-month risk dashboard</h2>
      <p className="subtitle">A registry of 725 districts with available historical evidence and model estimates. Registry coverage does not establish observation coverage or nationwide accuracy.</p>
      <p className="subtitle">Saved six-month historical benchmark: seasonal-naive RMSE 2.132 m versus research HGB 3.060 m on the same 209 cases in 32 districts. These previously inspected historical results do not establish current forecasting skill; HGB remains research-only and abstained.</p>
      {error && <div className="empty-state" role="alert">
        <p>{error}</p>
        <button className="alert-tab" onClick={() => setRetry(value => value + 1)}>Retry scores</button>
      </div>}
      {!loading && !error && status === 'awaiting_complete_scoring_run' && <div className="empty-state" role="status">
        <p>Scores are awaiting a complete scoring run for the current model and data. Risk tiers are unavailable.</p>
        <button className="alert-tab" onClick={() => setRetry(value => value + 1)}>Check again</button>
      </div>}
      {scoresReady && <p className="subtitle" role="status">
        Project risk scale based on {validScores.length} scored districts; {totalDistricts - validScores.length} districts have unavailable evidence.
        {observations.length > 0 && ` Source-backed month labels range from ${observations[0]} to ${observations.at(-1)}. These are monthly labels, not verified acquisition days.`}
      </p>}
      {scoresReady && uncalibrated && <p role="status">These project scores use initial component weights that have not been calibrated against independent crisis outcomes. A score is not an accuracy or confidence percentage.</p>}

      {/* Summary cards */}
      <div className="summary-cards">
        {Object.entries(tierCounts).map(([tier, count], i) => (
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
              {scoresReady ? count : '—'}
            </div>
            <div className="card-label">{tier}</div>
          </div>
        ))}
      </div>

      {/* Stats bar */}
      {scoresReady && (
        <div className="stats-bar fade-in">
          <div className="stat-item">
            <span>📊</span>
            <span>Total districts:</span>
            <span className="stat-value">{totalDistricts}</span>
          </div>
          <div className="stat-item">
            <span>🔬</span>
            <span>Available estimates:</span>
            <span className="stat-value">{estimateCounts.district_level} district · {estimateCounts.zone_fallback} zone fallback</span>
          </div>
          <div className="stat-item">
            <span>🎯</span>
            <span>Average of available scores:</span>
            <span className="stat-value">{avgScore ?? 'Unavailable'}</span>
          </div>
          <div className="stat-item">
            <span>⚡</span>
            <span>Highest project index:</span>
            <span className="stat-value">
              {topRisk ? `${topRisk.name} (${topRisk.score})` : '—'}
            </span>
          </div>
        </div>
      )}

      {/* Leaflet choropleth map */}
      {loading ? (
        <div className="loading-container">
          <div className="loading-spinner" />
          <div className="loading-text">Loading nationwide district map...</div>
        </div>
      ) : scoresReady ? (
        <div className="fade-in">
          <MapComponent
            scores={scores}
            geojsonUrl={GEOJSON_URL}
            onDistrictClick={handleDistrictClick}
          />
        </div>
      ) : null}

      {/* District list (top risk) */}
      <h2>Districts ranked by project index</h2>
      <div className="district-list">
        {loading ? (
          <>
            {[...Array(5)].map((_, i) => (
              <div key={i} className="skeleton-pulse" style={{ height: '56px', marginBottom: '8px' }} />
            ))}
          </>
        ) : scoresReady && validScores.length === 0 ? (
          <div className="empty-state">Groundwater evidence is unavailable for this scoring run.</div>
        ) : scoresReady ? (
          [...validScores].sort((a, b) => b.score - a.score).slice(0, 50).map((d, i) => (
            <div
              key={d.district_id}
              className="district-row fade-in"
              style={{ animationDelay: `${Math.min(i * 0.03, 0.5)}s` }}
              onClick={() => navigate(`/district/${d.district_id}`)}
            >
              <div>
                <span className="district-name">{d.name}, {d.state}</span>
                <div className="district-meta">
                  {TIER_DESC[d.tier] || "Review available evidence"} · {d.estimate_type === "zone_fallback" ? "Agro-climatic zone estimate" : "Estimate using district history"}
                </div>
              </div>
              <span className="district-score" style={{ background: TIER_COLORS[d.tier] || '#64748b' }}>
                {TIER_ICONS[d.tier] || '•'} {d.score} — {d.tier}
              </span>
            </div>
          ))
        ) : null}
      </div>
    </div>
  );
}

export default Home;
