import { Link } from 'react-router-dom';

const tiers = [
  { id: 'A', label: 'Data-supported XGBoost', color: '#2563eb' },
  { id: 'B', label: 'Limited-history estimates', color: '#b45309' },
  { id: 'C', label: 'Zero-history references', color: '#64748b' },
  { id: 'D', label: 'Missing-weather estimates', color: '#c2410c' },
];

export function ForecastCoverage({ summary, loading, error, onRetry = () => {} }) {
  return <section aria-label="Published twelve-month forecast coverage" aria-busy={loading}>
    {summary && <p className="subtitle" role="status"><strong>{summary.districts_forecast} / {summary.districts_total} districts</strong> have 12 monthly outputs
      {' · '}{summary.available_states_count} states and UTs{' · '}As of {summary.as_of}. <Link to="/states">Explore state forecasts</Link></p>}
    {loading && <p role="status" className="compact-note">Loading published forecast coverage…</p>}
    {error && <p role="alert" className="compact-note">Forecast coverage is unavailable. District search remains available. <button className="alert-tab" type="button" onClick={onRetry}>Retry forecast coverage</button></p>}
    <div className="summary-cards">{tiers.map(tier => <article key={tier.id} className="summary-card" style={{ '--card-color': tier.color }}>
      <span className="card-icon">Tier {tier.id}</span>
      <div className="card-count" style={{ color: tier.color }}>{summary ? summary.evidence_tier_counts[tier.id] || 0 : '—'}</div>
      <div className="card-label">{tier.label}</div>
    </article>)}</div>
    {summary && <p className="compact-note">Forecasts and reference estimates have different evidence levels. Coverage does not establish accuracy. Open a district for values, historical ranges and limitations.</p>}
  </section>;
}

export function RiskIndexNotice({ loading, error, ready, onRetry = () => {} }) {
  if (ready || loading) return null;
  return <p className="compact-note" role="status">
    {error ? 'The separate risk index could not be loaded.' : 'The separate risk index has not been published for the current model and data.'}
    {' '}District search and twelve-month forecasts do not require risk scores.{' '}
    <button className="alert-tab" type="button" onClick={onRetry}>Check risk scores again</button>
  </p>;
}
