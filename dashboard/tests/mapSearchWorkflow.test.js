import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { fetchExperimentalScenario, fetchScores } from '../src/api.js';
import { districtForecastPath } from '../src/components/districtNavigation.js';
import { districtSearchKeyAction, searchDistricts } from '../src/components/districtSearch.js';
import { loadJsx } from './helpers/loadJsx.js';

const { MapDistrictSearch, DistrictSearchView } = await loadJsx(new URL('../src/components/DistrictSearch.jsx', import.meta.url));
const districts = [
  { district_id: 'HR-Kaithal', name: 'Kaithal', state: 'Haryana' },
  { district_id: 'CG-Bilaspur', name: 'Bilaspur', state: 'Chhattisgarh' },
  { district_id: 'HP-Bilaspur', name: 'Bilaspur', state: 'Himachal Pradesh' },
  // This canonical district has no separate matching polygon in the map source.
  { district_id: 'MH-Mumbai_Suburban', name: 'Mumbai Suburban', state: 'Maharashtra' },
];

let originalFetch;
beforeEach(() => { originalFetch = globalThis.fetch; });
afterEach(() => { globalThis.fetch = originalFetch; });

function descendants(node, predicate) {
  if (node == null || typeof node !== 'object') return [];
  if (Array.isArray(node)) return node.flatMap(child => descendants(child, predicate));
  return [...(predicate(node) ? [node] : []), ...descendants(node.props?.children, predicate)];
}

function districtFromPath(path) {
  const url = new URL(path, 'https://aquaiq.example');
  assert.equal(url.hash, '#forecast-graph');
  assert.equal(url.search, '');
  return decodeURIComponent(url.pathname.slice('/district/'.length));
}

function recordScenarioRequests() {
  const requests = [];
  globalThis.fetch = async url => {
    requests.push(url);
    const id = decodeURIComponent(new URL(url, 'https://aquaiq.example').pathname.split('/').at(-1));
    return { ok: true, json: async () => ({ district_id: id, status: 'unavailable', forecast: [] }) };
  };
  return requests;
}

test('the production map search retains its exact field and canonical catalog without any geometry', () => {
  const control = MapDistrictSearch({ scores: districts });
  assert.equal(control.props.districts, districts);
  assert.equal(control.props.placeholder, 'Search district...');
  assert.equal(control.props.loading, false);
  assert.equal(control.props.error, null);
  const html = renderToStaticMarkup(control);
  assert.equal((html.match(/role="combobox"/g) || []).length, 1);
  assert.match(html, /placeholder="Search district\.\.\."/);
  assert.match(html, /Search district/);
});

test('clicking the actual map suggestion opens its canonical district graph and scenario API', async () => {
  const requests = recordScenarioRequests();
  let route;
  const control = MapDistrictSearch({ scores: districts,
    onDistrictClick: id => { route = districtForecastPath(id); } });
  const matches = searchDistricts(control.props.districts, 'Bilaspur');
  const list = DistrictSearchView({ id: 'map-click', open: true, query: 'Bilaspur', matches,
    onSelect: control.props.onSelect });
  const options = descendants(list, node => node.props?.role === 'option');
  options[1].props.onClick();
  assert.equal(route, '/district/HP-Bilaspur#forecast-graph');
  const response = await fetchExperimentalScenario(districtFromPath(route));
  assert.equal(response.district_id, districts[2].district_id);
  assert.deepEqual(requests, ['/api/research/scenario/HP-Bilaspur?months=12']);
});

test('exact Enter selects the map catalog ID and requests that district even without a polygon', async () => {
  const requests = recordScenarioRequests();
  let route;
  const control = MapDistrictSearch({ scores: districts,
    onDistrictClick: id => { route = districtForecastPath(id); } });
  const query = ' mh_mumbai suburban ';
  const action = districtSearchKeyAction('Enter', { districts: control.props.districts, query,
    matches: searchDistricts(control.props.districts, query), activeIndex: -1, open: true });
  assert.equal(action.type, 'submit');
  assert.equal(action.result.status, 'found');
  assert.equal(action.result.district, districts[3]);
  control.props.onSelect(action.result.district);
  assert.equal(route, '/district/MH-Mumbai_Suburban#forecast-graph');
  const response = await fetchExperimentalScenario(districtFromPath(route));
  assert.equal(response.district_id, districts[3].district_id);
  assert.deepEqual(requests, ['/api/research/scenario/MH-Mumbai_Suburban?months=12']);
});

test('ambiguous map Enter keeps district identity unresolved until a labelled option is chosen', () => {
  const query = 'Bilaspur';
  const action = districtSearchKeyAction('Enter', { districts, query, matches: searchDistricts(districts, query),
    activeIndex: -1, open: true });
  assert.equal(action.result.status, 'ambiguous');
  assert.equal(action.result.district, null);
  assert.deepEqual(action.result.matches.map(district => `${district.state}: ${district.district_id}`),
    ['Chhattisgarh: CG-Bilaspur', 'Himachal Pradesh: HP-Bilaspur']);
});

test('the map catalog exposes loading and an actual API failure with a working parent retry', async () => {
  const loading = renderToStaticMarkup(createElement(MapDistrictSearch, { scores: [], catalogLoading: true }));
  assert.match(loading, /role="combobox"[^>]*disabled=""/);
  assert.match(loading, /Loading districts/);
  assert.match(loading, /role="status"/);

  globalThis.fetch = async () => ({ ok: false, status: 503 });
  let failure;
  try { await fetchScores(); } catch (error) { failure = error.message; }
  assert.match(failure, /Scores fetch failed: 503/);
  let retryRequest;
  let retries = 0;
  const control = MapDistrictSearch({ scores: [], catalogError: failure, onCatalogRetry: () => {
    retries += 1;
    retryRequest = fetchScores();
  } });
  const html = renderToStaticMarkup(control);
  assert.match(html, /role="alert"/);
  assert.match(html, /Scores fetch failed: 503/);
  assert.match(html, /Retry district list/);
  const errorView = DistrictSearchView({ id: 'map-retry', error: control.props.error, onRetry: control.props.onRetry });
  const retryButton = descendants(errorView, node => node.type === 'button' && !node.props.disabled).at(-1);
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ status: 'success', districts }) });
  retryButton.props.onClick();
  assert.equal(retries, 1);
  assert.equal((await retryRequest).districts, districts);
});

test('the Home route helper safely preserves a canonical identifier in one route segment', () => {
  const id = 'XX-District / Test';
  assert.equal(districtForecastPath(id), '/district/XX-District%20%2F%20Test#forecast-graph');
  assert.equal(districtFromPath(districtForecastPath(id)), id);
});
