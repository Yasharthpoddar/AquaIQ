import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { loadJsx } from './helpers/loadJsx.js';
import { postSimulate } from '../src/api.js';
import {
  INITIAL_SIMULATION_INPUTS, SIMULATION_PRESETS, canExportComparison, comparisonCsv,
  createScenarioRunner, normalizeSimulationResult, selectedSimulationPreset, simulationCsvCell,
  simulationInputReducer, simulationPayload, validSimulationInputs,
} from '../src/components/simulationComparison.js';

const { default: Simulate, SimulationControls, ComparisonResults } = await loadJsx(new URL('../src/pages/Simulate.jsx', import.meta.url));

// Synthetic scores exercise presentation and request contracts, not model skill.
const district = { district_id: 'HR-Kaithal', name: 'Kaithal', state: 'Haryana', score: 50,
  tier: 'Watch', status: 'historical_forecast', last_observed_date: '2020-05-01' };
function response(score = 50, baseline = 50, overrides = {}) {
  return { district_id: district.district_id, status: 'historical_forecast', baseline_score: baseline,
    baseline_tier: 'Watch', simulated_score: score, simulated_tier: 'Watch', delta: 999,
    last_observed_date: '2020-05-01', ...overrides };
}
function comparison(rows, overrides = {}) {
  return { district: { ...district }, rows, completed: true, ...overrides };
}
function elements(node) {
  if (!node || typeof node !== 'object') return [];
  if (Array.isArray(node)) return node.flatMap(elements);
  return [node, ...elements(node.props?.children)];
}
function button(tree, text) {
  return elements(tree).find(element => element.type === 'button' && element.props.children === text);
}
function input(tree, id) {
  return elements(tree).find(element => element.type === 'input' && element.props.id === id);
}
const render = (component, props) => renderToStaticMarkup(createElement(component, props));

test('all six presets carry exactly the requested rainfall and extraction percentages', () => {
  assert.deepEqual(SIMULATION_PRESETS.map(preset => [preset.label, preset.rainfallChange, preset.extractionChange]), [
    ['Baseline', 0, 0], ['Drier monsoon', -20, 0], ['Wetter monsoon', 20, 0],
    ['Higher extraction', 0, 20], ['Reduced extraction', 0, -20], ['Combined stress', -20, 20],
  ]);
});

test('actual preset buttons populate both controlled sliders and reset returns both to zero', () => {
  let inputs = { ...INITIAL_SIMULATION_INPUTS };
  const controls = () => SimulationControls({ selectedDistrict: district, inputs,
    onPreset: id => { inputs = simulationInputReducer(inputs, { type: 'preset', id }); },
    onReset: () => { inputs = simulationInputReducer(inputs, { type: 'reset' }); },
    onInputChange: (field, value) => { inputs = simulationInputReducer(inputs, { type: 'change', field, value }); },
  });
  for (const preset of SIMULATION_PRESETS) {
    button(controls(), preset.label).props.onClick();
    const tree = controls();
    assert.equal(input(tree, 'sim-rainfall').props.value, preset.rainfallChange);
    assert.equal(input(tree, 'sim-extraction').props.value, preset.extractionChange);
    assert.equal(button(tree, preset.label).props['aria-pressed'], true);
    assert.match(renderToStaticMarkup(tree), new RegExp(`id="sim-extraction-value">\\+?${preset.extractionChange}%`));
  }
  input(controls(), 'sim-rainfall').props.onChange({ target: { value: '13' } });
  assert.equal(inputs.rainfallChange, 13);
  assert.equal(selectedSimulationPreset(inputs), null);
  button(controls(), 'Reset to zero').props.onClick();
  assert.deepEqual(inputs, { rainfallChange: 0, extractionChange: 0 });
  assert.equal(button(controls(), 'Reset to zero').props.disabled, true);
});

