import { useEffect, useState } from 'react';
import { fetchResearchCatalog, fetchResearchForecast } from '../api';
import { formatResearchDepth, validateResearchCatalog, validateResearchForecast } from './researchForecastContract';

/** File-only research reads; independent of legacy scoring and its database. */
export default function ResearchForecast({ districtId = null }) {
  const [catalog, setCatalog] = useState(null);
  const [catalogError, setCatalogError] = useState(null);
  const [selectedDistrict, setSelectedDistrict] = useState('');
  const [origin, setOrigin] = useState('');
  const [requestedOrigin, setRequestedOrigin] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const effectiveDistrict = districtId || selectedDistrict;

  useEffect(() => {
    let cancelled = false;
    fetchResearchCatalog().then(validateResearchCatalog).then(data => {
      if (cancelled) return;
      setCatalog(data); setCatalogError(null);
      setSelectedDistrict(previous => previous || data.districts.find(row => row.district_id === 'TS-Adilabad')?.district_id || data.districts[0]?.district_id || '');
      if (!districtId && !data.districts.length) setLoading(false);
    }).catch(err => { if (!cancelled) { setCatalogError(err.message); if (!districtId) setLoading(false); } });
    return () => { cancelled = true; };
  }, [districtId, retry]);

  useEffect(() => {
    if (!effectiveDistrict) return;
    let cancelled = false;
    setLoading(true); setError(null); setResult(null);
    fetchResearchForecast(effectiveDistrict, requestedOrigin).then(validateResearchForecast).then(data => {
      if (cancelled) return;
      setResult(data); setOrigin(data.origin_month || ''); setLoading(false);
    }).catch(err => { if (!cancelled) { setError(err.message); setLoading(false); } });
    return () => { cancelled = true; };
  }, [effectiveDistrict, requestedOrigin, retry]);

  const selected = catalog?.districts.find(row => row.district_id === effectiveDistrict);
  return <section className="card" aria-label="Primary twelve-month research forecast" style={{padding:'1.25rem',margin:'1.5rem 0'}}>
    <h2>Primary research: 12 calendar months ahead</h2>
    <p>Can an estimate for an observed origin month improve on the same observed depth one year later? This is a direct M+12 target, separate from the six-month monthly climate projection.</p>
    {!districtId && catalog && <p>
      <label htmlFor="research-district">Research district: </label>
      <select id="research-district" value={selectedDistrict} onChange={event => {
        setSelectedDistrict(event.target.value); setRequestedOrigin(null); setOrigin('');
      }}>{catalog.districts.map(row => <option key={row.district_id} value={row.district_id}>{row.name || row.district_id}{row.state ? `, ${row.state}` : ''}</option>)}</select>
    </p>}
    {catalog && !catalog.districts.length && <p role="status">The local research catalog has no source-backed districts. Required research assets are unavailable.</p>}
    {catalogError && <p role="alert">Research catalog unavailable: {catalogError}</p>}
    {effectiveDistrict && <form onSubmit={event => { event.preventDefault(); setRequestedOrigin(origin || null); setRetry(value => value + 1); }} style={{margin:'1rem 0'}}>
      <label htmlFor={`research-origin-${districtId || 'home'}`}>Observed origin month: </label>
      <input id={`research-origin-${districtId || 'home'}`} type="month" value={origin} onChange={event => setOrigin(event.target.value)} />{' '}
      <button type="submit">Inspect research estimate</button>{' '}
      <button type="button" onClick={() => { setRequestedOrigin(null); setRetry(value => value + 1); }}>Latest observed origin</button>
      {selected && <p>Latest source-backed month: {selected.latest_observed_month || 'Unavailable'}. A historical month can be inspected explicitly; unavailable current inputs never trigger a silent fallback to an older month.</p>}
    </form>}
    {loading && <p role="status">Loading twelve-month research evidence…</p>}
    {error && <div role="alert"><p>{error}</p><button type="button" onClick={() => setRetry(value => value + 1)}>Retry research evidence</button></div>}
    {result && <ResearchForecastEvidence result={result} />}
    <p>Saved 792-case regional historical comparison: annual baseline RMSE 1.458 m, expanding XGBoost 1.420 m. The difference interval (−0.317 to +0.264 m) crosses zero and sensitivity analyses reverse the apparent advantage. These results do not validate this separate fixed-cutoff artifact or future forecasts. HGB remains blocked from real shadow prediction.</p>
    <p>This fixed-cutoff artifact's own 24-case Adilabad historical check favored the annual baseline: baseline RMSE 0.877 m versus ML 2.664 m (MAE 0.645 versus 2.145 m). These previously inspected cases establish no prospective skill.</p>
  </section>;
}

