export const SIMULATION_PRESETS = Object.freeze([
  { id: 'baseline', label: 'Baseline', rainfallChange: 0, extractionChange: 0 },
  { id: 'drier', label: 'Drier monsoon', rainfallChange: -20, extractionChange: 0 },
  { id: 'wetter', label: 'Wetter monsoon', rainfallChange: 20, extractionChange: 0 },
  { id: 'higher-extraction', label: 'Higher extraction', rainfallChange: 0, extractionChange: 20 },
  { id: 'reduced-extraction', label: 'Reduced extraction', rainfallChange: 0, extractionChange: -20 },
  { id: 'combined', label: 'Combined stress', rainfallChange: -20, extractionChange: 20 },
].map(preset => Object.freeze(preset)));

export const INITIAL_SIMULATION_INPUTS = Object.freeze({ rainfallChange: 0, extractionChange: 0 });
export const TIER_COLORS = Object.freeze({ Safe: '#22c55e', Watch: '#eab308', Warning: '#f97316', Crisis: '#ef4444' });
const AVAILABLE_SOURCE_STATUSES = new Set(['success', 'historical_forecast']);

export function availableSimulationEvidence(status) {
  return AVAILABLE_SOURCE_STATUSES.has(status);
}

export function simulationInputReducer(inputs, action) {
  if (action.type === 'reset') return { ...INITIAL_SIMULATION_INPUTS };
  if (action.type === 'preset') {
    const preset = SIMULATION_PRESETS.find(value => value.id === action.id);
    return preset ? { rainfallChange: preset.rainfallChange, extractionChange: preset.extractionChange } : inputs;
  }
  if (action.type === 'change' && ['rainfallChange', 'extractionChange'].includes(action.field)) {
    return { ...inputs, [action.field]: action.value };
  }
  return inputs;
}

export function selectedSimulationPreset(inputs) {
  return SIMULATION_PRESETS.find(preset => preset.rainfallChange === inputs.rainfallChange
    && preset.extractionChange === inputs.extractionChange) || null;
}

export function validSimulationInputs(inputs) {
  return inputs != null && [inputs.rainfallChange, inputs.extractionChange]
    .every(value => typeof value === 'number' && Number.isFinite(value) && value >= -100 && value <= 100);
}

export function simulationPayload(districtId, inputs) {
  if (typeof districtId !== 'string' || !districtId.trim() || !validSimulationInputs(inputs)) {
    throw new Error('Select a district and use finite percentage changes between −100% and +100%.');
  }
  return {
    district_id: districtId,
    rainfall_change_pct: inputs.rainfallChange,
    extraction_change_pct: inputs.extractionChange,
  };
}

export function validSimulationScore(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100;
}

export function simulationTier(value) {
  return typeof value === 'string' && Object.hasOwn(TIER_COLORS, value) ? value : null;
}

export function formatSimulationNumber(value, signed = false) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'Unavailable';
  return `${signed && value > 0 ? '+' : ''}${value}`;
}

function resultShell(scenario) {
  return {
    id: scenario.id,
    label: scenario.label,
    rainfallChange: scenario.rainfallChange,
    extractionChange: scenario.extractionChange,
    baselineScore: null,
    baselineTier: null,
    scenarioScore: null,
    scenarioTier: null,
    delta: null,
    observedDate: null,
    sourceStatus: null,
    status: 'unavailable',
    message: '',
  };
}

export function normalizeSimulationResult(data, districtId, scenario) {
  const result = resultShell(scenario);
  if (!data || typeof data !== 'object' || Array.isArray(data) || data.district_id !== districtId) {
    return { ...result, message: 'The service returned an incompatible district response. Retry this scenario.' };
  }
  result.sourceStatus = typeof data.status === 'string' ? data.status : null;
  result.observedDate = typeof data.last_observed_date === 'string' ? data.last_observed_date : null;
  // Unavailable evidence must stay unavailable even if an invalid response also contains numbers.
  if (!availableSimulationEvidence(data.status)) {
    return { ...result, message: data.status === 'insufficient_data'
      ? 'Insufficient model evidence for this district.' : 'Scenario evidence is unavailable.' };
  }
  result.baselineScore = validSimulationScore(data.baseline_score) ? data.baseline_score : null;
  result.baselineTier = result.baselineScore !== null ? simulationTier(data.baseline_tier) : null;
  result.scenarioScore = validSimulationScore(data.simulated_score) ? data.simulated_score : null;
  result.scenarioTier = result.scenarioScore !== null ? simulationTier(data.simulated_tier) : null;
  if (result.baselineScore === null || result.scenarioScore === null) {
    return { ...result, scenarioScore: null, scenarioTier: null,
      message: 'A valid baseline and scenario index are both required.' };
  }
  // Derive the displayed difference from the same API scores used by the table and bars.
  result.delta = Number((result.scenarioScore - result.baselineScore).toFixed(10));
  result.status = 'available';
  return result;
}

// A single active run and sequential requests keep the existing endpoint's workload bounded.
// Returning null for a repeated call protects against double clicks before React rerenders.
export function createScenarioRunner(request) {
  let running = false;
  return async ({ districtId, scenarios, onResult = () => {}, shouldContinue = () => true }) => {
    if (running) return null;
    if (!Array.isArray(scenarios) || !scenarios.length) throw new Error('Choose at least one scenario.');
    scenarios.forEach(scenario => simulationPayload(districtId, scenario));
    running = true;
    const rows = [];
    try {
      for (const scenario of scenarios) {
        if (!shouldContinue()) break;
        let result;
        try {
          const data = await request(simulationPayload(districtId, scenario));
          result = normalizeSimulationResult(data, districtId, scenario);
        } catch (error) {
          result = { ...resultShell(scenario), status: 'error',
            message: error instanceof Error && error.message ? error.message : 'This scenario could not be evaluated.' };
        }
        rows.push(result);
        if (shouldContinue()) onResult([...rows]);
      }
      return rows;
    } finally {
      running = false;
    }
  };
}

export function canExportComparison(comparison) {
  return comparison?.completed === true && Array.isArray(comparison.rows) && comparison.rows.length > 0;
}

// Escape spreadsheet formula prefixes in text fields, retaining real numeric negatives.
export function simulationCsvCell(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  let text = String(value ?? '');
  if (/^\s*[=+@-]/u.test(text) || /^[\t\r\n]/u.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function comparisonCsv(comparison) {
  if (!canExportComparison(comparison)) return '';
  const header = ['district_id', 'district_name', 'state', 'scenario', 'rainfall_change_pct',
    'extraction_change_pct', 'baseline_score', 'baseline_tier', 'scenario_score', 'scenario_tier',
    'delta', 'availability_status', 'source_status', 'last_observed_date', 'message'];
  const rows = comparison.rows.map(row => [comparison.district.district_id, comparison.district.name,
    comparison.district.state, row.label, row.rainfallChange, row.extractionChange, row.baselineScore,
    row.baselineTier, row.scenarioScore, row.scenarioTier, row.delta, row.status, row.sourceStatus,
    row.observedDate, row.message]);
  return [header, ...rows].map(row => row.map(simulationCsvCell).join(',')).join('\r\n');
}
