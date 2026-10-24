import { useState, useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { getStateColor } from '../stateMap.js';

export { getStateColor };

/**
 * StateMapComponent — Interactive Leaflet India Choropleth for States
 *
 * Props:
 *   states: Array of state summary objects
 *   selectedStateId: string (e.g. 'UP')
 *   onSelectState: callback(stateId)
 *   metric: 'depth' | 'delta'
 *   geojsonUrl: default '/india_states.geojson'
 */

function tooltipText(value) {
  return String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}

export default function StateMapComponent({
  states = [],
  selectedStateId = null,
  onSelectState = null,
  metric = 'depth',
  geojsonUrl = '/india_states.geojson',
}) {
  const mapContainer = useRef(null);
  const mapInstance = useRef(null);
  const geojsonLayer = useRef(null);
  const [mapError, setMapError] = useState(null);

  // Build quick lookup table: state_id -> state object
  const stateLookup = useRef({});
  useEffect(() => {
    const dict = {};
    states.forEach(s => {
      if (s.state_id) dict[s.state_id.toUpperCase()] = s;
    });
    stateLookup.current = dict;
  }, [states]);

  // Initialize Leaflet map
  useEffect(() => {
    if (mapInstance.current || !mapContainer.current) return;

    const map = L.map(mapContainer.current, {
      center: [22.5, 82.0],
      zoom: 4.5,
      minZoom: 4,
      maxZoom: 9,
      attributionControl: false,
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
      subdomains: 'abcd',
    }).addTo(map);

    mapInstance.current = map;

    return () => {
      map.remove();
      mapInstance.current = null;
    };
  }, []);

  // Render or update GeoJSON layer
  useEffect(() => {
    if (!mapInstance.current || !geojsonUrl) return;

    const controller = new AbortController();
    let cancelled = false;

    fetch(geojsonUrl, { signal: controller.signal })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(geojson => {
        if (cancelled || !mapInstance.current) return;

        if (geojsonLayer.current) {
          mapInstance.current.removeLayer(geojsonLayer.current);
          geojsonLayer.current = null;
        }

        const layer = L.geoJSON(geojson, {
          style: feature => {
            const sid = feature.properties?.state_id?.toUpperCase();
            const stateObj = stateLookup.current[sid];
            const isSelected = selectedStateId && sid === selectedStateId.toUpperCase();

            return {
              fillColor: getStateColor(stateObj, metric),
              weight: isSelected ? 3.5 : 1.2,
              opacity: 0.9,
              color: isSelected ? '#1d4ed8' : '#64748b',
              fillOpacity: stateObj?.status === 'available' ? 0.78 : 0.35,
            };
          },
          onEachFeature: (feature, layerItem) => {
            const sid = feature.properties?.state_id?.toUpperCase();
            const sName = feature.properties?.state_name || sid;
            const stateObj = stateLookup.current[sid];

            let tooltipHtml = `<strong>${tooltipText(sName)}</strong> (${tooltipText(sid)})<br/>`;
            if (stateObj && stateObj.status === 'available') {
              tooltipHtml += `
                Current Depth: <strong>${stateObj.current_gwl_m_bgl} m bgl</strong><br/>
                12M Forecast: <strong>${stateObj.forecast_12m_gwl_m_bgl} m bgl</strong> (${stateObj.projected_change_12m_m >= 0 ? '+' : ''}${stateObj.projected_change_12m_m} m)<br/>
                Reporting Coverage: <strong>${stateObj.contributing_districts}/${stateObj.total_districts} districts (${stateObj.district_coverage_pct}%)</strong><br/>
                <small style="color:#64748b">As of: ${tooltipText(stateObj.last_observed_date)}</small>
              `;
            } else {
              tooltipHtml += `<small style="color:#94a3b8">Groundwater observations insufficient or unavailable</small>`;
            }

            layerItem.bindTooltip(tooltipHtml, { sticky: true });

            layerItem.on('mouseover', () => {
              layerItem.setStyle({ weight: 3, color: '#2563eb', fillOpacity: 0.92 });
              layerItem.bringToFront();
            });

            layerItem.on('mouseout', () => {
              geojsonLayer.current?.resetStyle(layerItem);
            });

            layerItem.on('click', () => {
              if (onSelectState && sid) {
                onSelectState(sid);
              }
            });
          },
        }).addTo(mapInstance.current);

        geojsonLayer.current = layer;
      })
      .catch(err => {
        if (!cancelled) setMapError(`State boundaries are unavailable. ${err.message}`);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [geojsonUrl, states, selectedStateId, metric, onSelectState]);

  return (
    <div className="state-map-wrapper" style={{ position: 'relative', width: '100%', height: '100%', minHeight: '440px' }}>
      <div ref={mapContainer} style={{ width: '100%', height: '100%', minHeight: '440px', borderRadius: '8px', zIndex: 1 }} />
      {mapError && (
        <div style={{ position: 'absolute', top: '10px', left: '10px', right: '10px', background: '#fee2e2', color: '#b91c1c', padding: '8px 12px', borderRadius: '6px', fontSize: '13px', zIndex: 1000 }}>
          {mapError}
        </div>
      )}
      <div className="state-map-legend" style={{ position: 'absolute', bottom: '15px', right: '15px', background: 'rgba(255, 255, 255, 0.94)', padding: '10px 14px', borderRadius: '8px', fontSize: '12px', boxShadow: '0 2px 8px rgba(0,0,0,0.15)', zIndex: 900, maxWidth: '240px' }}>
        <div style={{ fontWeight: 600, marginBottom: '6px', color: '#1e293b' }}>
          {metric === 'depth' ? 'Groundwater Depth (m bgl)' : '12M Projected Change (Δm)'}
        </div>
        {metric === 'depth' ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
              <span style={{ width: '14px', height: '14px', background: '#22c55e', borderRadius: '3px' }} />
              <span>&lt; 5 m (Shallow / High Availability)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
              <span style={{ width: '14px', height: '14px', background: '#eab308', borderRadius: '3px' }} />
              <span>5 – 10 m (Moderate Depth)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
              <span style={{ width: '14px', height: '14px', background: '#f97316', borderRadius: '3px' }} />
              <span>10 – 20 m (Deep Water Table)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
              <span style={{ width: '14px', height: '14px', background: '#ef4444', borderRadius: '3px' }} />
              <span>&gt; 20 m (Severely Depleted)</span>
            </div>
          </>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
              <span style={{ width: '14px', height: '14px', background: '#059669', borderRadius: '3px' }} />
              <span>&lt; -1.0 m (Substantial Rise / Recharge)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
              <span style={{ width: '14px', height: '14px', background: '#10b981', borderRadius: '3px' }} />
              <span>-1.0 to 0.0 m (Mild Rise)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
              <span style={{ width: '14px', height: '14px', background: '#f59e0b', borderRadius: '3px' }} />
              <span>0.0 to 1.0 m (Mild Depletion)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
              <span style={{ width: '14px', height: '14px', background: '#ef4444', borderRadius: '3px' }} />
              <span>&gt; 1.0 m (Significant Depletion)</span>
            </div>
          </>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px', borderTop: '1px solid #e2e8f0', paddingTop: '4px' }}>
          <span style={{ width: '14px', height: '14px', background: '#e2e8f0', borderRadius: '3px' }} />
          <span style={{ color: '#64748b' }}>Insufficient Data</span>
        </div>
      </div>
    </div>
  );
}
