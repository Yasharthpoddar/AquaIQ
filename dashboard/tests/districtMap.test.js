import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { boundaryCoverage, buildScoreLookup, districtBoundaries, matchDistrict } from '../src/districtMap.js';

test('state polygons in the actual source cannot obscure the district map', () => {
  const source = JSON.parse(readFileSync(new URL('../public/india_districts.geojson', import.meta.url), 'utf8'));
  const districts = districtBoundaries(source);
  assert.equal(source.features.length, 760);
  assert.equal(districts.features.length, 726);
  assert.ok(districts.features.every(feature => feature.properties.district));
  assert.equal(source.features.length - districts.features.length, 34);
});

test('district name matches stay within the same state and preserve zero scores', () => {
  const scores = [
    { district_id: 'CG-Bilaspur', name: 'Bilaspur', state: 'Chhattisgarh', score: 0 },
    { district_id: 'HP-Bilaspur', name: 'Bilaspur', state: 'Himachal Pradesh', score: 92 },
  ];
  const lookup = buildScoreLookup(scores);
  assert.equal(matchDistrict({ district: 'Bilaspur', st_nm: 'Chhattisgarh' }, lookup), scores[0]);
  assert.equal(matchDistrict({ district: 'Bilaspur', st_nm: 'Himachal Pradesh' }, lookup), scores[1]);
  assert.equal(matchDistrict({ district: 'Bilaspur', st_nm: 'Gujarat', district_id: 'HP-Bilaspur' }, lookup), null);
  assert.equal(matchDistrict({ district: 'Bilaspur' }, lookup), null);
});

test('coverage reports a missing Mumbai Suburban boundary without borrowing Mumbai geometry', () => {
  const source = JSON.parse(readFileSync(new URL('../public/india_districts.geojson', import.meta.url), 'utf8'));
  const scores = [
    { district_id: 'MH-Mumbai', name: 'Mumbai', state: 'Maharashtra' },
    { district_id: 'MH-Mumbai_Suburban', name: 'Mumbai Suburban', state: 'Maharashtra' },
  ];
  const coverage = boundaryCoverage(districtBoundaries(source), scores);
  assert.equal(coverage.mapped, 1);
  assert.deepEqual(coverage.missing, [scores[1]]);
});

test('malformed boundary responses fail visibly and empty coverage is explicit', () => {
  assert.throws(() => districtBoundaries({}), /no features/);
  assert.deepEqual(boundaryCoverage({ features: [] }, []), { mapped: 0, missing: [] });
});
