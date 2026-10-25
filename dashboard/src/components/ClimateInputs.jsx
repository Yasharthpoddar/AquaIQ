import { useEffect, useState } from 'react';
import { CLIMATE_FIELDS, loadClimateInputs } from './climateInputs.js';

const monthLabel = month => {
  const [year, number] = month.slice(0, 7).split('-').map(Number);
  return new Date(Date.UTC(year, number - 1, 1)).toLocaleDateString('en', {month:'short',year:'numeric',timeZone:'UTC'});
};
const numberLabel = value => Number.isFinite(value) ? value.toFixed(2) : 'Unavailable';

export function ClimateInputsView({ districtId, data = null, loading = false, error = null, onRetry = () => {} }) {
  return <section className="card forecast-card" aria-label="Rainfall, temperature and evapotranspiration inputs" aria-busy={loading}>
    <header className="section-heading"><div><h2>Rainfall &amp; climate inputs</h2><p className="muted">Existing six-month model · assumed weather, not weather predictions</p></div><span className="experimental-badge">Model input assumptions</span></header>
    <p className="forecast-note">These inputs belong to the separate six-month XGBoost groundwater model. The 12-month XGBoost outlook has its own monthly weather inputs.</p>
    {loading && <p className="inline-state" role="status">Loading rainfall, temperature and evapotranspiration inputs…</p>}
    {error && <div className="inline-state error-state" role="alert"><p>{error}</p><button className="button button-secondary" type="button" onClick={onRetry}>Retry climate inputs</button></div>}
    {data && <>
      <div className="forecast-context"><span>{districtId} · As of {data.asOf}</span><span>{data.methodLabel}</span></div>
      {data.status === 'unavailable' ? <div className="inline-state" role="status"><h3>Climate inputs unavailable</h3><p>{data.message}</p><button className="button button-secondary" type="button" onClick={onRetry}>Retry climate inputs</button></div> : <>
        {data.estimateType === 'zone_fallback' && <p className="availability-reason" role="status">Uses zone-based history: {data.sourceZone || 'zone name unavailable'}.</p>}
        {data.partial && <p className="availability-reason" role="status">Some inputs were not available in the response. Missing values are shown as unavailable.</p>}
        <div className="table-scroll" role="region" aria-label="Six-month weather input table" tabIndex={0}>
          <table className="data-table"><caption>Assumed weather inputs for {monthLabel(data.rows[0].month)}–{monthLabel(data.rows.at(-1).month)} · not observed future weather</caption>
            <thead><tr><th scope="col">Month</th>{CLIMATE_FIELDS.map(field => <th scope="col" key={field.key}>{field.label}<br /><span className="muted">{field.unit}</span></th>)}</tr></thead>
            <tbody>{data.rows.map(row => <tr key={row.month}><th scope="row">{monthLabel(row.month)}</th>{CLIMATE_FIELDS.map(field => <td key={field.key}>{numberLabel(row[field.key])}</td>)}</tr>)}</tbody>
          </table>
        </div>
        <p className="compact-note">Only six months are supplied by this model. Evapotranspiration is available; a separate evaporation forecast is not provided.</p>
        <details className="technical-details"><summary>Source dates &amp; origin inputs</summary>
          <p>Latest usable historical feature month for each input. These dates do not certify acquisition or publication times.</p>
          <div className="table-scroll"><table className="data-table"><caption>Weather source history</caption><thead><tr><th scope="col">Input</th><th scope="col">Latest usable month</th></tr></thead><tbody>{CLIMATE_FIELDS.map(field => <tr key={field.key}><th scope="row">{field.label}</th><td>{data.sourceDates[field.key] ? monthLabel(data.sourceDates[field.key]) : 'Unknown'}</td></tr>)}</tbody></table></div>
          <p>{data.includesFilledHistory === true ? 'Usable weather history may include forward-filled values.' : data.includesFilledHistory === false ? 'Weather fill flags were used to exclude filled history.' : 'Weather-history imputation status is unknown.'}</p>
          {data.origin && <><h3>Origin-month weather inputs · {monthLabel(data.origin.month)}</h3><p>{data.origin.basisLabel}</p><div className="table-scroll"><table className="data-table"><caption>Values exposed for the separate model’s origin month</caption><thead><tr><th scope="col">Input</th><th scope="col">Value</th><th scope="col">Unit</th></tr></thead><tbody>{CLIMATE_FIELDS.map(field => <tr key={field.key}><th scope="row">{field.label}</th><td>{numberLabel(data.origin[field.key])}</td><td>{field.unit}</td></tr>)}</tbody></table></div></>}
          <p>Exact groundwater lag and cumulative feature-vector values are not returned by this endpoint. No pumping or extraction forecast is supplied.</p>
        </details>
      </>}
    </>}
  </section>;
}

export default function ClimateInputs({ districtId, asOf }) {
  const identity = `${districtId}|${asOf}`;
  const [state, setState] = useState({identity:null,data:null,error:null,loading:true});
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setState({identity,data:null,error:null,loading:true});
    loadClimateInputs(districtId, asOf).then(data => {
      if (!cancelled) setState({identity,data,error:null,loading:false});
    }).catch(error => {
      if (!cancelled) setState({identity,data:null,error:error?.message || 'Climate inputs could not be loaded.',loading:false});
    });
    return () => { cancelled = true; };
  }, [districtId, asOf, identity, retry]);
  const current = state.identity === identity ? state : {data:null,error:null,loading:true};
  return <ClimateInputsView districtId={districtId} data={current.data} loading={current.loading} error={current.error} onRetry={() => setRetry(value => value + 1)} />;
}
