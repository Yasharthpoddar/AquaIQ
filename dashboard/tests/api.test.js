import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { fetchConfig, fetchDistrict, fetchHistory, fetchPredict, fetchScores, postSimulate } from '../src/api.js';

let originalFetch;
beforeEach(() => { originalFetch = globalThis.fetch; });
afterEach(() => { globalThis.fetch = originalFetch; });

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const jsonResponse = value => ({ ok: true, json: async () => value });

test('concurrent district reads share the network request, including JSON parsing', async () => {
  const body = deferred();
  const urls = [];
  globalThis.fetch = async url => {
    urls.push(url);
    return { ok: true, json: () => body.promise };
  };
  const first = fetchDistrict('GJ-Gandhinagar');
  await Promise.resolve();
  const repeatedEffect = fetchDistrict('GJ-Gandhinagar');
  assert.deepEqual(urls, ['/api/district/GJ-Gandhinagar']);
  const result = { crisis_score: 87, metadata: { name: 'Gandhinagar' } };
  body.resolve(result);
  assert.deepEqual(await Promise.all([first, repeatedEffect]), [result, result]);
});

test('completed GETs do not cache subsequent visits or refreshed scores', async () => {
  let reads = 0;
  globalThis.fetch = async () => jsonResponse({ scoring_run: ++reads });
  assert.equal((await fetchScores()).scoring_run, 1);
  assert.equal((await fetchScores()).scoring_run, 2);
  assert.equal(reads, 2);
});

test('different districts and prediction windows remain independent', async () => {
  const response = deferred();
  const urls = [];
  globalThis.fetch = url => { urls.push(url); return response.promise; };
  const requests = [fetchDistrict('AP-Krishna'), fetchDistrict('GJ-Gandhinagar'),
    fetchPredict('AP-Krishna'), fetchPredict('AP-Krishna', { window: 'next_six_months' })];
  assert.equal(new Set(urls).size, 4);
  assert.ok(urls.includes('/api/predict/AP-Krishna?window=next_six_months'));
  response.resolve(jsonResponse({ status: 'available' }));
  await Promise.all(requests);
});

test('failed shared HTTP reads reject all callers and a retry makes a new request', async () => {
  const response = deferred();
  let reads = 0;
  globalThis.fetch = () => { reads += 1; return response.promise; };
  const first = fetchConfig();
  const duplicate = fetchConfig();
  const rejected = [assert.rejects(first, /Config fetch failed: 503/), assert.rejects(duplicate, /Config fetch failed: 503/)];
  response.resolve({ ok: false, status: 503 });
  await Promise.all(rejected);
  assert.equal(reads, 1);
  globalThis.fetch = async () => { reads += 1; return jsonResponse({ ready: true }); };
  assert.deepEqual(await fetchConfig(), { ready: true });
  assert.equal(reads, 2);
});

test('network and invalid JSON failures clear pending reads for retries', async () => {
  globalThis.fetch = async () => { throw new Error('Connection lost'); };
  await assert.rejects(fetchHistory('AP-Krishna'), /Connection lost/);
  globalThis.fetch = async () => ({ ok: true, json: async () => { throw new Error('Invalid JSON'); } });
  await assert.rejects(fetchHistory('AP-Krishna'), /Invalid JSON/);
  globalThis.fetch = async () => jsonResponse({ data: [{ month: '2021-01', gwl: 3.35 }] });
  assert.equal((await fetchHistory('AP-Krishna')).data[0].gwl, 3.35);
});

test('simulation writes are never shared or cached', async () => {
  const response = deferred();
  const bodies = [];
  globalThis.fetch = (url, options) => { bodies.push(JSON.parse(options.body)); return response.promise; };
  const first = postSimulate({ district_id: 'AP-Krishna', rainfall_change: 0 });
  const second = postSimulate({ district_id: 'AP-Krishna', rainfall_change: 0 });
  assert.equal(bodies.length, 2);
  response.resolve(jsonResponse({ simulated_score: 30 }));
  assert.equal((await first).simulated_score, 30);
  assert.equal((await second).simulated_score, 30);
});

test('default history includes the source start and lets the API select the current end', async () => {
  const urls = [];
  globalThis.fetch = async url => { urls.push(url); return jsonResponse({ data: [] }); };
  await fetchHistory('RJ-Jaipur');
  await fetchHistory('RJ-Jaipur', '2025-01', '2026-01');
  assert.deepEqual(urls, [
    '/api/history/RJ-Jaipur?start=2002-01',
    '/api/history/RJ-Jaipur?start=2025-01&end=2026-01',
  ]);
});
