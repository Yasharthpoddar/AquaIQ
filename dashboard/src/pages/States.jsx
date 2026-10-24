import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import StateMapComponent from '../components/StateMapComponent';
import StateForecastGraph from '../components/StateForecastGraph';
import { fetchStatesSummary, fetchStatePredict } from '../api';
import '../App.css';

export default function States() {
  const { id: paramStateId } = useParams();
  const navigate = useNavigate();

  const [summaryData, setSummaryData] = useState(null);
  const [selectedStateId, setSelectedStateId] = useState(paramStateId?.toUpperCase() || 'UP');
  const [forecastData, setForecastData] = useState(null);
  const [metric, setMetric] = useState('depth'); // 'depth' | 'delta'
  const [loading, setLoading] = useState(true);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Fetch nationwide summary
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchStatesSummary(12)
      .then(data => {
        if (!cancelled) {
          setSummaryData(data);
          setLoading(false);
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(`Failed to load states summary: ${err.message}`);
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, []);

  // Sync paramStateId if URL changes
  useEffect(() => {
    if (paramStateId && paramStateId.toUpperCase() !== selectedStateId) {
      setSelectedStateId(paramStateId.toUpperCase());
    }
  }, [paramStateId]);

  // Fetch forecast for selected state
  useEffect(() => {
    if (!selectedStateId) return;

    let cancelled = false;
    setForecastLoading(true);

    fetchStatePredict(selectedStateId, 12)
      .then(data => {
        if (!cancelled) {
          setForecastData(data);
          setForecastLoading(false);
        }
      })
      .catch(err => {
        if (!cancelled) {
          setForecastData({
            state_id: selectedStateId,
            state_name: selectedStateId,
            status: 'insufficient_data',
            message: err.message,
          });
          setForecastLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [selectedStateId]);

  const handleSelectState = (stateId) => {
    const code = stateId.toUpperCase();
    setSelectedStateId(code);
    navigate(`/states/${code}`);
  };

  const statesList = summaryData?.states || [];
  const selectedStateSummary = statesList.find(s => s.state_id === selectedStateId);

  // Filtered states for ranking table
  const filteredStates = statesList.filter(s =>
    s.state_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.state_id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="page states-page" style={{ padding: '24px', maxWidth: '1280px', margin: '0 auto' }}>
      {/* Page Title & Experimental Header */}
      <div style={{ marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <h1 style={{ margin: 0, fontSize: '26px', color: '#0f172a' }}>State-Wise Groundwater Forecasting</h1>
          <span style={{ background: '#f3e8ff', color: '#7e22ce', fontSize: '12px', fontWeight: 600, padding: '3px 10px', borderRadius: '12px', border: '1px solid #d8b4fe' }}>
            Experimental 12-Month Outlook
          </span>
        </div>
        <p style={{ margin: '6px 0 0', color: '#64748b', fontSize: '14px' }}>
          Monitor regional groundwater conditions across 36 Indian States &amp; Union Territories, compare depletion rates, and drill down to individual districts.
        </p>
      </div>

      {/* Hydrogeological Metric Educational Banner */}
      <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '8px', padding: '12px 16px', marginBottom: '24px', display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
        <span style={{ fontSize: '20px' }}>ℹ️</span>
        <div style={{ fontSize: '13px', color: '#1e3a8a', lineHeight: 1.5 }}>
          <strong>Understanding Groundwater Depth:</strong> Groundwater levels are reported in <strong>metres below ground level (m bgl)</strong>.
          A <em>greater depth value indicates a deeper, more depleted water table (less available groundwater)</em>, whereas a smaller depth value indicates water is closer to the surface.
          A positive change (+Δm) represents water table depletion, while a negative change (-Δm) represents water table rise or recharge.
        </div>
      </div>

      {/* Control Bar: Metric Selector and State Dropdown */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', marginBottom: '20px', background: '#f8fafc', padding: '12px 18px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#334155' }}>Display Metric:</span>
          <div style={{ display: 'flex', background: '#e2e8f0', borderRadius: '6px', padding: '2px' }}>
            <button
              type="button"
              onClick={() => setMetric('depth')}
              style={{
                border: 'none',
                padding: '6px 14px',
                borderRadius: '5px',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
                background: metric === 'depth' ? '#ffffff' : 'transparent',
                color: metric === 'depth' ? '#0f172a' : '#64748b',
                boxShadow: metric === 'depth' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              }}
            >
              Groundwater Depth (m bgl)
            </button>
            <button
              type="button"
              onClick={() => setMetric('delta')}
              style={{
                border: 'none',
                padding: '6px 14px',
                borderRadius: '5px',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
                background: metric === 'delta' ? '#ffffff' : 'transparent',
                color: metric === 'delta' ? '#0f172a' : '#64748b',
                boxShadow: metric === 'delta' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              }}
            >
              12-Month Depth Change (Δm)
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#334155' }}>Select State:</span>
          <select
            value={selectedStateId}
            onChange={e => handleSelectState(e.target.value)}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '13px',
              background: '#ffffff',
              color: '#0f172a',
              cursor: 'pointer',
            }}
          >
            {statesList.map(s => (
              <option key={s.state_id} value={s.state_id}>
                {s.state_name} ({s.state_id}) {s.status !== 'available' ? '— Sparse Data' : ''}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div style={{ padding: '60px', textAlign: 'center', color: '#64748b' }}>
          Loading state groundwater data and boundaries...
        </div>
      ) : error ? (
        <div style={{ padding: '24px', background: '#fee2e2', color: '#b91c1c', borderRadius: '8px' }}>
          {error}
        </div>
      ) : (
        <>
          {/* Main Two-Column View: Map on Left, Selected State Profile on Right */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '24px', marginBottom: '32px' }}>
            {/* Left: Choropleth Map */}
            <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '16px', display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <h3 style={{ margin: 0, fontSize: '16px', color: '#0f172a' }}>India State Map</h3>
                <span style={{ fontSize: '12px', color: '#64748b' }}>Click a state to inspect forecast</span>
              </div>
              <div style={{ height: '500px', width: '100%' }}>
                <StateMapComponent
                  states={statesList}
                  selectedStateId={selectedStateId}
                  onSelectState={handleSelectState}
                  metric={metric}
                  geojsonUrl="/india_states.geojson"
                />
              </div>
            </div>

            {/* Right: Selected State Details & 12M Forecast Graph */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Stat Cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '12px' }}>
                <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px 14px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>Current Depth</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', marginTop: '4px' }}>
                    {selectedStateSummary?.current_gwl_m_bgl != null ? `${selectedStateSummary.current_gwl_m_bgl} m` : 'N/A'}
                  </div>
                  <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                    {selectedStateSummary?.last_observed_date || 'No recent obs'}
                  </div>
                </div>

                <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px 14px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>12M Forecast</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#7c3aed', marginTop: '4px' }}>
                    {selectedStateSummary?.forecast_12m_gwl_m_bgl != null ? `${selectedStateSummary.forecast_12m_gwl_m_bgl} m` : 'Unavailable'}
                  </div>
                  <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                    Horizon M+12
                  </div>
                </div>

                <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px 14px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>12M Projected Change</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: selectedStateSummary?.projected_change_12m_m > 0 ? '#dc2626' : '#16a34a', marginTop: '4px' }}>
                    {selectedStateSummary?.projected_change_12m_m != null ? `${selectedStateSummary.projected_change_12m_m >= 0 ? '+' : ''}${selectedStateSummary.projected_change_12m_m} m` : 'N/A'}
                  </div>
                  <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                    {selectedStateSummary?.projected_change_12m_m > 0 ? 'Water table drop' : 'Water table rise'}
                  </div>
                </div>

                <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px 14px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>District Coverage</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', marginTop: '4px' }}>
                    {selectedStateSummary?.contributing_districts || 0} / {selectedStateSummary?.total_districts || 0}
                  </div>
                  <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                    {selectedStateSummary?.district_coverage_pct || 0}% contributing
                  </div>
                </div>
              </div>

              {/* State Forecast Graph */}
              {forecastLoading ? (
                <div style={{ padding: '60px', textAlign: 'center', background: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', color: '#64748b' }}>
                  Loading 12-month projection for {selectedStateId}...
                </div>
              ) : (
                <StateForecastGraph forecastData={forecastData} />
              )}
            </div>
          </div>

          {/* District Drill-Down Section */}
          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '20px', marginBottom: '32px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '17px', color: '#0f172a' }}>
                  Districts in {selectedStateSummary?.state_name || selectedStateId} ({forecastData?.districts?.length || 0})
                </h3>
                <span style={{ fontSize: '12px', color: '#64748b' }}>
                  Drill down into individual district-level conditions, 6-month projections, and experimental 12-month models.
                </span>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '10px' }}>
              {(forecastData?.districts || []).map(distId => {
                const parts = distId.split('-');
                const distName = parts.length > 1 ? parts[1].replace(/_/g, ' ') : distId;
                return (
                  <Link
                    key={distId}
                    to={`/district/${encodeURIComponent(distId)}`}
                    style={{
                      display: 'block',
                      padding: '10px 12px',
                      background: '#f8fafc',
                      border: '1px solid #e2e8f0',
                      borderRadius: '6px',
                      textDecoration: 'none',
                      color: '#0f172a',
                      transition: 'border-color 0.15s, background 0.15s',
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.borderColor = '#2563eb';
                      e.currentTarget.style.background = '#eff6ff';
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.borderColor = '#e2e8f0';
                      e.currentTarget.style.background = '#f8fafc';
                    }}
                  >
                    <div style={{ fontWeight: 600, fontSize: '13px' }}>{distName}</div>
                    <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>{distId}</div>
                  </Link>
                );
              })}
            </div>
          </div>

          {/* Comparative National Ranking Table */}
          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '17px', color: '#0f172a' }}>All-India State Groundwater Comparison</h3>
                <span style={{ fontSize: '12px', color: '#64748b' }}>
                  National comparative table of all 36 States &amp; Union Territories.
                </span>
              </div>
              <input
                type="text"
                placeholder="Filter by state name or code..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                style={{
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '13px',
                  width: '240px',
                }}
              />
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #e2e8f0', background: '#f8fafc', color: '#475569' }}>
                    <th style={{ padding: '10px 12px' }}>Rank (Depth)</th>
                    <th style={{ padding: '10px 12px' }}>State / UT</th>
                    <th style={{ padding: '10px 12px' }}>Code</th>
                    <th style={{ padding: '10px 12px' }}>Reporting Districts</th>
                    <th style={{ padding: '10px 12px' }}>Current Depth</th>
                    <th style={{ padding: '10px 12px' }}>12M Forecast</th>
                    <th style={{ padding: '10px 12px' }}>12M Change</th>
                    <th style={{ padding: '10px 12px' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredStates.map(s => {
                    const isSelected = s.state_id === selectedStateId;
                    return (
                      <tr
                        key={s.state_id}
                        onClick={() => handleSelectState(s.state_id)}
                        style={{
                          borderBottom: '1px solid #f1f5f9',
                          cursor: 'pointer',
                          background: isSelected ? '#eff6ff' : 'transparent',
                        }}
                      >
                        <td style={{ padding: '10px 12px', fontWeight: 600, color: '#64748b' }}>
                          {s.depth_rank != null ? `#${s.depth_rank}` : '—'}
                        </td>
                        <td style={{ padding: '10px 12px', fontWeight: 600, color: isSelected ? '#1d4ed8' : '#0f172a' }}>
                          {s.state_name}
                        </td>
                        <td style={{ padding: '10px 12px', color: '#64748b' }}>
                          {s.state_id}
                        </td>
                        <td style={{ padding: '10px 12px' }}>
                          {s.contributing_districts} / {s.total_districts} ({s.district_coverage_pct}%)
                        </td>
                        <td style={{ padding: '10px 12px', fontWeight: 600 }}>
                          {s.current_gwl_m_bgl != null ? `${s.current_gwl_m_bgl.toFixed(2)} m bgl` : '—'}
                        </td>
                        <td style={{ padding: '10px 12px' }}>
                          {s.forecast_12m_gwl_m_bgl != null ? `${s.forecast_12m_gwl_m_bgl.toFixed(2)} m bgl` : '—'}
                        </td>
                        <td style={{
                          padding: '10px 12px',
                          fontWeight: 600,
                          color: s.projected_change_12m_m > 0 ? '#dc2626' : s.projected_change_12m_m < 0 ? '#16a34a' : '#64748b'
                        }}>
                          {s.projected_change_12m_m != null ? `${s.projected_change_12m_m >= 0 ? '+' : ''}${s.projected_change_12m_m.toFixed(2)} m` : '—'}
                        </td>
                        <td style={{ padding: '10px 12px' }}>
                          {s.status === 'available' ? (
                            <span style={{ background: '#dcfce7', color: '#166534', padding: '3px 8px', borderRadius: '10px', fontSize: '11px', fontWeight: 600 }}>
                              Available
                            </span>
                          ) : (
                            <span style={{ background: '#f1f5f9', color: '#64748b', padding: '3px 8px', borderRadius: '10px', fontSize: '11px', fontWeight: 500 }}>
                              Sparse Data
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
