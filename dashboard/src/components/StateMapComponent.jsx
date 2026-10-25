import { useState, useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { getStateColor, buildStateLookup, matchState, stateSelectionId } from '../stateMap.js';

export { getStateColor };

export default function StateMapComponent({ states = [], selectedStateId = null, onSelectState = null, metric = 'depth', geojsonUrl = '/india_states.geojson' }) {
  const container = useRef(null), mapRef = useRef(null);
  const [boundary, setBoundary] = useState(null), [error, setError] = useState(null), [retry, setRetry] = useState(0);
  useEffect(() => {
    const map = L.map(container.current, { center: [22.5, 82], zoom: 4, minZoom: 2, maxZoom: 9, scrollWheelZoom: false });
    mapRef.current = map;
    // Local boundaries remain usable without external map tiles.
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(container.current);
    return () => { observer.disconnect(); map.remove(); mapRef.current = null; };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setError(null); setBoundary(null);
    fetch(geojsonUrl, { signal: controller.signal }).then(response => {
      if (!response.ok) throw new Error('State boundaries could not be loaded.');
      return response.json();
    }).then(value => {
      const ids = value.features?.map(feature => feature.properties?.state_id);
      if (value.type !== 'FeatureCollection' || !ids?.length || ids.some(id => !/^[A-Z]{2}$/.test(id)) || new Set(ids).size !== ids.length) throw new Error('Invalid state-boundary identifiers.');
      if (!controller.signal.aborted) setBoundary(value);
    }).catch(reason => { if (!controller.signal.aborted) setError(reason.message); });
    return () => controller.abort();
  }, [geojsonUrl, retry]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !boundary) return;
    const lookup = buildStateLookup(states);
    const style = feature => {
      const state = matchState(feature.properties, lookup);
      const selected = state?.state_id === selectedStateId;
      return { fillColor: getStateColor(state, metric), color: selected ? '#1d4ed8' : '#64748b', weight: selected ? 3.5 : 1, fillOpacity: state?.status === 'available' ? .75 : .4 };
    };
    const layer = L.geoJSON(boundary, { style, onEachFeature: (feature, item) => {
      const state = matchState(feature.properties, lookup), id = stateSelectionId(states, feature.properties.state_id);
      const label = document.createElement('div');
      label.textContent = state ? state.state_name + ' · ' + (state.status === 'available'
        ? 'Estimated current depth: ' + state.current_gwl_m_bgl + ' m bgl. M+12 estimate: ' + state.forecast_12m_gwl_m_bgl + ' m bgl. Panel: ' + state.contributing_districts + '/' + state.total_districts + ' districts. Evidence: ' + Object.entries(state.evidence_tier_counts || {}).map(([tier,count]) => tier+': '+count).join(', ')
        : state.status === 'pending' ? 'Forecast summary loading. Select to load this state independently.'
          : state.status === 'summary_error' ? 'Forecast summary unavailable. Select to load this state independently.'
            : 'Forecast unavailable.') : 'State summary unavailable.';
      item.bindTooltip(label, { sticky: true });
      const select = () => { if (id) onSelectState?.(id); };
      item.on('click', select);
      item.on('mouseover', () => { item.setStyle({ weight: 3, color: '#2563eb' }); item.bringToFront(); });
      item.on('mouseout', () => item.setStyle(style(feature)));
      item.on('add', () => {
        const element = item.getElement();
        if (!element || !id) return;
        element.setAttribute('tabindex', '0');
        element.setAttribute('role', 'button');
        element.setAttribute('aria-label', 'Select ' + state.state_name);
        element.setAttribute('aria-pressed', String(id === selectedStateId));
        element.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(); } });
      });
    } }).addTo(map);
    map.fitBounds(layer.getBounds(), { padding: [12, 12] });
    return () => { map.removeLayer(layer); };
  }, [boundary, states, selectedStateId, metric, onSelectState]);
  const legend = metric === 'depth'
    ? [['#22c55e', '<5 m'], ['#eab308', '5–<10 m'], ['#f97316', '10–<20 m'], ['#ef4444', '≥20 m']]
    : [['#059669', '<−1 m'], ['#10b981', '−1 to 0 m'], ['#f59e0b', '>0 to 1 m'], ['#ef4444', '>1 m']];
  return <div className="state-map-wrapper">
    {error ? <p role="alert">{error} <button type="button" onClick={() => setRetry(value => value + 1)}>Retry boundaries</button></p> : !boundary && <p role="status">Loading state boundaries…</p>}
    <div ref={container} className="state-map-canvas" aria-label="India state boundaries; use the state selector as a keyboard alternative" />
    <div className="state-map-legend" aria-label={metric === 'depth' ? 'Estimated depth in metres below ground' : 'M+12 change in metres'}>
      {legend.concat([['#e2e8f0', states.some(state => ['pending', 'summary_error'].includes(state.status)) ? 'Summary pending / unavailable' : 'Unavailable']]).map(([color, label]) => <span key={label}><i style={{ background: color }} />{label}</span>)}
    </div>
  </div>;
}
