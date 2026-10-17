import { useState, useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { fetchConfig } from '../api';
import { boundaryCoverage, buildScoreLookup, districtBoundaries, districtName, matchDistrict } from '../districtMap';

/**
 * MapComponent — Leaflet.js India choropleth map
 *
 * Props:
 *   scores: Array of { district_id, name, state, score, tier, estimate_type }
 *   geojsonUrl: path to the India district GeoJSON
 *   onDistrictClick: callback(district_id) when a district polygon is clicked
 */

const DEFAULT_TIER_COLORS = {
  Safe: '#22c55e',
  Watch: '#eab308',
  Warning: '#f97316',
  Crisis: '#ef4444',
};

const DEFAULT_COLOR = '#e2e8f0';

function tooltipText(value) {
  return String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}

function MapComponent({ scores = [], geojsonUrl, onDistrictClick }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const geojsonLayer = useRef(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [tierConfig, setTierConfig] = useState(null);
  const [mapError, setMapError] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [retry, setRetry] = useState(0);

  // Fetch official tier configuration from backend
  useEffect(() => {
    let cancelled = false;
    fetchConfig()
      .then(cfg => {
        if (!cancelled && cfg && cfg.tiers) setTierConfig(cfg.tiers);
      })
      .catch(() => {
        // Only the palette falls back; risk tiers always come from score records.
      });
    return () => { cancelled = true; };
  }, []);

  const getTierColor = (score, tier) => {
    if (!Number.isFinite(score) || !Object.hasOwn(DEFAULT_TIER_COLORS, tier)) return DEFAULT_COLOR;
    return tierConfig?.[tier]?.color || DEFAULT_TIER_COLORS[tier];
  };

  // Match only a canonical ID or a name within the same state.
  const scoreLookup = useRef({});
  useEffect(() => {
    scoreLookup.current = buildScoreLookup(scores);
  }, [scores]);

  const findMatch = props => matchDistrict(props, scoreLookup.current);

  // Initialize map
  useEffect(() => {
    if (mapInstance.current) return;

    const map = L.map(mapRef.current, {
      center: [22.5, 82],
      zoom: 5,
      zoomControl: true,
      scrollWheelZoom: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 12,
    }).addTo(map);

    mapInstance.current = map;

    return () => {
      map.remove();
      mapInstance.current = null;
      geojsonLayer.current = null;
    };
  }, []);

  // Load GeoJSON and style districts
  useEffect(() => {
    if (!mapInstance.current || !geojsonUrl) return;
    let cancelled = false;
    const controller = new AbortController();
    const map = mapInstance.current;
    setMapError(null);
    setCoverage(null);

    if (geojsonLayer.current) {
      map.removeLayer(geojsonLayer.current);
      geojsonLayer.current = null;
    }

    fetch(geojsonUrl, { signal: controller.signal })
      .then(r => {
        if (!r.ok) throw new Error(`Boundary fetch failed: ${r.status}`);
        return r.json();
      })
      .then(geojson => {
        if (cancelled || mapInstance.current !== map) return;
        const boundaries = districtBoundaries(geojson);
        setCoverage(boundaryCoverage(boundaries, scores, scoreLookup.current));
        const layer = L.geoJSON(boundaries, {
          style: (feature) => {
            const match = findMatch(feature.properties || {});
            return {
              fillColor: match ? getTierColor(match.score, match.tier) : DEFAULT_COLOR,
              weight: 1,
              opacity: 0.7,
              color: '#94a3b8',
              fillOpacity: match && Number.isFinite(match.score) ? 0.75 : 0.25,
            };
          },
          onEachFeature: (feature, layer) => {
            const props = feature.properties || {};
            const dName = districtName(props) || 'Unknown';
            const sName = props.st_nm || props.state || props.ST_NM || '';
            const match = findMatch(props);

            const tooltipContent = match
              ? `<strong>${tooltipText(match.name || dName)}</strong> (${tooltipText(match.state || sName)})<br/>
                 ${Number.isFinite(match.score) ? `Score: <strong>${match.score}</strong> · <span style="font-weight:600">${tooltipText(match.tier || 'Unclassified')}</span>` : 'Groundwater evidence unavailable'}<br/>
                 <small style="color:#64748b">${match.estimate_type === 'zone_fallback' ? 'Agro-climatic zone estimate' : 'District observations'}${match.last_observed_date ? ` · Last observation: ${tooltipText(match.last_observed_date)}` : ''}</small>`
              : `<strong>${tooltipText(dName)}</strong> (${tooltipText(sName)})<br/><small style="color:#94a3b8">District evidence unavailable</small>`;

            layer.bindTooltip(tooltipContent, { sticky: true });

            layer.on('mouseover', () => {
              layer.setStyle({ weight: 2.5, color: '#2563eb', fillOpacity: 0.9 });
              layer.bringToFront();
            });
            layer.on('mouseout', () => {
              geojsonLayer.current?.resetStyle(layer);
            });

            layer.on('click', () => {
              if (onDistrictClick && match && match.district_id) {
                onDistrictClick(match.district_id);
              }
            });
          },
        }).addTo(map);

        geojsonLayer.current = layer;
      })
      .catch(err => { if (!cancelled) setMapError(`District boundaries are unavailable. ${err.message}`); });
    return () => { cancelled = true; controller.abort(); };
  }, [geojsonUrl, scores, tierConfig, retry]);

  // Search: zoom to matching district
  const handleSearch = (query) => {
    setSearchQuery(query);
    if (!geojsonLayer.current || !query) return;

    const q = query.toLowerCase().trim();
    geojsonLayer.current.eachLayer((layer) => {
      const dName = districtName(layer.feature?.properties).toLowerCase();
      if (dName.includes(q)) {
        mapInstance.current.fitBounds(layer.getBounds(), { maxZoom: 8 });
        layer.openTooltip();
        layer.setStyle({ weight: 3, color: '#2563eb', fillOpacity: 0.9 });
      }
    });
  };

  const legendColors = tierConfig
    ? Object.fromEntries(Object.entries(tierConfig).map(([k, v]) => [k, v.color]))
    : DEFAULT_TIER_COLORS;

  return (
    <div className="map-wrapper">
      {mapError && <div className="empty-state" role="alert">
        <p>{mapError}</p>
        <button className="alert-tab" onClick={() => setRetry(value => value + 1)}>Retry map</button>
      </div>}
      {coverage && <div className="map-coverage" role="status">
        <p>District boundaries match {coverage.mapped} of {scores.length} scored district records.</p>
        {coverage.missing.length > 0 && <p>Available without a separate matching boundary: {coverage.missing.map((district, index) => <span key={district.district_id}>
          {index > 0 && ' · '}<button type="button" className="alert-tab" onClick={() => onDistrictClick?.(district.district_id)}>{district.name}, {district.state}</button>
        </span>)}. Open a district to review its evidence.</p>}
      </div>}
      <div className="map-search">
        <input
          type="text"
          placeholder="Search district..."
          value={searchQuery}
          onChange={(e) => handleSearch(e.target.value)}
          className="search-input"
        />
      </div>
      <div ref={mapRef} className="map-container" />

      {/* Legend */}
      <div className="map-legend">
        {Object.entries(legendColors).map(([tier, color]) => (
          <div key={tier} className="legend-item">
            <span className="legend-swatch" style={{ background: color }} />
            <span>{tier}</span>
          </div>
        ))}
        <div className="legend-item">
          <span className="legend-swatch" style={{ background: DEFAULT_COLOR }} />
          <span>Evidence unavailable</span>
        </div>
      </div>
    </div>
  );
}

export default MapComponent;
