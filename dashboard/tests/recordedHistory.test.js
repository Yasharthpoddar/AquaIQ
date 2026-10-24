import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { recordedHistoryRows, recordedHistoryValue, recordedHistoryObservationSegments, recordedHistoryGapSegments } from '../src/components/recordedHistory.js';
import { loadJsx } from './helpers/loadJsx.js';

const { recordedHistoryPlot, HistoryTooltip } = await loadJsx(new URL('../src/pages/DistrictDetail.jsx', import.meta.url));

test('recorded history preserves explicit missing months between observations', () => {
  const rows = recordedHistoryRows([
    { month: '2026-01', gwl: 4, is_observed: true },
    { month: '2026-02', gwl: null, is_observed: true },
    { month: '2026-03', gwl: 5, is_observed: true },
  ]);
  assert.deepEqual(rows, [
    { month: '2026-01', observed: 4, filled: null },
    { month: '2026-02', observed: null, filled: null },
    { month: '2026-03', observed: 5, filled: null },
  ]);
});

test('absent calendar buckets are null gaps and input is sorted without fabricating depths', () => {
  const input = [
    { month: '2026-04', gwl: 9, is_observed: true },
    { month: '2026-01', gwl: 6, is_observed: true },
  ];
  const original = structuredClone(input);
  assert.deepEqual(recordedHistoryRows(input), [
    { month: '2026-01', observed: 6, filled: null },
    { month: '2026-02', observed: null, filled: null },
    { month: '2026-03', observed: null, filled: null },
    { month: '2026-04', observed: 9, filled: null },
  ]);
  assert.deepEqual(input, original);
});

test('observed and forward-filled depths remain separate, including finite zero', () => {
  assert.deepEqual(recordedHistoryRows([
    { month: '2026-01', gwl: 0, is_observed: true, is_imputed: false },
    { month: '2026-02', gwl: 0, is_observed: false, is_imputed: true },
    { month: '2026-03', gwl: 3.2, is_observed: true, is_imputed: false },
    { month: '2026-04', gwl: 3.2, is_observed: false, is_imputed: true },
  ]), [
    { month: '2026-01', observed: 0, filled: null },
    { month: '2026-02', observed: null, filled: 0 },
    { month: '2026-03', observed: 3.2, filled: null },
    { month: '2026-04', observed: null, filled: 3.2 },
  ]);
});

test('nonfinite, nonnumeric, unflagged and conflicting evidence stays unavailable', () => {
  const rows = recordedHistoryRows([
    { month: '2026-01', gwl: NaN, is_observed: true },
    { month: '2026-02', gwl: Infinity, is_imputed: true },
    { month: '2026-03', gwl: '4.2', is_observed: true },
    { month: '2026-04', gwl: 4.2 },
    { month: '2026-05', gwl: 4.2, is_observed: true, is_imputed: true },
    { month: '2026-06', gwl: 4.2, is_observed: false, is_imputed: false },
  ]);
  assert.equal(rows.length, 6);
  assert.ok(rows.every(row => row.observed === null && row.filled === null));
});

test('calendar gaps cross a year boundary and date labels retain their source month', () => {
  assert.deepEqual(recordedHistoryRows([
    { date: '2027-02-01', gwl: 5.5, is_observed: true },
    { month: '2026-11', gwl: 4.5, is_observed: true },
  ]), [
    { month: '2026-11', observed: 4.5, filled: null },
    { month: '2026-12', observed: null, filled: null },
    { month: '2027-01', observed: null, filled: null },
    { month: '2027-02', observed: 5.5, filled: null },
  ]);
});

test('empty or invalid month labels do not create chart buckets', () => {
  assert.deepEqual(recordedHistoryRows(), []);
  assert.deepEqual(recordedHistoryRows([]), []);
  assert.deepEqual(recordedHistoryRows([
    { month: '', gwl: 4, is_observed: true },
    { month: '2026-00', gwl: 4, is_observed: true },
    { month: '2026-13', gwl: 4, is_observed: true },
    { month: 'not-a-month', gwl: 4, is_observed: true },
  ]), []);
});

test('the actual recorded-history chart uses the complete calendar and leaves both line gaps disconnected', () => {
  const rows = recordedHistoryRows([
    { month: '2026-01', gwl: 4, is_observed: true },
    { month: '2026-03', gwl: 4.5, is_imputed: true },
    { month: '2026-04', gwl: 5, is_observed: true },
  ]);
  const chart = recordedHistoryPlot(rows, { width: 720, height: 300 });
  assert.equal(chart.props.data, rows);
  assert.deepEqual(chart.props.data[1], { month: '2026-02', observed: null, filled: null });
  const lines = chart.props.children.filter(child => ['observed', 'filled'].includes(child?.props?.dataKey));
  assert.equal(lines.length, 2);
  for (const line of lines) assert.equal(line.props.connectNulls, false);
  assert.deepEqual(lines.map(line => line.props.dataKey), ['observed', 'filled']);
});

