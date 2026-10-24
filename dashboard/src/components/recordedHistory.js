/** Reuse an available history value for display, keeping empty months null. */
export function recordedHistoryValue(row) {
  return Number.isFinite(row.observed) ? row.observed : Number.isFinite(row.filled) ? row.filled : null;
}

/** Select existing observed endpoints on the full calendar, without a short dataset. */
export function recordedHistoryGuideValue(observations) {
  const months = new Set(observations.map(row => row.month));
  return row => months.has(row.month) && Number.isFinite(row.observed) ? row.observed : null;
}

/** Visual guides join original observations only within an available calendar run. */
export function recordedHistoryObservationSegments(rows) {
  const segments = [];
  let observations = [];
  const finish = () => {
    if (observations.length > 1) segments.push(observations);
    observations = [];
  };
  for (const row of rows) {
    if (recordedHistoryValue(row) === null) finish();
    else if (Number.isFinite(row.observed)) observations.push(row);
  }
  finish();
  return segments;
}

/** Dashed bridges connect existing endpoints across missing periods, never new values. */
export function recordedHistoryGapSegments(rows) {
  const segments = [];
  let previous = null;
  let missing = false;
  for (const row of rows) {
    if (recordedHistoryValue(row) === null) missing = true;
    if (Number.isFinite(row.observed)) {
      if (previous && missing) segments.push([previous, row]);
      previous = row;
      missing = false;
    }
  }
  return segments;
}

/** Preserve calendar gaps; nulls never become invented measurements. */
export function recordedHistoryRows(history = []) {
  const byMonth = new Map();
  for (const row of history) {
    const month = String(row.month || row.date || '').slice(0, 7);
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) continue;
    byMonth.set(month, {
      month,
      observed: row.is_observed === true && row.is_imputed !== true && Number.isFinite(row.gwl) ? row.gwl : null,
      filled: row.is_imputed === true && row.is_observed !== true && Number.isFinite(row.gwl) ? row.gwl : null,
    });
  }
  const months = [...byMonth.keys()].sort();
  if (!months.length) return [];
  const ordinal = month => Number(month.slice(0, 4)) * 12 + Number(month.slice(5)) - 1;
  const start = ordinal(months[0]);
  const end = ordinal(months.at(-1));
  const result = [];
  for (let index = start; index <= end; index += 1) {
    const month = `${String(Math.floor(index / 12)).padStart(4, '0')}-${String(index % 12 + 1).padStart(2, '0')}`;
    result.push(byMonth.get(month) || { month, observed: null, filled: null });
  }
  return result;
}
