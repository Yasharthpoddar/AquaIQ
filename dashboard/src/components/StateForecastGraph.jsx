import { useState } from 'react';

/**
 * StateForecastGraph — Line chart visualising historical observations and 12-month projections
 *
 * Props:
 *   forecastData: Forecast response object from /api/predict/state/<state_id>
 */

export default function StateForecastGraph({ forecastData }) {
  const [hoveredPoint, setHoveredPoint] = useState(null);

  if (!forecastData || forecastData.status !== 'forecast') {
    return (
      <div className="forecast-unavailable-card" style={{ padding: '24px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0', textAlign: 'center', color: '#64748b' }}>
        <p style={{ fontWeight: 600, fontSize: '15px', color: '#334155', marginBottom: '6px' }}>
          {forecastData?.state_name || 'State'} 12-Month Projection Unavailable
        </p>
        <p style={{ fontSize: '13px' }}>
          {forecastData?.message || forecastData?.unavailable_reason || 'Insufficient historical observation rounds for state time-series projection.'}
        </p>
      </div>
    );
  }

  const history = forecastData.history || [];
  const forecast = forecastData.forecast || [];
  const lastObsVal = forecastData.last_observed_gwl_m_bgl ?? history[history.length - 1]?.gwl_m_bgl;

  // Build unified points list for chart
  // History: { date, val, type: 'history' }
  // Forecast: { date, val, type: 'forecast', baselines }
  const histPoints = history.map(h => ({
    date: h.date,
    label: h.date.slice(0, 7),
    val: h.gwl_m_bgl,
    type: 'history',
    districts: h.contributing_districts_count,
    coverage: h.district_coverage_pct,
  }));

  const fcPoints = forecast.map(f => ({
    date: f.target_date,
    label: f.target_date.slice(0, 7),
    val: f.predicted_gwl,
    delta: f.delta_from_current_m,
    persistence: f.baselines?.persistence,
    seasonal: f.baselines?.seasonal_naive,
    type: 'forecast',
    horizon: f.horizon,
  }));

  // Chart layout dimensions
  const width = 720;
  const height = 300;
  const padLeft = 55;
  const padRight = 30;
  const padTop = 25;
  const padBottom = 45;

  const allVals = [
    ...histPoints.map(p => p.val),
    ...fcPoints.map(p => p.val),
    ...fcPoints.map(p => p.persistence).filter(Number.isFinite),
    ...fcPoints.map(p => p.seasonal).filter(Number.isFinite),
  ].filter(Number.isFinite);

  const minVal = Math.max(0, Math.floor(Math.min(...allVals) - 1));
  const maxVal = Math.ceil(Math.max(...allVals) + 1);
  const valRange = maxVal - minVal || 1;

  // Combine x-axis points
  const combinedPoints = [...histPoints, ...fcPoints];
  const numPoints = combinedPoints.length;

  const getX = index => padLeft + (index / (numPoints - 1 || 1)) * (width - padLeft - padRight);
  const getY = val => padTop + ((maxVal - val) / valRange) * (height - padTop - padBottom);

  // SVG paths
  // 1. History line
  const histPathD = histPoints.length > 0
    ? histPoints.reduce((acc, p, i) => `${acc} ${i === 0 ? 'M' : 'L'} ${getX(i)} ${getY(p.val)}`, '')
    : '';

  // 2. Forecast line (connect from last history point)
  const fcStartIndex = histPoints.length - 1;
  let fcPathD = '';
  if (fcPoints.length > 0) {
    if (fcStartIndex >= 0) {
      fcPathD = `M ${getX(fcStartIndex)} ${getY(histPoints[fcStartIndex].val)}`;
    }
    fcPoints.forEach((p, i) => {
      const idx = histPoints.length + i;
      fcPathD += ` ${fcPathD ? 'L' : 'M'} ${getX(idx)} ${getY(p.val)}`;
    });
  }

  // 3. Seasonal baseline line across forecast horizon
  let seasonalPathD = '';
  if (fcPoints.length > 0) {
    fcPoints.forEach((p, i) => {
      if (Number.isFinite(p.seasonal)) {
        const idx = histPoints.length + i;
        seasonalPathD += ` ${seasonalPathD ? 'L' : 'M'} ${getX(idx)} ${getY(p.seasonal)}`;
      }
    });
  }

  // Y-axis tick marks
  const numTicks = 5;
  const yTicks = Array.from({ length: numTicks }, (_, i) => minVal + (i * valRange) / (numTicks - 1));

  return (
    <div className="state-forecast-graph-container" style={{ background: '#ffffff', padding: '16px 20px', borderRadius: '8px', border: '1px solid #e2e8f0', marginTop: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
        <div>
          <h4 style={{ margin: 0, fontSize: '16px', color: '#0f172a' }}>
            {forecastData.state_name} — 12-Month Groundwater Depth Outlook
          </h4>
          <span style={{ fontSize: '12px', color: '#64748b' }}>
            Origin: {forecastData.forecast_origin} · Units: <strong>m bgl</strong> (metres below ground level)
          </span>
        </div>
        <div style={{ display: 'flex', gap: '14px', alignItems: 'center', fontSize: '12px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '12px', height: '3px', background: '#2563eb' }} />
            <span>Observed History</span>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '12px', height: '3px', background: '#7c3aed', borderTop: '2px dashed #7c3aed' }} />
            <span>12M Projection</span>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '12px', height: '2px', background: '#d97706', borderTop: '2px dotted #d97706' }} />
            <span>Seasonal Baseline</span>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '12px', height: '2px', background: '#94a3b8', borderTop: '1px dashed #94a3b8' }} />
            <span>Persistence</span>
          </span>
        </div>
      </div>

      <div style={{ position: 'relative', width: '100%', overflowX: 'auto' }}>
        <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', minWidth: '550px' }}>
          {/* Grid lines and Y axis ticks */}
          {yTicks.map(t => {
            const y = getY(t);
            return (
              <g key={t}>
                <line x1={padLeft} y1={y} x2={width - padRight} y2={y} stroke="#f1f5f9" strokeWidth="1" />
                <text x={padLeft - 8} y={y + 4} textAnchor="end" fontSize="11" fill="#64748b">
                  {t.toFixed(1)}m
                </text>
              </g>
            );
          })}

          {/* Persistence baseline line */}
          {Number.isFinite(lastObsVal) && (
            <line
              x1={getX(histPoints.length)}
              y1={getY(lastObsVal)}
              x2={getX(numPoints - 1)}
              y2={getY(lastObsVal)}
              stroke="#94a3b8"
              strokeWidth="1.5"
              strokeDasharray="4 3"
            />
          )}

          {/* Seasonal baseline line */}
          {seasonalPathD && (
            <path d={seasonalPathD} fill="none" stroke="#d97706" strokeWidth="1.8" strokeDasharray="3 3" opacity="0.85" />
          )}

          {/* History path */}
          {histPathD && (
            <path d={histPathD} fill="none" stroke="#2563eb" strokeWidth="2.5" />
          )}

          {/* Forecast path */}
          {fcPathD && (
            <path d={fcPathD} fill="none" stroke="#7c3aed" strokeWidth="2.5" strokeDasharray="5 4" />
          )}

          {/* Forecast separator vertical line */}
          {fcStartIndex >= 0 && (
            <line
              x1={getX(fcStartIndex)}
              y1={padTop}
              x2={getX(fcStartIndex)}
              y2={height - padBottom}
              stroke="#cbd5e1"
              strokeWidth="1.2"
              strokeDasharray="2 2"
            />
          )}

          {/* History circles */}
          {histPoints.map((p, i) => (
            <circle
              key={p.date}
              cx={getX(i)}
              cy={getY(p.val)}
              r="3.5"
              fill="#2563eb"
              stroke="#ffffff"
              strokeWidth="1.5"
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setHoveredPoint({ ...p, x: getX(i), y: getY(p.val) })}
              onMouseLeave={() => setHoveredPoint(null)}
            />
          ))}

          {/* Forecast circles */}
          {fcPoints.map((p, i) => {
            const idx = histPoints.length + i;
            return (
              <circle
                key={p.date}
                cx={getX(idx)}
                cy={getY(p.val)}
                r="4.5"
                fill="#7c3aed"
                stroke="#ffffff"
                strokeWidth="1.5"
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => setHoveredPoint({ ...p, x: getX(idx), y: getY(p.val) })}
                onMouseLeave={() => setHoveredPoint(null)}
              />
            );
          })}

          {/* X axis labels (sparse) */}
          {combinedPoints.map((p, i) => {
            // Show label every few points or at key boundaries
            if (i % Math.ceil(numPoints / 7) === 0 || i === histPoints.length - 1 || i === numPoints - 1) {
              return (
                <text
                  key={p.date}
                  x={getX(i)}
                  y={height - padBottom + 18}
                  textAnchor="middle"
                  fontSize="10"
                  fill="#64748b"
                >
                  {p.label}
                </text>
              );
            }
            return null;
          })}
        </svg>

        {/* Hover Tooltip Popup */}
        {hoveredPoint && (
          <div
            style={{
              position: 'absolute',
              left: `${Math.min(hoveredPoint.x + 10, width - 180)}px`,
              top: `${Math.max(hoveredPoint.y - 80, 5)}px`,
              background: 'rgba(15, 23, 42, 0.92)',
              color: '#ffffff',
              padding: '8px 12px',
              borderRadius: '6px',
              fontSize: '12px',
              pointerEvents: 'none',
              boxShadow: '0 4px 12px rgba(0,0,0,0.25)',
              zIndex: 10,
              minWidth: '150px',
            }}
          >
            <div style={{ fontWeight: 600, borderBottom: '1px solid rgba(255,255,255,0.2)', paddingBottom: '3px', marginBottom: '4px' }}>
              {hoveredPoint.date} ({hoveredPoint.type === 'history' ? 'Observed' : `Horizon M+${hoveredPoint.horizon}`})
            </div>
            <div>Depth: <strong>{hoveredPoint.val.toFixed(2)} m bgl</strong></div>
            {hoveredPoint.type === 'forecast' && (
              <>
                <div>Change: <strong>{hoveredPoint.delta >= 0 ? '+' : ''}{hoveredPoint.delta.toFixed(2)} m</strong></div>
                {Number.isFinite(hoveredPoint.seasonal) && (
                  <div style={{ color: '#fde68a' }}>Seasonal Naive: {hoveredPoint.seasonal.toFixed(2)} m</div>
                )}
                {Number.isFinite(hoveredPoint.persistence) && (
                  <div style={{ color: '#cbd5e1' }}>Persistence: {hoveredPoint.persistence.toFixed(2)} m</div>
                )}
              </>
            )}
            {hoveredPoint.type === 'history' && (
              <div style={{ color: '#93c5fd' }}>
                Coverage: {hoveredPoint.districts} districts ({hoveredPoint.coverage}%)
              </div>
            )}
          </div>
        )}
      </div>

      {/* Experimental Evaluation & Limitations Notice */}
      <div style={{ marginTop: '14px', padding: '10px 14px', background: '#f8fafc', borderRadius: '6px', borderLeft: '3px solid #7c3aed', fontSize: '12px', color: '#475569' }}>
        <strong>Experimental Notice:</strong> State projection is an empirical time-series outlook (Approach A1, MAE: 1.94 m vs Persistence: 2.56 m).
        In hydrogeology, <strong>greater depth below ground level (m bgl) indicates lower groundwater availability</strong>. Local water management should inspect individual reporting districts.
      </div>
    </div>
  );
}
