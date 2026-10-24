import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { districtSearchKeyAction, districtSearchLabel, resolveDistrictSearch, searchDistricts } from './districtSearch.js';

const messages = {
  empty: 'Enter a district name, state, or ID.',
  ambiguous: 'Several districts match. Choose a district with its state and ID below.',
  'not-found': 'No matching district. Try a district name, state, or canonical ID.',
};

/** Stateless markup also lets tests exercise actual option callbacks and ARIA states. */
export function DistrictSearchView({ id, label = 'Search district', placeholder = 'District, state or ID',
  query = '', matches = [], totalMatches = matches.length, open = false, activeIndex = -1,
  loading = false, error = null, disabled = false, status = '', onQueryChange = () => {},
  onSelect = () => {}, onSubmit = () => {}, onKeyDown = () => {}, onFocus = () => {},
  onBlur = () => {}, onRetry, activeOptionRef }) {
  const unavailable = disabled || loading || Boolean(error);
  const showResults = open && !unavailable && matches.length > 0;
  const empty = open && !unavailable && query.trim() && !matches.length;
  const feedback = loading ? 'Loading districts…' : error ? String(error) : status
    || (empty ? messages['not-found'] : open && totalMatches > matches.length ? `Showing ${matches.length} of ${totalMatches} matches. Refine the name, state or ID.` : '');
  return <div className="district-search" role="search" aria-label={label} aria-busy={loading} onBlur={onBlur}>
    <label htmlFor={`${id}-input`}>{label}</label>
    <div className="district-search-form">
      <input id={`${id}-input`} type="search" role="combobox" value={query} placeholder={placeholder}
        className="search-input" autoComplete="off" disabled={unavailable}
        aria-autocomplete="list" aria-haspopup="listbox" aria-expanded={showResults}
        aria-controls={showResults ? `${id}-results` : undefined}
        aria-activedescendant={showResults && activeIndex >= 0 ? `${id}-option-${activeIndex}` : undefined}
        aria-describedby={`${id}-hint${feedback ? ` ${id}-status` : ''}`}
        onChange={event => onQueryChange(event.target.value)} onKeyDown={onKeyDown} onFocus={onFocus} />
      <button className="button button-secondary" type="button" disabled={unavailable || !query.trim()} onClick={onSubmit}>Select</button>
    </div>
    <span id={`${id}-hint`} className="sr-only">Search by district name, state or ID. Use arrow keys to choose a result and Enter to select.</span>
    {feedback && <div id={`${id}-status`} className="district-search-status" role={error ? 'alert' : 'status'}>
      {feedback}{error && onRetry && <button className="button button-secondary" type="button" disabled={disabled || loading} onClick={onRetry}>Retry district list</button>}
    </div>}
    {showResults && <ul className="district-search-results" id={`${id}-results`} role="listbox" aria-label="Matching districts">
      {matches.map((district, index) => <li key={district.district_id} role="none">
        <button id={`${id}-option-${index}`} ref={index === activeIndex ? activeOptionRef : null} type="button" role="option" tabIndex={-1}
          aria-selected={index === activeIndex} onMouseDown={event => event.preventDefault()} onClick={() => onSelect(district)}>
          <span>{district.name || district.district_id}</span><small>{district.state || 'State unavailable'} · {district.district_id}</small>
        </button>
      </li>)}
    </ul>}
  </div>;
}

/** Parents own the canonical API catalog and the selected district identity. */
export default function DistrictSearch({ districts = [], selectedId = '', onSelect = () => {},
  onQueryChange = () => {}, loading = false, error = null, onRetry, disabled = false,
  label = 'Search district', placeholder = 'District, state or ID' }) {
  const id = useId();
  const selected = districts.find(district => district.district_id === selectedId);
  const [query, setQuery] = useState(() => districtSearchLabel(selected));
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [status, setStatus] = useState('');
  const activeOptionRef = useRef(null);
  const allMatches = useMemo(() => searchDistricts(districts, query), [districts, query]);
  const matches = allMatches.slice(0, 8);

  useEffect(() => {
    // An empty selection from a user edit must leave that user's query intact.
    if (!selected) return;
    setQuery(districtSearchLabel(selected)); setOpen(false); setActiveIndex(-1); setStatus('');
  }, [selected]);

  useEffect(() => {
    if (open && activeIndex >= 0) activeOptionRef.current?.scrollIntoView?.({ block: 'nearest' });
  }, [open, activeIndex]);

  const chooseDistrict = district => {
    if (disabled || loading || error) return;
    setQuery(districtSearchLabel(district)); setOpen(false); setActiveIndex(-1); setStatus('');
    onSelect(district);
  };
  const applyResult = result => {
    if (result.status === 'found') chooseDistrict(result.district);
    else { setStatus(messages[result.status]); setOpen(true); setActiveIndex(-1); }
  };
  const submit = () => {
    if (!disabled && !loading && !error) applyResult(resolveDistrictSearch(districts, query));
  };
  const keyDown = event => {
    // This control can live inside another form: Enter selects, never submits it.
    if (event.key === 'Enter') event.preventDefault();
    if (disabled || loading || error) return;
    const action = districtSearchKeyAction(event.key, { districts, query, matches, activeIndex, open });
    if (action.type === 'ignore') return;
    event.preventDefault();
    if (action.type === 'submit') applyResult(action.result);
    if (action.type === 'close') { setOpen(false); setActiveIndex(-1); setStatus(''); }
    if (action.type === 'open') { setOpen(true); setActiveIndex(action.activeIndex); }
  };
  return <DistrictSearchView id={id} label={label} placeholder={placeholder} query={query} matches={matches}
    totalMatches={allMatches.length} open={open} activeIndex={activeIndex} loading={loading} error={error}
    disabled={disabled} status={!loading && !error && !districts.length ? 'No districts are available.' : status}
    activeOptionRef={activeOptionRef} onRetry={onRetry} onSelect={chooseDistrict} onSubmit={submit} onKeyDown={keyDown}
    onQueryChange={value => { setQuery(value); setOpen(true); setActiveIndex(-1); setStatus(''); onQueryChange(value); }}
    onFocus={() => setOpen(true)} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) { setOpen(false); setActiveIndex(-1); } }} />;
}

/** The existing Home map search uses the same canonical click path as its polygons. */
export function MapDistrictSearch({ scores = [], catalogLoading = false, catalogError = null,
  onCatalogRetry, onDistrictClick }) {
  return <DistrictSearch districts={scores} loading={catalogLoading} error={catalogError}
    onRetry={onCatalogRetry} label="Search district" placeholder="Search district..."
    onSelect={district => onDistrictClick?.(district.district_id)} />;
}
