import { useEffect, useState } from 'react';
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend, ReferenceLine } from 'recharts';
import { fetchStateMedianPredict, fetchPrimaryStateHistory } from '../api.js';
import {
  validateStateMedianForecast,
  stateMedianChartRows,
  stateRecordedHistoryRows,
  state12mPredictionRows,
  medianForecastMethod,
  medianMethodLabel,
  validateStateMedianHistory,
  stateHistoryKey,
  currentStateHistoryRead,
  medianSummaryRecords,
  referenceAgeMonths,
} from './stateMedianForecastContract.js';
import {
  recordedHistoryGuideValue,
  recordedHistoryObservationSegments,
  recordedHistoryGapSegments,
} from './recordedHistory.js';
import { formatStateMonth } from './StateForecastGraph.jsx';

const depth = value => Number.isFinite(value) ? `${value.toFixed(2)} m bgl` : 'Unavailable';
const errorDistance = value => Number.isFinite(value) ? `${value.toFixed(2)} m` : 'Unavailable';

export async function loadStateMedianForecast(stateId, asOf = null, fetcher = fetchStateMedianPredict) {
  return validateStateMedianForecast(await fetcher(stateId, asOf), stateId, asOf);
}

export async function loadFullStateMedianHistory(forecast, fetcher = fetchPrimaryStateHistory) {
  return validateStateMedianHistory(await fetcher(forecast.state_id, forecast.as_of, forecast.generation_id), forecast);
}

export function useStateMedianHistory(forecast) {
  const [read, setRead] = useState(null), [retry, setRetry] = useState(0);
  const key = stateHistoryKey(forecast);
  useEffect(() => {
    if (!key || forecast.status === 'model_unavailable') return;
    let cancelled = false;
    setRead({ key, loading: true, value: null, error: null });
    loadFullStateMedianHistory(forecast).then(value => {
      if (!cancelled) setRead({ key, loading: false, value, error: null });
    }).catch(error => {
      if (!cancelled) setRead({ key, loading: false, value: null, error: error.message || 'Full state history unavailable.' });
    });
    return () => { cancelled = true; };
  }, [key, retry]);
  const current = currentStateHistoryRead(read, forecast);
  return { ...current, loading: Boolean(key && forecast.status !== 'model_unavailable' && (!current || current.loading)), onRetry: () => setRetry(value => value + 1) };
}

export function StateMedianCoverageCard({ summary, loading = false }) {
  const records = medianSummaryRecords(summary);
  return <article className="card"><span>States with complete 12-month forecasts</span><strong>{records ? <>{records.available} <small>/ {summary.total_states}</small></> : loading ? 'Loading…' : 'Unverified'}</strong>
    {records && <><small>{records.xgboost} XGBoost · {records.persistence} persistence fallback · {records.unavailable} unavailable</small><small>{records.forecastMonths} forecast-month values</small></>}
    <small>Availability does not establish accuracy</small></article>;
}

/** Legacy combined tooltip maintained for compatibility with existing tests */
export function StateMedianTooltip({ active, payload }) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  const measured = row.observed ?? row.lowCoverage;
  return <div className="state-chart-tooltip" role="tooltip" style={{ background: '#fff', border: '1px solid #cbd5e1', borderRadius: 10, padding: '.75rem .9rem', boxShadow: '0 4px 12px #0f172a15', maxWidth: 300, fontSize: '.82rem', lineHeight: 1.5 }}><strong>{formatStateMonth(row.month)}</strong>{row.stateName && <p>{row.stateName}</p>}
    {Number.isFinite(measured) && <><p>{row.lowCoverage !== null ? 'Genuine low-coverage historical median' : 'Observed historical state median'}: {depth(measured)}</p>{Number.isInteger(row.districts) && Number.isInteger(row.registered) && <p>{row.districts} / {row.registered} reporting districts{Number.isFinite(row.coverage) ? ` · ${row.coverage.toFixed(1)}% coverage` : ''}</p>}{Number.isInteger(row.observations) && <p>{row.observations} valid district-month observations</p>}{row.lowCoverage !== null && <p>Excluded from training targets; shown as a separate point.</p>}</>}
    {Number.isFinite(row.predicted) && <><p>{row.method || 'Median forecast'} · M+{row.horizon}: {depth(row.predicted)}</p>{row.referenceDate && <p>Genuine reference observation: {row.referenceDate}</p>}{row.latestObservationDate && row.latestObservationDate !== row.referenceDate && <p>Latest genuine observation: {row.latestObservationDate}</p>}{Number.isInteger(row.referenceDistricts) && Number.isInteger(row.referenceRegistered) && <p>Historical reference: {row.referenceDistricts} / {row.referenceRegistered} districts{Number.isFinite(row.referenceCoverage) ? ` · ${row.referenceCoverage.toFixed(1)}% coverage` : ''}. Forecast-period coverage is not observed.</p>}</>}
    {!Number.isFinite(measured) && !Number.isFinite(row.predicted) && <p>No observed state median for this month</p>}
  </div>;
}