export function ResearchForecastEvidence({ result }) {
  return <>
      <p><strong>Origin:</strong> {result.origin_month || 'Unavailable'} · <strong>Target (M+12):</strong> {result.target_month || 'Unavailable'}</p>
      <p><strong>Output:</strong> {result.output_kind === 'historical_research' ? 'Historical research estimate' : 'Current-vintage research estimate'} · no prospective forecast has been issued.</p>
      <div style={{overflowX:'auto',margin:'1rem 0'}}><table style={{width:'100%',textAlign:'left'}}>
        <caption style={{textAlign:'left'}}>Direct target-month comparison; depths in metres below ground level</caption>
        <thead><tr><th scope="col">Method</th><th scope="col">Target-month depth</th></tr></thead>
        <tbody>
          <tr><th scope="row">Fixed-settings research ML candidate</th><td>{formatResearchDepth(result.ml_estimate_m)}</td></tr>
          <tr><th scope="row">Annual baseline (persistence = annual seasonal naive)</th><td>{formatResearchDepth(result.annual_baseline_m)}</td></tr>
          {Number.isFinite(result.observed_target_m) && <tr><th scope="row">Source-backed historical target measurement</th><td>{formatResearchDepth(result.observed_target_m)}</td></tr>}
        </tbody>
      </table></div>
      {result.unavailable_reasons.map(message => <p key={message} role="status">{message}</p>)}
      <p><strong>Supported model scope:</strong> {result.scope?.description || 'Unavailable'}{result.scope?.supported_district_ids?.length ? ` (${result.scope.supported_district_ids.join(', ')})` : ''}. Scope does not establish nationwide accuracy.</p>
      <p><strong>Source:</strong> {result.source?.name || 'Unavailable'} · latest source-backed month: {result.source?.latest_observed_month || 'Unavailable'}.</p>
      <p><strong>Origin evidence:</strong> {result.source?.origin_is_observed === true ? 'source-backed observation' : 'not an eligible observed origin'}; {result.source?.origin_is_imputed === true ? 'imputed' : result.source?.origin_is_imputed === false ? 'not imputed' : 'imputation status unknown'}.</p>
      <p><strong>Reported dates:</strong> {result.source?.reported_date_start || 'Unknown'} to {result.source?.reported_date_end || 'Unknown'} · well count: {result.source?.well_count ?? 'Unknown'}.</p>
      <p>Reported dates and month labels do not certify acquisition or model-availability times. Datum and physical well continuity remain unverified. Twelve calendar months does not establish twelve full months of operational lead.</p>
      {!!result.source?.input_flags?.length && <details>
        <summary>Input provenance and missingness</summary>
        <div style={{overflowX:'auto'}}><table style={{width:'100%',textAlign:'left'}}>
          <thead><tr><th scope="col">Input</th><th scope="col">Evidence status</th><th scope="col">Source month</th><th scope="col">Age (months)</th></tr></thead>
          <tbody>{result.source.input_flags.map((flag, index) => <tr key={`${flag.feature}-${index}`}>
            <th scope="row">{flag.feature}</th><td>{String(flag.status || 'unknown').replaceAll('_', ' ')}</td><td>{flag.source_month || 'Unknown'}</td><td>{flag.age_months ?? 'Unknown'}</td>
          </tr>)}</tbody>
        </table></div>
      </details>}
      {result.model && <details><summary>Research artifact identity</summary>
        <p>Family: {result.model.family || 'Unavailable'} · observed training-target cutoff: {result.model.train_target_cutoff || 'Unavailable'}.</p>
        {['model_sha256','card_sha256','configuration_sha256','protocol_sha256','feature_generation_id'].map(field => <p key={field} style={{overflowWrap:'anywhere'}}>{field}: {result.model[field] || 'Unavailable'}</p>)}
      </details>}
      {result.limitations.map(message => <p key={message}>{message}</p>)}
    </>;
}