test('actual form submission sends selected slider values through the existing simulation API', async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options, payload: JSON.parse(options.body) });
    return { ok: true, json: async () => response(42) };
  };
  try {
    let inputs = { ...INITIAL_SIMULATION_INPUTS };
    let completion;
    const runner = createScenarioRunner(postSimulate);
    const controls = () => SimulationControls({ selectedDistrict: district, inputs,
      onInputChange: (field, value) => { inputs = simulationInputReducer(inputs, { type: 'change', field, value }); },
      onRun: () => { completion = runner({ districtId: district.district_id, scenarios: [{ id: 'custom', label: 'Custom scenario', ...inputs }] }); },
    });
    input(controls(), 'sim-rainfall').props.onChange({ target: { value: '-17' } });
    input(controls(), 'sim-extraction').props.onChange({ target: { value: '23' } });
    let prevented = false;
    controls().props.onSubmit({ preventDefault: () => { prevented = true; } });
    const rows = await completion;
    assert.equal(prevented, true);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, '/api/simulate');
    assert.equal(calls[0].options.method, 'POST');
    assert.deepEqual(calls[0].payload, { district_id: 'HR-Kaithal', rainfall_change_pct: -17, extraction_change_pct: 23 });
    assert.equal(rows[0].delta, -8);
    assert.deepEqual([rows[0].rainfallChange, rows[0].extractionChange], [-17, 23]);
  } finally { globalThis.fetch = originalFetch; }
});

test('comparison requests are sequential, include all six combinations and preserve successes around failures', async () => {
  let active = 0;
  let maximum = 0;
  const payloads = [];
  const progress = [];
  const runner = createScenarioRunner(async payload => {
    active += 1; maximum = Math.max(maximum, active); payloads.push(payload);
    await Promise.resolve(); active -= 1;
    if (payload.rainfall_change_pct === 20) throw new Error('Synthetic service failure');
    if (payload.extraction_change_pct === -20) return response(null, null, { status: 'insufficient_data' });
    return response(50 + payload.extraction_change_pct / 2);
  });
  const rows = await runner({ districtId: district.district_id, scenarios: SIMULATION_PRESETS, onResult: value => progress.push(value) });
  assert.equal(maximum, 1);
  assert.deepEqual(payloads, SIMULATION_PRESETS.map(preset => simulationPayload(district.district_id, preset)));
  assert.deepEqual(rows.map(row => row.status), ['available', 'available', 'error', 'available', 'unavailable', 'available']);
  assert.deepEqual(progress.map(value => value.length), [1, 2, 3, 4, 5, 6]);
  assert.equal(progress[0][0].scenarioScore, 50);
  assert.equal(rows[0].scenarioScore, 50);
  assert.equal(rows[3].scenarioScore, 60);
  assert.equal(rows[5].scenarioScore, 60);
  assert.equal(rows[2].scenarioScore, null);
  assert.match(rows[2].message, /Synthetic service failure/);
});

test('an active run rejects duplicate submission before another request and unlocks after completion', async () => {
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  let calls = 0;
  const runner = createScenarioRunner(async () => { calls += 1; await pending; return response(); });
  const job = { districtId: district.district_id, scenarios: [SIMULATION_PRESETS[0]] };
  const first = runner(job);
  assert.equal(await runner(job), null);
  assert.equal(calls, 1);
  release();
  await first;
  assert.equal((await runner(job)).length, 1);
  assert.equal(calls, 2);
});

test('leaving the page stops additional comparison requests after the in-flight request', async () => {
  let alive = true;
  let calls = 0;
  const runner = createScenarioRunner(async () => { calls += 1; return response(); });
  const rows = await runner({ districtId: district.district_id, scenarios: SIMULATION_PRESETS,
    shouldContinue: () => alive, onResult: () => { alive = false; } });
  assert.equal(calls, 1);
  assert.equal(rows.length, 1);
});

test('deltas derive from actual scores, including zero, negative changes and legitimate zero indices', () => {
  for (const [baseline, scenario, expected] of [[50, 50, 0], [50, 35, -15], [0, 0, 0], [0, 20, 20], [50.1, 40.2, -9.9]]) {
    const row = normalizeSimulationResult(response(scenario, baseline), district.district_id, SIMULATION_PRESETS[0]);
    assert.equal(row.status, 'available');
    assert.equal(row.baselineScore, baseline);
    assert.equal(row.scenarioScore, scenario);
    assert.equal(row.delta, expected);
  }
});