test('solid observation guides use full-calendar selectors and keep real gaps out of their endpoints', () => {
  const rows = recordedHistoryRows([
    { month: '2026-01', gwl: 0, is_observed: true },
    { month: '2026-02', gwl: 0, is_imputed: true },
    { month: '2026-03', gwl: 5, is_observed: true },
    { month: '2026-04', gwl: 5, is_imputed: true },
    { month: '2026-05', gwl: null, is_observed: true },
    { month: '2026-06', gwl: 6, is_observed: true },
    { month: '2026-07', gwl: 6, is_imputed: true },
    { month: '2026-08', gwl: 7, is_observed: true },
    { month: '2026-10', gwl: 8, is_observed: true },
    { month: '2026-11', gwl: 8, is_imputed: true },
    { month: '2026-12', gwl: 9, is_observed: true },
  ]);
  const original = structuredClone(rows);
  assert.deepEqual(rows.map(recordedHistoryValue), [0, 0, 5, 5, null, 6, 6, 7, null, 8, 8, 9]);
  assert.deepEqual(recordedHistoryObservationSegments(rows).map(segment => segment.map(row => row.month)), [
    ['2026-01', '2026-03'], ['2026-06', '2026-08'], ['2026-10', '2026-12'],
  ]);
  const chart = recordedHistoryPlot(rows, { width: 720, height: 300 });
  const children = chart.props.children.flat();
  const guides = children.filter(child => child?.props?.className === 'history-observation-guide');
  assert.equal(guides.length, 3);
  assert.deepEqual(guides.map(line => rows.map(line.props.dataKey).filter(Number.isFinite)), [[0, 5], [6, 7], [8, 9]]);
  for (const guide of guides) {
    assert.equal(guide.props.connectNulls, true);
    assert.equal(guide.props.data, undefined, 'Short per-line datasets must not clamp full-calendar hover indexes');
    assert.equal(typeof guide.props.dataKey, 'function', 'Decorative guides must not share the observed tooltip key');
    assert.equal(guide.props.stroke, '#2563eb');
    assert.equal(guide.props.strokeDasharray, undefined);
    assert.equal(guide.props.dot, false);
    assert.equal(guide.props.activeDot, false);
    assert.equal(guide.props.legendType, 'none');
    assert.equal(guide.props.tooltipType, 'none');
    assert.ok(rows.every(row => guide.props.dataKey(row) === null || guide.props.dataKey(row) === row.observed), 'Guides use original observed values without interpolation');
  }
  const axis = children.find(child => child?.props?.dataKey === 'month');
  assert.equal(chart.props.data, rows);
  assert.equal(axis.props.allowDuplicatedCategory, false, 'Guide endpoints align by month, not by reduced-array index');
  const observed = chart.props.children.find(child => child?.props?.dataKey === 'observed');
  assert.equal(observed.props.stroke, '#2563eb');
  assert.equal(observed.props.strokeDasharray, undefined);
  assert.equal(observed.props.dot.fill, '#fff');
  assert.deepEqual(rows, original);
});

test('filled-only runs and isolated observations never create an invented observed trend', () => {
  const rows = recordedHistoryRows([
    { month: '2026-01', gwl: 3, is_imputed: true },
    { month: '2026-02', gwl: 3, is_imputed: true },
    { month: '2026-03', gwl: 4, is_observed: true },
    { month: '2026-05', gwl: 5, is_observed: true },
  ]);
  assert.deepEqual(recordedHistoryObservationSegments(rows), []);
  assert.equal(rows[2].observed, 4);
  assert.equal(rows[4].observed, 5);
  assert.deepEqual(rows[3], {month:'2026-04',observed:null,filled:null});
});

