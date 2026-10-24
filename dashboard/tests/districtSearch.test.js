import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadJsx } from './helpers/loadJsx.js';
import {
  districtSearchKeyAction, districtSearchLabel, normalizeDistrictQuery, resolveDistrictSearch, searchDistricts,
} from '../src/components/districtSearch.js';

const districts = [
  { district_id: 'HR-Kaithal', name: 'Kaithal', state: 'Haryana', score: 0 },
  { district_id: 'HR-Karnal', name: 'Karnal', state: 'Haryana' },
  { district_id: 'CG-Bilaspur', name: 'Bilaspur', state: 'Chhattisgarh' },
  { district_id: 'HP-Bilaspur', name: 'Bilaspur', state: 'Himachal Pradesh' },
  { district_id: 'MH-Mumbai_Suburban', name: 'Mumbai Suburban', state: 'Maharashtra' },
];

const { default: DistrictSearch, DistrictSearchView } = await loadJsx(new URL('../src/components/DistrictSearch.jsx', import.meta.url));

function descendants(node, predicate) {
  if (node == null || typeof node !== 'object') return [];
  if (Array.isArray(node)) return node.flatMap(child => descendants(child, predicate));
  return [...(predicate(node) ? [node] : []), ...descendants(node.props?.children, predicate)];
}

test('partial names and single-character queries provide live canonical suggestions', () => {
  assert.deepEqual(searchDistricts(districts, 'kai'), [districts[0]]);
  assert.deepEqual(searchDistricts(districts, 'kar'), [districts[1]]);
  assert.ok(searchDistricts(districts, 'k').includes(districts[0]));
  assert.equal(districts[0].score, 0);
});

test('state and canonical ID searches normalize case, spaces, hyphens and underscores', () => {
  assert.deepEqual(searchDistricts(districts, 'HARYANA'), districts.slice(0, 2));
  for (const query of ['hr-kaithal', ' HR_KAITHAL ', 'hr   kaithal']) {
    assert.equal(resolveDistrictSearch(districts, query).district, districts[0]);
  }
  for (const query of ['mumbai suburban', 'Mumbai_Suburban', 'mumbai-suburban']) {
    assert.equal(resolveDistrictSearch(districts, query).district, districts[4]);
  }
  assert.equal(normalizeDistrictQuery('  Mumbai_Suburban, Maharashtra '), 'mumbai suburban maharashtra');
});

test('duplicate names require a state or canonical ID and never pick the first district', () => {
  const ambiguous = resolveDistrictSearch(districts, 'Bilaspur');
  assert.equal(ambiguous.status, 'ambiguous');
  assert.equal(ambiguous.district, null);
  assert.deepEqual(ambiguous.matches, districts.slice(2, 4));
  assert.equal(resolveDistrictSearch(districts, 'Bilaspur, Himachal Pradesh').district, districts[3]);
  assert.equal(resolveDistrictSearch(districts, 'Chhattisgarh Bilaspur').district, districts[2]);
  assert.equal(resolveDistrictSearch(districts, 'HP-Bilaspur').district, districts[3]);
});

test('exact canonical identity and exact name take priority over additional partial matches', () => {
  const extended = [...districts, { district_id: 'HR-Kaithal_Rural', name: 'Kaithal Rural', state: 'Haryana' }];
  assert.equal(resolveDistrictSearch(extended, 'Kaithal').district, districts[0]);
  assert.equal(resolveDistrictSearch(extended, 'HR-Kaithal').district, districts[0]);
  assert.equal(resolveDistrictSearch(extended, 'Haryana').status, 'ambiguous');
  assert.equal(resolveDistrictSearch(extended, districtSearchLabel(districts[0])).district, districts[0]);
});

test('empty, unknown and malformed records stay explicit without requiring a map boundary', () => {
  assert.equal(resolveDistrictSearch(districts, '  ').status, 'empty');
  assert.equal(resolveDistrictSearch(districts, 'No such district').status, 'not-found');
  // Mumbai Suburban is a canonical record even when no separate polygon exists.
  assert.equal(resolveDistrictSearch([districts[4]], 'MH-Mumbai_Suburban').district, districts[4]);
  assert.deepEqual(searchDistricts([null, {}, { name: 'Kaithal' }, districts[0], districts[0]], 'kai'), [districts[0]]);
  assert.deepEqual(searchDistricts(null, 'kai'), []);
  assert.deepEqual(searchDistricts(districts, 'haryana', 1), [districts[0]]);
});

test('Enter resolves a unique exact search while ambiguous and unknown submissions remain unresolved', () => {
  const action = query => districtSearchKeyAction('Enter', { districts, query,
    matches: searchDistricts(districts, query), activeIndex: -1, open: true });
  assert.equal(action('HR-Kaithal').result.district, districts[0]);
  assert.equal(action('Bilaspur').result.status, 'ambiguous');
  assert.equal(action('Bilaspur').result.district, null);
  assert.equal(action('Unknown district').result.status, 'not-found');
  assert.equal(action('').result.status, 'empty');
});

