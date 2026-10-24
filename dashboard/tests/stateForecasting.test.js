import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { getStateColor } from '../src/stateMap.js';

test('india_states.geojson contains exactly 36 states matching canonical registry', () => {
  const geojson = JSON.parse(readFileSync(new URL('../public/india_states.geojson', import.meta.url), 'utf8'));
  assert.equal(geojson.type, 'FeatureCollection');
  assert.equal(geojson.features.length, 36);

  const stateIds = new Set(geojson.features.map(f => f.properties.state_id));
  assert.equal(stateIds.size, 36);

  // Key states verified
  for (const expected of ['UP', 'TN', 'MH', 'RJ', 'KA', 'DL', 'LA', 'LD', 'AN', 'CH', 'DD', 'JK']) {
    assert.ok(stateIds.has(expected), `Missing state_id ${expected}`);
  }
});

test('getStateColor accurately maps depth metric (greater depth = higher depletion)', () => {
  // Shallow depth (<5m) -> green
  assert.equal(getStateColor({ status: 'available', current_gwl_m_bgl: 3.2 }, 'depth'), '#22c55e');

  // Moderate depth (5-10m) -> yellow
  assert.equal(getStateColor({ status: 'available', current_gwl_m_bgl: 7.5 }, 'depth'), '#eab308');

  // Deep water table (10-20m) -> orange
  assert.equal(getStateColor({ status: 'available', current_gwl_m_bgl: 15.0 }, 'depth'), '#f97316');

  // Severely depleted (>20m) -> red
  assert.equal(getStateColor({ status: 'available', current_gwl_m_bgl: 28.4 }, 'depth'), '#ef4444');

  // Insufficient data -> neutral gray
  assert.equal(getStateColor({ status: 'insufficient_data', current_gwl_m_bgl: null }, 'depth'), '#e2e8f0');
  assert.equal(getStateColor(null, 'depth'), '#e2e8f0');
});

test('getStateColor accurately maps delta metric (positive = depletion, negative = recharge)', () => {
  // Substantial recharge (delta < -1.0m) -> dark green
  assert.equal(getStateColor({ status: 'available', projected_change_12m_m: -1.8 }, 'delta'), '#059669');

  // Mild recharge (-1.0 to 0.0m) -> green
  assert.equal(getStateColor({ status: 'available', projected_change_12m_m: -0.4 }, 'delta'), '#10b981');

  // Mild depletion (0.0 to 1.0m) -> amber
  assert.equal(getStateColor({ status: 'available', projected_change_12m_m: 0.6 }, 'delta'), '#f59e0b');

  // Significant depletion (delta > 1.0m) -> red
  assert.equal(getStateColor({ status: 'available', projected_change_12m_m: 2.3 }, 'delta'), '#ef4444');

  // Insufficient data -> neutral gray
  assert.equal(getStateColor({ status: 'insufficient_data', projected_change_12m_m: null }, 'delta'), '#e2e8f0');
});
