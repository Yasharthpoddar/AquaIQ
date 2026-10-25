import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import MapComponent from '../components/MapComponent';
import { fetchScores, fetchDistrictCatalog, fetchStatesSummary } from '../api';
import { mergeDistrictScores, validateDistrictCatalog, validateHomeForecastSummary } from '../components/districtCatalog.js';
import { ForecastCoverage, RiskIndexNotice } from '../components/ForecastCoverage.jsx';
import { districtForecastPath } from '../components/districtNavigation.js';
import '../App.css';

/**
 * Home page — India choropleth map + summary stats.
 * Uses the Leaflet MapComponent with GeoJSON boundaries.
 * District navigation and published forecasts are independent of risk scoring.
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
  const [catalog, setCatalog] = useState([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState(null);
  const [catalogRetry, setCatalogRetry] = useState(0);
  const [forecastSummary, setForecastSummary] = useState(null);
  const [forecastLoading, setForecastLoading] = useState(true);
  const [forecastError, setForecastError] = useState(null);
  const [forecastRetry, setForecastRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setCatalogLoading(true); setCatalogError(null);
    fetchDistrictCatalog().then(validateDistrictCatalog).then(data => {
      if (!cancelled) { setCatalog(data.districts); setTotalDistricts(data.total); }
    }).catch(error => { if (!cancelled) { setCatalog([]); setCatalogError(error.message || 'District registry unavailable.'); } })
      .finally(() => { if (!cancelled) setCatalogLoading(false); });
    return () => { cancelled = true; };
  }, [catalogRetry]);

  useEffect(() => {
    let cancelled = false;
    setForecastLoading(true); setForecastError(null); setForecastSummary(null);
    fetchStatesSummary().then(validateHomeForecastSummary).then(data => {
      if (!cancelled) setForecastSummary(data);
    }).catch(error => { if (!cancelled) setForecastError(error.message || 'Forecast coverage unavailable.'); })
      .finally(() => { if (!cancelled) setForecastLoading(false); });
    return () => { cancelled = true; };
  }, [forecastRetry]);

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
    navigate(districtForecastPath(districtId));
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
  const mappedDistricts = useMemo(() => mergeDistrictScores(catalog, scores), [catalog, scores]);

  return (
    <div className="page">
      <header className="page-heading"><p className="eyebrow">AquaIQ analytics</p><h1>Groundwater overview</h1><p className="subtitle">Explore district evidence and experimental estimates for the next 12 months.</p></header>
      <ForecastCoverage summary={forecastSummary} loading={forecastLoading} error={forecastError}
        onRetry={() => setForecastRetry(value => value + 1)} />
      <RiskIndexNotice loading={loading} error={error} ready={scoresReady} onRetry={() => setRetry(value => value + 1)} />
      {scoresReady && totalDistricts > 0 && <p className="subtitle" role="status">
        {validScores.length} scored · {totalDistricts - validScores.length} unavailable · {totalDistricts} districts
        {observations.length > 0 && ` · Source months ${observations[0].slice(0,7)}–${observations.at(-1).slice(0,7)}`}
      </p>}
      {scoresReady && uncalibrated && <p className="compact-note">Uncalibrated project index · not a crisis probability. Monthly estimates are experimental.</p>}

      {/* Summary cards */}
      {scoresReady && <><h2>Project risk index</h2><div className="summary-cards">
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
      </div></>}

      {/* Stats bar */}
      {scoresReady && totalDistricts > 0 && (
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
      <MapComponent
        scores={mappedDistricts}
        geojsonUrl={GEOJSON_URL}
        onDistrictClick={handleDistrictClick}
        catalogLoading={catalogLoading}
        catalogError={catalogError}
        onCatalogRetry={() => setCatalogRetry(value => value + 1)}
      />

      {/* District list (top risk) */}
      {scoresReady && <><h2>Districts ranked by project index</h2>
      <div className="district-list">
        {validScores.length === 0 ? (
          <div className="empty-state">Groundwater evidence is unavailable for this scoring run.</div>
        ) : (
          [...validScores].sort((a, b) => b.score - a.score).slice(0, 50).map((d, i) => (
            <div
              key={d.district_id}
              className="district-row fade-in"
              style={{ animationDelay: `${Math.min(i * 0.03, 0.5)}s` }}
              onClick={() => handleDistrictClick(d.district_id)}
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
        )}
      </div></>}
    </div>
  );
}

export default Home;
