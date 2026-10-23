import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchScores } from '../api.js';
import { resolveDistrictSearch, searchDistricts } from './districtSearch.js';

export default function DistrictSearch({ placeholder = 'Search district or state…', compact = false }) {
  const navigate = useNavigate();
  const [districts, setDistricts] = useState([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [message, setMessage] = useState('');
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchScores()
      .then(data => {
        if (!Array.isArray(data.districts)) throw new Error('District list is unavailable.');
        if (!cancelled) { setDistricts(data.districts); setLoadError(''); }
      })
      .catch(error => {
        if (!cancelled) setLoadError(error.message || 'Could not load districts.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [retry]);

  const matches = useMemo(() => searchDistricts(districts, query, 7), [districts, query]);

  const openDistrict = district => {
    setQuery('');
    setMessage('');
    navigate(`/district/${encodeURIComponent(district.district_id)}`);
  };

  const submit = event => {
    event.preventDefault();
    const result = resolveDistrictSearch(districts, query);
    if (result.status === 'found') return openDistrict(result.district);
    if (result.status === 'ambiguous') {
      setMessage('More than one district matches. Choose a result with its state below.');
      return;
    }
    if (result.status === 'not-found') {
      setMessage('No matching district found. Try a district name, state, or ID.');
      return;
    }
    setMessage('Enter a district name or state.');
  };

  return (
    <div className={`district-search ${compact ? 'district-search-compact' : ''}`}>
      <form className="district-search-form" onSubmit={submit} role="search">
        <label className="sr-only" htmlFor={compact ? 'district-search-compact' : 'district-search-main'}>Search district</label>
        <input
          id={compact ? 'district-search-compact' : 'district-search-main'}
          type="search"
          value={query}
          onChange={event => { setQuery(event.target.value); setMessage(''); }}
          placeholder={loading ? 'Loading districts…' : placeholder}
          disabled={loading || Boolean(loadError)}
          autoComplete="off"
          aria-label="Search district by name, state, or ID"
          aria-describedby={message ? 'district-search-status' : undefined}
        />
        <button type="submit" disabled={loading || Boolean(loadError) || !query.trim()}>Open</button>
      </form>
      {loadError && <p className="district-search-status" role="alert">{loadError} <button type="button" onClick={() => setRetry(value => value + 1)}>Retry</button></p>}
      {message && <p className="district-search-status" id="district-search-status" role="status">{message}</p>}
      {query.trim().length >= 2 && matches.length > 0 && (
        <div className="district-search-results" role="listbox" aria-label="Matching districts">
          {matches.map(district => (
            <button type="button" role="option" aria-selected="false" key={district.district_id}
              onClick={() => openDistrict(district)}>
              <span>{district.name || district.district_id}</span>
              <small>{district.state || 'State unavailable'} · {district.district_id}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