test('a dashed visual bridge makes the trend continuous without creating values in missing months', () => {
  const rows = recordedHistoryRows([
    {month:'2020-01',gwl:4,is_observed:true},
    {month:'2020-03',gwl:4,is_imputed:true},
    {month:'2026-01',gwl:7,is_observed:true},
  ]);
  const chart = recordedHistoryPlot(rows);
  const bridge = chart.props.children.flat().find(child => child?.props?.className === 'history-gap-guide');
  assert.ok(bridge);
  assert.equal(bridge.props.connectNulls, true);
  assert.equal(bridge.props.strokeDasharray, '5 5');
  assert.equal(bridge.props.dot, false);
  assert.equal(bridge.props.data, undefined);
  assert.equal(bridge.props.tooltipType, 'none');
  assert.equal(bridge.props.legendType, 'none');
  assert.deepEqual(rows.map(bridge.props.dataKey).filter(Number.isFinite), [4,7]);
  assert.equal(bridge.props.dataKey(rows[1]), null);
  assert.equal(bridge.props.dataKey(rows[2]), null, 'A forward fill must not become an observed bridge endpoint');
  const tooltip = chart.props.children.flat().find(child => child?.props?.content?.type === HistoryTooltip);
  assert.ok(tooltip);
  assert.equal(tooltip.props.filterNull, false, 'Missing-month hover must still show an explicit unavailable message');
  assert.equal(tooltip.props.shared, true);
  assert.equal(tooltip.props.trigger, 'hover');
  assert.equal(tooltip.props.content.props.rows, rows);
  assert.equal(tooltip.props.wrapperStyle.pointerEvents, 'none');
});

test('history hover shows the original month and zero depth with observed versus filled status', () => {
  const rows = recordedHistoryRows([
    {month:'2026-01',gwl:0,is_observed:true},
    {month:'2026-02',gwl:0,is_imputed:true},
  ]);
  const observed = renderToStaticMarkup(createElement(HistoryTooltip,{active:true,label:'2026-01',rows,
    payload:[{value:999,name:'Misleading decorative payload'}]}));
  assert.match(observed,/January 2026/);
  assert.match(observed,/Source-marked observation/);
  assert.match(observed,/0\.00 m below ground/);
  assert.doesNotMatch(observed,/999|Misleading|Forward-filled/);
  const filled = renderToStaticMarkup(createElement(HistoryTooltip,{active:true,label:'2026-02',rows}));
  assert.match(filled,/February 2026/);
  assert.match(filled,/Forward-filled value/);
  assert.match(filled,/0\.00 m below ground/);
  assert.match(filled,/Not a new measurement/);
});

test('hover on a missing month reports unavailable rather than an interpolated number or zero', () => {
  const rows = recordedHistoryRows([
    {month:'2026-01',gwl:4,is_observed:true},
    {month:'2026-03',gwl:6,is_observed:true},
  ]);
  const html = renderToStaticMarkup(createElement(HistoryTooltip,{active:true,label:'2026-02',rows}));
  assert.match(html,/February 2026/);
  assert.match(html,/No recorded value for this month/);
  assert.match(html,/visual guide only/);
  assert.doesNotMatch(html,/\d+\.\d+ m below ground/);
  assert.equal(renderToStaticMarkup(createElement(HistoryTooltip,{active:false,label:'2026-01',rows})), '');
  assert.equal(renderToStaticMarkup(createElement(HistoryTooltip,{active:true,label:'unknown',rows})), '');
});

test('late-year hover resolves by the full original calendar label, independent of short guide payloads', () => {
  const rows = recordedHistoryRows([
    {month:'2002-01',gwl:4,is_observed:true},
    {month:'2026-12',gwl:8.25,is_observed:true},
  ]);
  const html = renderToStaticMarkup(createElement(HistoryTooltip,{active:true,label:'2026-12',rows,
    payload:[{payload:rows[0],value:4}]}));
  assert.match(html,/December 2026/);
  assert.match(html,/8\.25 m below ground/);
  assert.doesNotMatch(html,/4\.00 m below ground|January 2002/);
});

test('missing-period bridges use the adjacent original observations and never extrapolate either end', () => {
  const rows = recordedHistoryRows([
    {month:'2026-01',gwl:null,is_observed:true},
    {month:'2026-02',gwl:3,is_observed:true},
    {month:'2026-03',gwl:3,is_imputed:true},
    {month:'2026-05',gwl:4,is_observed:true},
    {month:'2026-06',gwl:5,is_observed:true},
    {month:'2026-08',gwl:6,is_observed:true},
    {month:'2026-09',gwl:null,is_observed:true},
  ]);
  const original = structuredClone(rows);
  const gaps = recordedHistoryGapSegments(rows);
  assert.deepEqual(gaps.map(pair => pair.map(row => row.month)), [['2026-02','2026-05'],['2026-06','2026-08']]);
  assert.ok(gaps.flat().every(row => rows.includes(row)));
  assert.deepEqual(rows,original);
});
