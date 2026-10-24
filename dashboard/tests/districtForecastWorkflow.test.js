import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { loadJsx } from './helpers/loadJsx.js';

const { default: DistrictDetail } = await loadJsx(new URL('../src/pages/DistrictDetail.jsx', import.meta.url));
const { default: DistrictForecastGraph } = await loadJsx(new URL('../src/components/DistrictForecastGraph.jsx', import.meta.url));
const { default: ExperimentalScenario } = await loadJsx(new URL('../src/components/ExperimentalScenario.jsx', import.meta.url));

test('the actual district graph entry mounts only its own experimental scenario', () => {
  for (const districtId of ['HR-Kaithal', 'HR-Kurukshetra', 'TS-Adilabad', 'AN-Nicobars']) {
    const graph = DistrictForecastGraph({ districtId });
    assert.equal(graph.type, ExperimentalScenario);
    assert.equal(graph.props.districtId, districtId);
    assert.equal(graph.key, districtId, 'district change remounts the independent read state');
  }
});

test('actual district routes ignore old historical query choices and keep the monthly card mounted during loading', () => {
  for (const path of ['/district/HR-Kaithal', '/district/HR-Kurukshetra?view=historical',
    '/district/TS-Adilabad?origin_month=2024-01#forecast-graph', '/district/AN-Nicobars?view=scenario']) {
    const html = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: [path] },
      createElement(Routes, null, createElement(Route, { path: '/district/:id', element: createElement(DistrictDetail) }))));
    assert.match(html, /Next 12 months/);
    assert.match(html, /Experimental estimate/);
    assert.match(html, /Loading this district/);
    assert.doesNotMatch(html, /Historical M\+12 research|Groundwater graph view|forecast-origin-month|Latest observed origin|Observed origin month/);
  }
});
