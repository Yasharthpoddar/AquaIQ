import { useState, useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

/**
 * MapComponent — Leaflet.js India choropleth map (Week 5, Ayush)
 *
 * Props:
 *   scores: Array of { district_id, name, state, score, tier }
 *   geojsonUrl: path to the India district GeoJSON
 *   onDistrictClick: callback(district_id) when a district polygon is clicked
 */

const TIER_COLORS = {
  Safe: '#22c55e',
  Watch: '#f59e0b',
  Warning: '#ef4444',
  Crisis: '#dc2626',
};

const DEFAULT_COLOR = '#e2e8f0';

function getColor(score) {
  if (score == null) return DEFAULT_COLOR;
  if (score >= 81) return TIER_COLORS.Crisis;
  if (score >= 61) return TIER_COLORS.Warning;
  if (score >= 31) return TIER_COLORS.Watch;
  return TIER_COLORS.Safe;
}

function MapComponent({ scores = [], geojsonUrl, onDistrictClick }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const geojsonLayer = useRef(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Build a lookup from district name → score data
  const scoreLookup = {};
  scores.forEach(s => {
    scoreLookup[s.name?.toLowerCase()] = s;
    if (s.district_id) scoreLookup[s.district_id.toLowerCase()] = s;
  });

  // Initialize map
  useEffect(() => {
    if (mapInstance.current) return; // Already initialized

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
    };
  }, []);

  // Load GeoJSON and style districts
  useEffect(() => {
    if (!mapInstance.current || !geojsonUrl) return;

    // Remove old layer
    if (geojsonLayer.current) {
      mapInstance.current.removeLayer(geojsonLayer.current);
    }

    fetch(geojsonUrl)
      .then(r => r.json())
      .then(geojson => {
        const layer = L.geoJSON(geojson, {
          style: (feature) => {
            const name = (feature.properties.district || feature.properties.DISTRICT || feature.properties.name || '').toLowerCase();
            const match = scoreLookup[name];
            return {
              fillColor: match ? getColor(match.score) : DEFAULT_COLOR,
              weight: 1,
              opacity: 0.7,
              color: '#94a3b8',
              fillOpacity: match ? 0.7 : 0.3,
            };
          },
          onEachFeature: (feature, layer) => {
            const name = feature.properties.district || feature.properties.DISTRICT || feature.properties.name || 'Unknown';
            const state = feature.properties.state || feature.properties.ST_NM || '';
            const match = scoreLookup[name.toLowerCase()];

            // Hover tooltip
            const tooltipContent = match
              ? `<strong>${name}</strong>, ${state}<br/>Score: ${match.score} (${match.tier})`
              : `<strong>${name}</strong>, ${state}<br/>No data`;
            layer.bindTooltip(tooltipContent, { sticky: true });

            // Hover highlight
            layer.on('mouseover', () => {
              layer.setStyle({ weight: 3, color: '#1d4ed8', fillOpacity: 0.85 });
              layer.bringToFront();
            });
            layer.on('mouseout', () => {
              geojsonLayer.current.resetStyle(layer);
            });

            // Click handler
            layer.on('click', () => {
              if (onDistrictClick && match) {
                onDistrictClick(match.district_id);
              }
            });
          },
        }).addTo(mapInstance.current);

        geojsonLayer.current = layer;
      })
      .catch(err => console.warn('GeoJSON load failed:', err));
  }, [geojsonUrl, scores]);

  // Search: zoom to matching district
  const handleSearch = (query) => {
    setSearchQuery(query);
    if (!geojsonLayer.current || !query) return;

    const q = query.toLowerCase();
    geojsonLayer.current.eachLayer((layer) => {
      const name = (layer.feature?.properties?.district || layer.feature?.properties?.name || '').toLowerCase();
      if (name.includes(q)) {
        mapInstance.current.fitBounds(layer.getBounds(), { maxZoom: 8 });
        layer.openTooltip();
        layer.setStyle({ weight: 3, color: '#1d4ed8', fillOpacity: 0.9 });
      }
    });
  };

  return (
    <div className="map-wrapper">
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
        {Object.entries(TIER_COLORS).map(([tier, color]) => (
          <div key={tier} className="legend-item">
            <span className="legend-swatch" style={{ background: color }} />
            <span>{tier}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default MapComponent;