/** Legacy combined plot maintained for compatibility with existing tests */
export function stateMedianForecastPlot(value, dimensions = {}) {
  const fallback = medianForecastMethod(value) === 'persistence_fallback';
  return <LineChart {...dimensions} data={stateMedianChartRows(value)} margin={{ top: 16, right: 20, bottom: 10, left: 12 }} accessibilityLayer>
    <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#e2e8f0" />
    <XAxis dataKey="month" tickFormatter={formatStateMonth} minTickGap={45} tickLine={false} tick={{ fontSize: 12, fill: '#475569' }} />
    <YAxis width={66} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: '#475569' }} label={{ value: 'Depth (m below ground)', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle', fill: '#475569', fontSize: 12 } }} />
    <Tooltip trigger="hover" shared filterNull={false} content={<StateMedianTooltip />} isAnimationActive={false} cursor={{ stroke: '#64748b', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 20, pointerEvents: 'none' }} /><Legend wrapperStyle={{ fontSize: 13, paddingTop: 12 }} />
    <ReferenceLine x={value.forecast_origin.slice(0, 7)} stroke="#64748b" strokeDasharray="4 4" label={{ value: 'Forecast origin', position: 'insideTopRight', fontSize: 11 }} />
    <Line dataKey="observed" name="Observed district median" stroke="#2563eb" strokeWidth={1.2} dot={{ r: 3, fill: '#fff', strokeWidth: 1.2 }} activeDot={{ r: 5, fill: '#fff' }} connectNulls={false} isAnimationActive={false} />
    <Line dataKey="lowCoverage" name="Low coverage observation" stroke="#94a3b8" strokeWidth={0} legendType="circle" dot={{ r: 3, fill: '#94a3b8', stroke: '#94a3b8' }} connectNulls={false} isAnimationActive={false} />
    <Line dataKey="predicted" name={fallback ? 'Persistence fallback forecast' : `${medianMethodLabel(value)} forecast`} stroke="#0f766e" strokeWidth={1.8} strokeDasharray="6 3" dot={{ r: 3, fill: '#fff', strokeWidth: 2 }} activeDot={{ r: 5, fill: '#fff' }} connectNulls={false} isAnimationActive={false} />
  </LineChart>;
}

/** Tooltip for Graph 1: Recorded History */
export function StateRecordedHistoryTooltip({ active = false, label, payload, rows = [] }) {
  if (!active) return null;
  const row = payload?.[0]?.payload || rows.find(item => item.month === String(label));
  if (!row) return null;
  const isObserved = Number.isFinite(row.observed);
  const isFilled = Number.isFinite(row.filled);
  const isLowCoverage = Number.isFinite(row.lowCoverage);
  const val = isObserved ? row.observed : isLowCoverage ? row.lowCoverage : isFilled ? row.filled : null;
  const month = new Date(`${row.month}-01T00:00:00Z`).toLocaleDateString('en', { month: 'long', year: 'numeric', timeZone: 'UTC' });

  return (
    <div
      role="tooltip"
      aria-label="Recorded state groundwater history details"
      className="history-tooltip state-history-tooltip"
      style={{
        background: '#fff',
        border: '1px solid #cbd5e1',
        borderRadius: 10,
        padding: '.75rem .9rem',
        boxShadow: '0 4px 12px rgba(15,23,42,0.12)',
        maxWidth: 280,
        fontSize: '.82rem',
        lineHeight: 1.5,
      }}
    >
      <strong>{month}</strong>
      {row.stateName && <p style={{ color: '#475569', margin: '2px 0 0' }}>{row.stateName}</p>}
      {val !== null ? (
        <>
          <p style={{ color: isObserved ? '#2563eb' : '#64748b', marginTop: '.25rem', fontWeight: 600 }}>
            {isObserved ? 'Observed state median' : isLowCoverage ? 'Low-coverage observation' : 'Forward-filled value'}
          </p>
          <strong style={{ fontSize: '1.05rem' }}>{val.toFixed(2)} m below ground</strong>
          {Number.isInteger(row.districts) && Number.isInteger(row.registered) && (
            <p style={{ margin: '4px 0 0' }}>
              {row.districts} / {row.registered} reporting districts
              {Number.isFinite(row.coverage) ? ` · ${row.coverage.toFixed(1)}% coverage` : ''}
            </p>
          )}
          {Number.isInteger(row.observations) && (
            <p style={{ margin: '2px 0 0' }}>{row.observations} valid district-month observations</p>
          )}
          {isFilled && !isObserved && <p style={{ color: '#64748b', margin: '4px 0 0' }}>Not a new measurement.</p>}
          {isLowCoverage && <p style={{ color: '#64748b', margin: '4px 0 0' }}>Excluded from XGBoost training targets.</p>}
        </>
      ) : (
        <>
          <p style={{ marginTop: '.25rem' }}>No recorded value for this month.</p>
          <p style={{ color: '#64748b' }}>Dashed connection is a visual guide only.</p>
        </>
      )}
    </div>
  );
}

/** Plot for Graph 1: Recorded History */
export function stateRecordedHistoryPlot(rows, dimensions = {}) {
  return (
    <LineChart {...dimensions} data={rows} margin={{ top: 16, right: 20, bottom: 10, left: 12 }} accessibilityLayer>
      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
      <XAxis dataKey="month" allowDuplicatedCategory={false} minTickGap={45} tickLine={false} tick={{ fontSize: 12, fill: '#475569' }} />
      <YAxis width={66} tickLine={false} tick={{ fontSize: 12, fill: '#475569' }} label={{ value: 'Depth (m below ground)', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle', fill: '#475569', fontSize: 12 } }} />
      <Tooltip trigger="hover" shared filterNull={false} content={<StateRecordedHistoryTooltip rows={rows} />} isAnimationActive={false} cursor={{ stroke: '#64748b', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 20, pointerEvents: 'none' }} />
      <Legend itemSorter={item => item.value === 'Observed district median' ? 0 : 1} wrapperStyle={{ fontSize: 13, paddingTop: 12 }} />
      {recordedHistoryGapSegments(rows).map(segment => (
        <Line key={`gap-${segment[0].month}`} className="history-gap-guide" dataKey={recordedHistoryGuideValue(segment)} name="Missing-period guide" type="linear" stroke="#2563eb" strokeWidth={1.2} strokeDasharray="5 5" strokeOpacity={0.65} dot={false} activeDot={false} legendType="none" tooltipType="none" connectNulls isAnimationActive={false} />
      ))}
      {recordedHistoryObservationSegments(rows).map(segment => (
        <Line key={segment[0].month} className="history-observation-guide" dataKey={recordedHistoryGuideValue(segment)} name="Observation guide" type="linear" stroke="#2563eb" strokeWidth={1.2} dot={false} activeDot={false} legendType="none" tooltipType="none" connectNulls isAnimationActive={false} />
      ))}
      <Line dataKey="observed" name="Observed district median" stroke="#2563eb" strokeWidth={1.2} dot={{ r: 3, fill: '#fff', strokeWidth: 1.2 }} activeDot={{ r: 5, fill: '#fff' }} connectNulls={false} isAnimationActive={false} />
      <Line dataKey="lowCoverage" name="Low coverage observation" stroke="#94a3b8" strokeWidth={0} legendType="circle" dot={{ r: 3, fill: '#94a3b8', stroke: '#94a3b8' }} connectNulls={false} isAnimationActive={false} />
      <Line dataKey="filled" name="Forward-filled history" stroke="#94a3b8" strokeWidth={1} dot={{ r: 1.8, fill: '#fff', strokeWidth: 1 }} connectNulls={false} strokeDasharray="3 3" isAnimationActive={false} />
    </LineChart>
  );
}

/** Tooltip for Graph 2: 12-Month Groundwater Prediction */
export function State12mPredictionTooltip({ active = false, payload }) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  const month = new Date(`${row.month}-01T00:00:00Z`).toLocaleDateString('en', { month: 'long', year: 'numeric', timeZone: 'UTC' });
  const methodTitle = row.isFallback ? 'Persistence Fallback' : 'XGBoost Forecast';

  return (
    <div
      role="tooltip"
      aria-label="12-month prediction details"
      className="forecast-tooltip state-forecast-tooltip"
      style={{
        background: '#fff',
        border: '1px solid #cbd5e1',
        borderRadius: 8,
        padding: '0.65rem 0.85rem',
        boxShadow: '0 4px 12px rgba(15,23,42,0.12)',
        fontSize: '0.82rem',
        lineHeight: 1.45,
        maxWidth: 280,
      }}
    >
      <strong>{month} (M+{row.horizon})</strong>
      {row.stateName && <p style={{ color: '#475569', margin: '2px 0 0' }}>{row.stateName}</p>}
      <div style={{ color: '#0f766e', fontWeight: 600, marginTop: '0.25rem' }}>
        {methodTitle}: {Number.isFinite(row.predicted) ? `${row.predicted.toFixed(2)} m below ground` : 'Unavailable'}
      </div>
      {row.isFallback ? (
        <div style={{ color: '#64748b', fontSize: '0.78rem', marginTop: '0.25rem' }}>
          Reference observation: {row.referenceDate || 'unavailable'}
          {Number.isInteger(row.referenceAge) ? ` (${row.referenceAge} months old)` : ''}
          <br />Latest genuine observed state median held constant.
        </div>
      ) : (
        <div style={{ color: '#64748b', fontSize: '0.78rem', marginTop: '0.25rem' }}>
          Assumed historical climatology inputs · 12-month horizon
        </div>
      )}
    </div>
  );
}

/** Plot for Graph 2: 12-Month Groundwater Prediction */
export function state12mPredictionPlot(rows, value, dimensions = {}) {
  const fallback = medianForecastMethod(value) === 'persistence_fallback';
  return (
    <LineChart {...dimensions} data={rows} margin={{ top: 16, right: 20, bottom: 8, left: 12 }} accessibilityLayer>
      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
      <XAxis dataKey="month" tickFormatter={formatStateMonth} minTickGap={26} tickLine={false} tick={{ fontSize: 12, fill: '#475569' }} />
      <YAxis width={66} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: '#475569' }} label={{ value: 'Depth (m below ground)', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle', fill: '#475569', fontSize: 12 } }} />
      <Tooltip trigger="hover" content={<State12mPredictionTooltip />} isAnimationActive={false} cursor={{ stroke: '#64748b', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 20, pointerEvents: 'none' }} />
      <Legend wrapperStyle={{ fontSize: 13, paddingTop: 12 }} />
      <Line
        dataKey="predicted"
        name={fallback ? 'Persistence fallback estimate' : 'XGBoost forecast'}
        stroke="#0f766e"
        strokeWidth={1.8}
        strokeDasharray="6 3"
        dot={{ r: 3, fill: '#fff', strokeWidth: 2 }}
        activeDot={{ r: 5, fill: '#fff' }}
        connectNulls={false}
        isAnimationActive={false}
      />
    </LineChart>
  );
}

export function StateMedianForecastView({
  value = null,
  loading = false,
  error = null,
  onRetry = () => {},
  fullHistory = null,
  historyLoading = false,
  historyError = null,
  onHistoryRetry = () => {},
}) {
  const validatedHistory = fullHistory && value ? validateStateMedianHistory(fullHistory, value) : null;
  const historySource = validatedHistory?.history || value?.history || [];
  const stateName = value?.state_name || value?.state_id || '';
  const historyRows = stateRecordedHistoryRows(historySource, stateName);
  const predictionRows = state12mPredictionRows(value);

  const hasHistory = historyRows.some(row => Number.isFinite(row.observed) || Number.isFinite(row.filled) || Number.isFinite(row.lowCoverage));
  const firstGenuine = historySource.find(row => Number.isFinite(row.gwl_m_bgl) && row.is_observed !== false && row.is_imputed !== true && row.is_forecast !== true);
  const noFullObservations = Boolean(fullHistory && !firstGenuine);
  const earliestQualified = validatedHistory?.earliest_eligible_date ?? historySource.find(row => row.training_eligible)?.date;
  const evaluation = value?.evaluation;
  const fallback = medianForecastMethod(value) === 'persistence_fallback';
  const referenceAge = referenceAgeMonths(value);
  const hasPrediction = value?.status === 'forecast' && predictionRows.length === 12;

  const evaluationContext = evaluation && (
    <>
      <p>
        {evaluation.n
          ? `Evaluation: ${evaluation.period_start}–${evaluation.period_end}; ${evaluation.n} eligible forecast cases${Number.isInteger(evaluation.unique_state_month_targets) ? ` from ${evaluation.unique_state_month_targets} distinct state-month targets` : ''}${Number.isInteger(evaluation.states_evaluated) ? ` across ${evaluation.states_evaluated} ${evaluation.states_evaluated === 1 ? 'state' : 'states'}` : ''}. ${evaluation.horizons?.length ? `Evaluated horizons: ${evaluation.horizons.map(h => `M+${h}`).join(', ')}.` : 'Evaluated horizon coverage is unavailable.'}`
          : evaluation.description || 'Insufficient eligible historical targets for a held-out backtest.'} Historical backtest errors do not establish accuracy across the next 12 months.
      </p>
      {evaluation.n > 0 && (
        <p>
          {evaluation.artifact_role === 'frozen_historical_reference'
            ? `These errors describe a frozen historical reference artifact trained through ${evaluation.evaluated_artifact_training_cutoff || 'its documented cutoff'}, rather than a held-out test of the refitted serving artifact. `
            : ''}
          {evaluation.description} Repeated state-month targets across origins are dependent.
        </p>
      )}
      {Number.isInteger(evaluation.comparison_states_evaluated) && Number.isInteger(evaluation.comparison_unique_state_month_targets) && (
        <p>
          Overall paired historical comparison: {evaluation.comparison_states_evaluated} states and {evaluation.comparison_unique_state_month_targets} distinct state-month targets. Error metrics above describe the selected state's evaluation sample.
        </p>
      )}
    </>
  );

  if (loading) {
    return (
      <section className="card state-chart-card state-median-card" aria-label="State median forecast loading">
        <div className="forecast-placeholder" role="status">
          <span className="loading-spinner" />Loading state median evidence…
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="card state-chart-card state-median-card" aria-label="State median forecast error">
        <div className="inline-state error-state" role="alert">
          <p>{error}</p>
          <button className="button button-secondary" onClick={onRetry} type="button">Retry state median</button>
        </div>
      </section>
    );
  }

  if (!value) {
    return (
      <section className="card state-chart-card state-median-card" aria-label="State median forecast">
        <p className="inline-state" role="status">Select a state to inspect its median groundwater forecast.</p>
      </section>
    );
  }

  return (
    <>
      {/* Graph 1: Recorded History */}
      <section className="card history-card state-history-card" aria-label="Recorded groundwater history">
        <header className="section-heading">
          <div>
            <h2>Recorded History</h2>
            <p className="muted">
              Depth in metres below ground across reporting districts · {stateName}
            </p>
          </div>
        </header>
        <p className="forecast-note">
          Depth is measured in metres below ground (m bgl). Larger values mean a deeper water table. Depth below ground is not the same as total groundwater volume or availability.
        </p>
        {historyLoading && (
          <div className="forecast-placeholder" role="status">
            <span className="loading-spinner" />Loading recorded state history…
          </div>
        )}
        {historyError && (
          <div className="inline-state error-state" role="alert">
            <p>Full history unavailable: {historyError}. Showing only the history window bundled with this forecast.</p>
            <button className="button button-secondary" type="button" onClick={onHistoryRetry}>Retry full history</button>
          </div>
        )}
        {!historyLoading && !hasHistory && (
          <p className="inline-state" role="status">
            {noFullObservations || medianForecastMethod(value) === 'no_observations'
              ? 'The matching release source contains no genuine groundwater observations for this state.'
              : 'No groundwater observations are available for this state.'}
          </p>
        )}
        {!historyLoading && hasHistory && (
          <>
            {fullHistory && firstGenuine && (
              <p className="forecast-note">
                First genuine state median: {formatStateMonth(fullHistory.earliest_observation_date || firstGenuine.date)}. {earliestQualified ? `First coverage-qualified state median: ${formatStateMonth(earliestQualified)}.` : 'No historical month meets the XGBoost training-target coverage criteria; genuine low-coverage medians appear as grey points only.'}
              </p>
            )}
            <div className="chart-caption">
              <span>
                {fullHistory ? 'Full source history' : 'History window bundled with forecast'}
                {firstGenuine ? ` · ${formatStateMonth(firstGenuine.date)}–${formatStateMonth(historySource.at(-1).date)}` : ''}
              </span>
              <span>Higher depth = deeper water table</span>
            </div>
            <div className="state-chart">
              <ResponsiveContainer width="100%" height={360}>
                {stateRecordedHistoryPlot(historyRows)}
              </ResponsiveContainer>
            </div>
            <p className="compact-note">
              Hover or tap the chart for monthly values. Blue lines join eligible observations; dashed portions bridge missing periods as visual guides only. Grey points are forward fills or low-coverage medians, not new training targets. Depth in metres below ground does not represent total groundwater volume.
            </p>
          </>
        )}
      </section>

      {/* Graph 2: 12-Month Groundwater Prediction */}
      <section className="card forecast-card state-forecast-card" aria-label="12-Month groundwater prediction">
        <header className="section-heading">
          <div>
            <h2>12-Month Groundwater Prediction</h2>
            <p className="muted">
              State median forecast · next 12 full calendar months · m bgl
            </p>
          </div>
          <span className="experimental-badge">
            {fallback ? 'Limited-history fallback' : 'Limited historical evidence'}
          </span>
        </header>
        <p className="forecast-note">
          The median represents the typical district among districts observed that month. It does not measure groundwater volume, total availability or the most severely depleted district. Higher depth means a lower water table.
        </p>
        <p className="forecast-note">
          Forecast vintage: {value.as_of}. Generated {value.computed_at}. Model {value.model_version}; {fallback ? 'persistence uses no fitted model' : `training cutoff ${value.training_cutoff || 'unavailable'}`}.
        </p>
        {fallback && (
          <div className="inline-state" role="note">
            <strong>Persistence fallback</strong>
            <p>The latest genuine observed state median is held constant for all 12 forecast months. This fallback does not use XGBoost and does not estimate an emerging trend.</p>
            <p>XGBoost was not used: {value.fallback_reason}</p>
          </div>
        )}
        {value.historical_reference_date && (
          <p className="forecast-note">
            Reference observation: {value.historical_reference_date}{Number.isInteger(referenceAge) ? ` · ${referenceAge} months old at this vintage` : ''}. {value.reference_training_eligible === false ? 'Reference coverage is below the XGBoost training-target criteria; it remains a genuine observation.' : ''}{value.reference_is_stale === true || (Number.isInteger(referenceAge) && referenceAge > 12) ? ' This is a stale historical measurement, not a recent reading.' : ''}
          </p>
        )}
        {value.latest_observation_date && value.latest_observation_date !== value.historical_reference_date && (
          <p className="forecast-note">
            Latest genuine observation: {value.latest_observation_date} · {value.observation_age_months} months old. The forecast method uses the separately dated reference above.
          </p>
        )}
        {value.status !== 'forecast' && (
          <div className="inline-state" role="status">
            <h3>
              {noFullObservations || medianForecastMethod(value) === 'no_observations'
                ? 'No usable groundwater observations'
                : value.status === 'insufficient_data'
                ? 'Insufficient historical data for this model'
                : 'Median forecast unavailable'}
            </h3>
            <p>
              {noFullObservations
                ? 'The matching release source contains no genuine groundwater observations for this state.'
                : value.message}
            </p>
            <button className="button button-secondary" type="button" onClick={onRetry}>Retry state median</button>
          </div>
        )}
        <dl className="state-median-evidence">
          <div>
            <dt>Historical reference coverage</dt>
            <dd>{value.contributing_districts_count} / {value.total_districts_in_state} districts · {value.district_coverage_pct.toFixed(1)}%</dd>
          </div>
          <div>
            <dt>Held-out backtest MAE</dt>
            <dd>{evaluation?.n ? errorDistance(evaluation.mae_m) : 'Unavailable'}</dd>
          </div>
          <div>
            <dt>Held-out backtest RMSE</dt>
            <dd>{evaluation?.n ? errorDistance(evaluation.rmse_m) : 'Unavailable'}</dd>
          </div>
        </dl>
        <p className="forecast-note">
          {evaluation?.n ? `Historical error period: ${evaluation.period_start}–${evaluation.period_end}. ` : 'Historical error estimates are unavailable for this method. '}Forecast accuracy is not guaranteed; sample and horizon details are below.
        </p>
        {hasPrediction && (
          <>
            <div className="forecast-context" style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', margin: '14px 0', color: '#475569', fontSize: '.86rem' }}>
              <span>Forecast origin: {value.forecast_origin.slice(0, 7)}</span>
              <span>Forecast period: {formatStateMonth(value.forecast[0].target_date)} – {formatStateMonth(value.forecast.at(-1).target_date)}</span>
              <span>Vintage: {value.as_of}</span>
            </div>
            <div className="state-chart">
              <ResponsiveContainer width="100%" height={320}>
                {state12mPredictionPlot(predictionRows, value)}
              </ResponsiveContainer>
            </div>
            <details className="monthly-values">
              <summary>View all 12 median estimates</summary>
              <div className="table-scroll">
                <table className="data-table">
                  <caption>{value.state_name || value.state_id} · district median · m bgl</caption>
                  <thead>
                    <tr>
                      <th scope="col">Month</th>
                      <th scope="col">Horizon</th>
                      <th scope="col">Predicted median depth</th>
                    </tr>
                  </thead>
                  <tbody>
                    {value.forecast.map(row => (
                      <tr key={row.target_date}>
                        <th scope="row">{formatStateMonth(row.target_date)}</th>
                        <td>M+{row.horizon}</td>
                        <td>{depth(row.predicted_gwl)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        )}
        <details className="technical-details">
          <summary>Median model, backtest details and limitations</summary>
          <p>Policy: {value.model_name} · {value.model_version}. Method: {medianMethodLabel(value)}. Status: {value.status}; promotion: {value.promotion_status}.</p>
          <p>As of {value.as_of}; generated {value.computed_at}. Training cutoff: {value.training_cutoff || (fallback ? 'Not applicable to persistence' : 'No eligible model trained')}.</p>
          {Number.isInteger(value.genuine_observed_months) && <p>{value.genuine_observed_months} genuine observed state months; {value.genuine_observation_count} valid district-month observations.</p>}
          <p>Evaluation status: {evaluation?.status}.</p>
          {evaluationContext}
          {value.limitations?.length > 0 && (
            <ul>
              {value.limitations.map(item => <li key={item}>{item}</li>)}
            </ul>
          )}
        </details>
      </section>
    </>
  );
}

export default function StateMedianForecast({ stateId, asOf = null }) {
  const [read, setRead] = useState(null), [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!stateId) return;
    let cancelled = false;
    setRead({ stateId, asOf, loading: true, value: null, error: null });
    loadStateMedianForecast(stateId, asOf).then(value => {
      if (!cancelled) setRead({ stateId, asOf, loading: false, value, error: null });
    }).catch(error => {
      if (!cancelled) setRead({ stateId, asOf, loading: false, value: null, error: error.message || 'State median service unavailable.' });
    });
    return () => { cancelled = true; };
  }, [stateId, asOf, retry]);
  const current = read?.stateId === stateId && read?.asOf === asOf ? read : null;
  return <StateMedianForecastView value={current?.value} loading={!current || current.loading} error={current?.error} onRetry={() => setRetry(value => value + 1)} />;
}