test('arrow keys choose a labelled suggestion, Enter selects it, and Escape closes the list', () => {
  const matches = searchDistricts(districts, 'Bilaspur');
  let state = { districts, query: 'Bilaspur', matches, activeIndex: -1, open: false };
  const down = districtSearchKeyAction('ArrowDown', state);
  assert.deepEqual(down, { type: 'open', activeIndex: 0 });
  state = { ...state, open: true, activeIndex: down.activeIndex };
  const next = districtSearchKeyAction('ArrowDown', state);
  const enter = districtSearchKeyAction('Enter', { ...state, activeIndex: next.activeIndex });
  assert.equal(enter.result.district, districts[3]);
  assert.deepEqual(districtSearchKeyAction('ArrowUp', { ...state, activeIndex: 0 }), { type: 'open', activeIndex: 1 });
  assert.deepEqual(districtSearchKeyAction('Escape', state), { type: 'close' });
  assert.deepEqual(districtSearchKeyAction('Tab', state), { type: 'ignore' });
  assert.deepEqual(districtSearchKeyAction('ArrowDown', { ...state, matches: [] }), { type: 'open', activeIndex: -1 });
});

test('actual suggestion callback supplies the original canonical ID to the consuming route handler', () => {
  let selected;
  let route;
  const tree = DistrictSearchView({ id: 'route-search', query: 'Bilaspur', open: true,
    matches: districts.slice(2, 4), onSelect: district => {
      selected = district;
      route = `/district/${encodeURIComponent(district.district_id)}`;
    } });
  const options = descendants(tree, node => node.props?.role === 'option');
  options[1].props.onClick();
  assert.equal(selected, districts[3]);
  assert.equal(route, '/district/HP-Bilaspur');
});

test('actual input and select button forward edits and explicit submissions independently', () => {
  const edits = [];
  let submits = 0;
  const tree = DistrictSearchView({ id: 'events', query: 'Kaithal',
    onQueryChange: query => edits.push(query), onSubmit: () => { submits += 1; } });
  descendants(tree, node => node.type === 'input')[0].props.onChange({ target: { value: 'Haryana' } });
  assert.deepEqual(edits, ['Haryana']);
  assert.equal(submits, 0);
  descendants(tree, node => node.type === 'button')[0].props.onClick();
  assert.equal(submits, 1);
});

test('suggestions expose accessible keyboard focus, state and canonical identity', () => {
  const html = renderToStaticMarkup(createElement(DistrictSearchView, { id: 'accessible', query: 'Bilaspur',
    open: true, activeIndex: 1, matches: districts.slice(2, 4), label: 'Simulation district' }));
  assert.match(html, /role="combobox"/);
  assert.match(html, /aria-expanded="true"/);
  assert.match(html, /aria-controls="accessible-results"/);
  assert.match(html, /aria-activedescendant="accessible-option-1"/);
  assert.match(html, /role="listbox"/);
  assert.match(html, /aria-selected="true"/);
  assert.match(html, /Himachal Pradesh.*HP-Bilaspur/);
  assert.match(html, /Chhattisgarh.*CG-Bilaspur/);
  assert.doesNotMatch(html, /<form/);
});

test('loading, errors, retry, empty suggestions and a disabled control have clear states', () => {
  const loading = renderToStaticMarkup(createElement(DistrictSearchView, { id: 'loading', loading: true }));
  assert.match(loading, /Loading districts/);
  assert.match(loading, /role="status"/);
  assert.match(loading, /disabled=""/);
  let retries = 0;
  const errorTree = DistrictSearchView({ id: 'error', error: 'District API unavailable', onRetry: () => { retries += 1; } });
  descendants(errorTree, node => node.type === 'button' && !node.props.disabled).at(-1).props.onClick();
  assert.equal(retries, 1);
  const error = renderToStaticMarkup(errorTree);
  assert.match(error, /role="alert"/);
  assert.match(error, /District API unavailable/);
  assert.match(error, /Retry district list/);
  const empty = renderToStaticMarkup(createElement(DistrictSearchView, { id: 'empty', query: 'Unknown', open: true }));
  assert.match(empty, /No matching district/);
  assert.doesNotMatch(empty, /role="listbox"/);
  const disabled = renderToStaticMarkup(createElement(DistrictSearchView, { id: 'disabled', query: 'kai', open: true, matches: districts, disabled: true }));
  assert.match(disabled, /disabled=""/);
  assert.doesNotMatch(disabled, /role="listbox"/);
});

test('component instances have unique identifiers and render API text as escaped content', () => {
  const supplied = { district_id: 'XX-<script>', name: '<img src=x onerror=alert(1)>', state: '<script>state</script>' };
  const html = renderToStaticMarkup(createElement('div', null,
    createElement(DistrictSearch, { districts, selectedId: 'HR-Kaithal' }),
    createElement(DistrictSearch, { districts, selectedId: 'HR-Karnal' }),
    createElement(DistrictSearchView, { id: 'escaped', query: '<svg onload=alert(1)>', open: true, matches: [supplied] })));
  const inputIds = [...html.matchAll(/<input id="([^"]+)"/g)].map(match => match[1]);
  assert.equal(new Set(inputIds).size, 3);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.match(html, /&lt;script&gt;state&lt;\/script&gt;/);
  assert.match(html, /value="&lt;svg onload=alert\(1\)&gt;"/);
  assert.doesNotMatch(html, /<script|<img|<svg/);
});
