import { medianMethodLabel } from './stateMedianForecastContract.js';

const depth = value => Number.isFinite(value) ? `${value.toFixed(2)} m bgl` : 'Unavailable';
const change = value => Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${value.toFixed(2)} m` : 'Unavailable';
const statusLabel = row => row.status === 'available' ? 'Forecast available' : row.forecast_method === 'no_observations' ? 'No observations' : row.status === 'insufficient_data' ? 'Insufficient history' : 'Model unavailable';

export default function StateMedianSummaryTable({ states, selectedId, onSelect }) {
  return <div className="table-scroll state-summary-scroll" role="region" aria-label="State comparison table" tabIndex={0}>
    <table className="data-table"><caption>State median groundwater forecasts · m bgl · changes use each state's dated historical reference</caption>
      <thead><tr><th scope="col">State / UT</th><th scope="col">Method</th><th scope="col">Reference coverage</th><th scope="col">Observed reference median</th><th scope="col">M+12 median estimate</th><th scope="col">Change from reference (m)</th><th scope="col">Status</th></tr></thead>
      <tbody>{states.map(row => <tr key={row.state_id} aria-selected={row.state_id === selectedId}>
        <th scope="row"><button type="button" className="state-name-button" onClick={() => onSelect(row.state_id)}>{row.state_name}<small>{row.state_id}</small></button></th>
        <td>{medianMethodLabel(row)}</td>
        <td>{row.contributing_districts_count} / {row.total_districts_in_state} districts<br /><small>{row.district_coverage_pct.toFixed(1)}% coverage</small></td>
        <td>{depth(row.last_observed_gwl_m_bgl)}<br /><small>{row.historical_reference_date || 'No genuine reference'}{Number.isInteger(row.reference_age_months) ? ` · ${row.reference_age_months} months old` : ''}</small>{row.reference_training_eligible === false && row.historical_reference_date && <small>Below training-target coverage</small>}</td>
        <td>{depth(row.forecast_12m_gwl_m_bgl)}</td><td>{change(row.projected_change_12m_m)}</td>
        <td><span className={`state-status ${row.status === 'available' ? 'available' : ''}`}>{statusLabel(row)}</span></td>
      </tr>)}</tbody>
    </table>{!states.length && <p className="inline-state" role="status">No states match this filter.</p>}
  </div>;
}