test('missing, non-numeric, nonfinite and out-of-range indices never become zero', () => {
  for (const invalid of [null, undefined, NaN, Infinity, '0', false, [], {}, -1, 101]) {
    for (const key of ['baseline_score', 'simulated_score']) {
      const row = normalizeSimulationResult(response(40, 50, { [key]: invalid }), district.district_id, SIMULATION_PRESETS[0]);
      assert.equal(row.status, 'unavailable');
      assert.equal(row.scenarioScore, null);
      assert.equal(row.delta, null);
    }
  }
  for (const status of ['unavailable', 'insufficient_data', 'invalid_request', 'invented_status', undefined]) {
    const row = normalizeSimulationResult(response(0, 0, { status }), district.district_id, SIMULATION_PRESETS[0]);
    assert.equal(row.scenarioScore, null);
    assert.equal(row.baselineScore, null);
  }
  const wrongDistrict = normalizeSimulationResult(response(30, 50, { district_id: 'RJ-Jaipur' }), district.district_id, SIMULATION_PRESETS[0]);
  assert.equal(wrongDistrict.status, 'unavailable');
  assert.match(wrongDistrict.message, /incompatible district/);
  for (const tier of ['Dangerous', null, 0, { toString: 'invalid' }]) {
    const unknownTier = normalizeSimulationResult(response(30, 50, { simulated_tier: tier }), district.district_id, SIMULATION_PRESETS[0]);
    assert.equal(unknownTier.scenarioTier, null);
  }
});

test('invalid input cannot trigger API actions and busy controls remain disabled', async () => {
  for (const value of [null, NaN, Infinity, '10', true, -101, 101]) {
    assert.equal(validSimulationInputs({ rainfallChange: value, extractionChange: 0 }), false);
  }
  let calls = 0;
  const runner = createScenarioRunner(async () => { calls += 1; return response(); });
  await assert.rejects(runner({ districtId: '', scenarios: SIMULATION_PRESETS }), /Select a district/);
  await assert.rejects(runner({ districtId: district.district_id, scenarios: [{ rainfallChange: NaN, extractionChange: 0 }] }), /finite percentage/);
  assert.equal(calls, 0);
  for (const props of [{}, { selectedDistrict: district, busy: true }, { selectedDistrict: district, inputs: { rainfallChange: NaN, extractionChange: 0 } }]) {
    const tree = SimulationControls({ ...props, onRun: () => { calls += 1; }, onCompare: () => { calls += 1; } });
    assert.equal(button(tree, 'Run scenario').props.disabled, true);
    assert.equal(button(tree, 'Compare scenarios').props.disabled, true);
    tree.props.onSubmit({ preventDefault() {} });
    button(tree, 'Compare scenarios').props.onClick();
  }
  assert.equal(calls, 0);
  const busyHtml = render(SimulationControls, { selectedDistrict: district, busy: true });
  assert.match(busyHtml, /<fieldset[^>]*disabled/);
  assert.match(busyHtml, /role="status">Evaluating scenarios/);
});

test('bars and table render the same API indices and original inputs, including unavailable rows', () => {
  const baseline = normalizeSimulationResult(response(0, 0, { baseline_tier: 'Safe', simulated_tier: 'Safe' }), district.district_id, SIMULATION_PRESETS[0]);
  const combined = normalizeSimulationResult(response(65, 50, { simulated_tier: 'Warning' }), district.district_id, SIMULATION_PRESETS[5]);
  const missing = normalizeSimulationResult(response(null), district.district_id, SIMULATION_PRESETS[2]);
  const html = render(ComparisonResults, { comparison: comparison([baseline, combined, missing]), selectedDistrictId: district.district_id });
  assert.match(html, /width:0%/);
  assert.match(html, /width:65%/);
  assert.equal((html.match(/class="sim-bar-fill"/g) || []).length, 2);
  assert.match(html, /<th scope="row">Combined stress<\/th><td>-20%<\/td><td>\+20%<\/td><td>50<\/td>/);
  assert.match(html, /<td>65<\/td>.*Warning.*<td>\+15<\/td>/);
  assert.match(html, /<th scope="row">Baseline<\/th><td>0%<\/td><td>0%<\/td><td>0<\/td>/);
  assert.match(html, /<th scope="row">Wetter monsoon<\/th><td>\+20%<\/td><td>0%<\/td>.*Unavailable/);
  assert.match(html, /Source month: 2020-05.*historical source evidence/);
  assert.match(html, /role="region" aria-label="Scenario comparison table" tabindex="0"/);
  assert.equal((html.match(/<th scope="row">/g) || []).length, 3);
});

test('the saved district snapshot labels retained results after the selected district changes', () => {
  const saved = comparison([normalizeSimulationResult(response(), district.district_id, SIMULATION_PRESETS[0])]);
  const html = render(ComparisonResults, { comparison: saved, selectedDistrictId: 'RJ-Jaipur' });
  assert.match(html, /Kaithal, Haryana.*HR-Kaithal/);
  assert.match(html, /These results belong to Kaithal/);
  assert.doesNotMatch(html, /Jaipur/);
  assert.match(comparisonCsv(saved), /HR-Kaithal/);
});

