import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import { stateChartRows } from './stateForecastContract.js';

export const formatStateMonth = value => new Date(`${value.slice(0, 7)}-01T00:00:00Z`).toLocaleDateString('en', { month: 'short', year: 'numeric', timeZone: 'UTC' });
const depth = value => Number.isFinite(value) ? `${value.toFixed(2)} m bgl` : 'Unavailable';

export function StateForecastTooltip({ active, payload }) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  return <div className="state-chart-tooltip" role="tooltip"><strong>{formatStateMonth(row.month)}</strong>
    {Number.isFinite(row.observed) && <><p>Observed reporting-district mean: {depth(row.observed)}</p><p>Reporting districts: {row.districts ?? 'Unknown'} · {row.coverage ?? 'Unknown'}% coverage</p></>}
    {Number.isFinite(row.predicted) && <><p>Forecast estimate · M+{row.horizon}: {depth(row.predicted)}</p><p>Change from estimated anchor: {Number.isFinite(row.delta) ? `${row.delta >= 0 ? '+' : ''}${row.delta.toFixed(2)} m` : 'Unavailable'}</p></>}
    {!Number.isFinite(row.observed) && !Number.isFinite(row.predicted) && <p>No recorded value</p>}
  </div>;
}

export function stateForecastPlot(value, dimensions = {}) {
  return <LineChart {...dimensions} data={stateChartRows(value)} margin={{ top: 16, right: 18, bottom: 12, left: 4 }} accessibilityLayer>
    <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#e2e8f0" />
    <XAxis dataKey="month" tickFormatter={formatStateMonth} minTickGap={36} tickLine={false} />
    <YAxis width={68} tickLine={false} axisLine={false} label={{ value: 'Depth (m bgl)', angle: -90, position: 'insideLeft', fill: '#64748b' }} />
    <Tooltip filterNull={false} content={<StateForecastTooltip />} />
    <Legend />
    <Line dataKey="observed" name="Observed reporting-district mean" stroke="#94a3b8" strokeWidth={1.5} dot={{ r: 2 }} connectNulls={false} isAnimationActive={false} />
    <Line dataKey="predicted" name={value.model_version === '3.0-state-tiered' ? 'Mixed-method district mean' : 'XGBoost Forecast'} stroke="#2563eb" strokeWidth={2.5} dot={{ r: 3, fill: '#fff', strokeWidth: 2 }} activeDot={{ r: 5 }} connectNulls={false} isAnimationActive={false} />
  </LineChart>;
}

export default function StateForecastGraph({ forecastData = null, loading = false, error = null, onRetry = () => {} }) {
  return <section className="card state-chart-card" aria-label="Selected state forecast" aria-busy={loading}>
    <header className="section-heading"><div><h2>{forecastData?.state_name || 'Selected state'} forecast</h2><p className="muted">Next 12 full calendar months · metres below ground</p></div><span className="experimental-badge">Experimental</span></header>
    {loading ? <div className="forecast-placeholder" role="status"><span className="loading-spinner" />Loading state forecast…</div>
      : error ? <div className="inline-state error-state" role="alert"><p>{error}</p><button className="button button-secondary" type="button" onClick={onRetry}>Retry state forecast</button></div>
      : forecastData?.status !== 'forecast' ? <div className="inline-state" role="status"><h3>Forecast unavailable</h3><p>{forecastData?.message || forecastData?.unavailable_reason || 'Select a state to inspect available evidence.'}</p><button className="button button-secondary" type="button" onClick={onRetry}>Retry state forecast</button></div>
      : <><p className="forecast-note">A fixed panel of {forecastData.contributing_districts_count} district forecasts and reference estimates is averaged with equal weights. The current anchor is estimated, not a new measurement.</p>
        {forecastData.evidence_tier_counts && <p className="forecast-note" role="note">Evidence mix: {Object.entries(forecastData.evidence_tier_counts).map(([tier,count]) => `Tier ${tier}: ${count} (${(100*count/forecastData.total_districts_in_state).toFixed(1)}%)`).join(' · ')}. Tier A uses XGBoost; B/D use local persistence; C is a zero-history reference. Correlated donor errors prevent interpreting this average as a more reliable forecast.</p>}
        <div className="chart-caption"><span>{formatStateMonth(forecastData.forecast[0].target_date)}–{formatStateMonth(forecastData.forecast.at(-1).target_date)}</span><span>Higher depth = lower water level</span></div>
        <div className="state-chart"><ResponsiveContainer width="100%" height={330}>{stateForecastPlot(forecastData)}</ResponsiveContainer></div>
        <p className="forecast-note">History averages the districts reporting in each observed month; its composition can differ from the fixed forecast panel. Missing months remain gaps. Average depth does not measure groundwater volume.</p>
        <details className="monthly-values"><summary>View all 12 monthly estimates</summary><div className="table-scroll"><table className="data-table"><caption>{forecastData.state_name} · district mean · m bgl</caption><thead><tr><th scope="col">Month</th><th scope="col">Horizon</th><th scope="col">Depth (m bgl)</th><th scope="col">Change from estimated anchor (m)</th></tr></thead><tbody>{forecastData.forecast.map(row => <tr key={row.target_date}><th scope="row">{formatStateMonth(row.target_date)}</th><td>M+{row.horizon}</td><td>{row.predicted_gwl.toFixed(2)}</td><td>{row.delta_from_current_m >= 0 ? '+' : ''}{row.delta_from_current_m.toFixed(2)}</td></tr>)}</tbody></table></div></details>
        <details className="technical-details"><summary>Method, coverage and limitations</summary><p>Model: {forecastData.model_version}. Aggregation: {forecastData.aggregation_method}. Fixed panel: <code>{forecastData.panel_id}</code>.</p><p>As of {forecastData.as_of}; generated {forecastData.computed_at}. Predictions are experimental; independent prospective accuracy is unverified.</p>{Array.isArray(forecastData.limitations) && <ul>{forecastData.limitations.map(item => <li key={item}>{item}</li>)}</ul>}</details>
      </>}
  </section>;
}