test('CSV escapes commas, quotes and line breaks and neutralizes text formula prefixes only', () => {
  assert.equal(simulationCsvCell('A, "quoted"\nplace'), '"A, ""quoted""\nplace"');
  for (const text of ['=SUM(1,2)', '+CMD', '-formula', '@query', '  =formula', '\tformula', '\rformula', '\nformula']) {
    assert.ok(simulationCsvCell(text).startsWith('"\''));
  }
  assert.equal(simulationCsvCell(-20), '-20');
  assert.equal(simulationCsvCell(0), '0');
  const row = normalizeSimulationResult(response(40), district.district_id, SIMULATION_PRESETS[1]);
  const csv = comparisonCsv(comparison([row], { district: { district_id: 'HR-Kaithal', name: '=CMD,"quoted"\nname', state: '@state' } }));
  assert.match(csv, /"district_id","district_name","state","scenario","rainfall_change_pct"/);
  assert.match(csv, /"'=CMD,""quoted""\nname","'@state"/);
  assert.match(csv, /"Drier monsoon",-20,0,50,"Watch",40,"Watch",-10,"available"/);
});

test('CSV stays disabled until a run has completed and reports a useful no-results state', () => {
  for (const value of [null, comparison([]), comparison([{}], { completed: false })]) {
    assert.equal(canExportComparison(value), false);
    assert.equal(comparisonCsv(value), '');
    assert.equal(button(ComparisonResults({ comparison: value }), 'Export CSV').props.disabled, true);
  }
  const row = normalizeSimulationResult(response(), district.district_id, SIMULATION_PRESETS[0]);
  assert.equal(canExportComparison(comparison([row])), true);
  assert.equal(button(ComparisonResults({ comparison: comparison([row]), busy: true }), 'Export CSV').props.disabled, true);
  assert.match(render(ComparisonResults, {}), /Run a scenario or comparison to enable CSV export/);
});

test('controls expose labels, percentages and baseline availability without requiring chart hover', () => {
  const html = render(SimulationControls, { selectedDistrict: { ...district, score: 0, tier: 'Safe' }, inputs: { rainfallChange: -20, extractionChange: 20 } });
  assert.match(html, /<label for="sim-rainfall">Rainfall variation/);
  assert.match(html, /<label for="sim-extraction">Extraction sensitivity/);
  assert.match(html, /aria-valuetext="-20 percent rainfall change"/);
  assert.match(html, /aria-valuetext="\+20 percent extraction change"/);
  assert.match(html, /Current baseline index.*<strong>0 <small>\/ 100/s);
  assert.match(html, /Source month: 2020-05/);
  const unavailable = render(SimulationControls, { selectedDistrict: { ...district, score: null } });
  assert.match(unavailable, /Current baseline index.*<strong>Unavailable/s);
  const unavailableEvidence = render(SimulationControls, { selectedDistrict: { ...district, score: 0, status: 'insufficient_data', last_observed_date: 0 } });
  assert.match(unavailableEvidence, /Current baseline index.*<strong>Unavailable/s);
  assert.match(unavailableEvidence, /Source month: Unavailable/);
  const initialPage = render(Simulate, {});
  assert.match(initialPage, /Loading districts/);
  assert.match(initialPage, /role="search" aria-label="Simulation district"/);
  assert.match(initialPage, /role="combobox"/);
  assert.match(initialPage, /<button[^>]*disabled="">Run scenario/);
  assert.match(initialPage, /<details[^>]*><summary>How it works/);
  assert.doesNotMatch(initialPage, /<details[^>]*open/);
});

test('district labels, scenario labels and service errors render as escaped text', () => {
  const row = normalizeSimulationResult(response(), district.district_id, { ...SIMULATION_PRESETS[0], label: '<img src=x onerror=alert(1)>' });
  row.status = 'error'; row.message = '<script>unsafe</script>';
  const html = render(ComparisonResults, { comparison: comparison([row], { district: { ...district, name: '<script>district</script>' } }) });
  assert.match(html, /&lt;script&gt;district/);
  assert.match(html, /&lt;script&gt;unsafe/);
  assert.match(html, /&lt;img/);
  assert.doesNotMatch(html, /<script>|<img/);
});
