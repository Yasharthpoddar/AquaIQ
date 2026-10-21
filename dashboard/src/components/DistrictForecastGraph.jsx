import { useSearchParams } from 'react-router-dom';
import HistoricalGraph from './ForecastGraphPanel';
import ExperimentalScenario from './ExperimentalScenario';
import { forecastView } from './experimentalScenarioContract';

export default function DistrictForecastGraph({ districtId }) {
  const [params, setParams] = useSearchParams();
  const view = forecastView(params);
  const chooseView = next => setParams(previous => {
    const updated = new URLSearchParams(previous);
    updated.set('view', next);
    if (next === 'scenario') updated.delete('origin_month');
    return updated;
  });
  return <>
    <div role="group" aria-label="Groundwater graph view" style={{marginTop:'1.5rem'}}>
      <button type="button" aria-pressed={view === 'scenario'} onClick={() => chooseView('scenario')}>Next 12 months from today (experimental)</button>{' '}
      <button type="button" aria-pressed={view === 'historical'} onClick={() => chooseView('historical')}>Historical M+12 research</button>
    </div>
    {view === 'scenario' ? <ExperimentalScenario key={districtId} districtId={districtId} /> : <HistoricalGraph key={districtId} districtId={districtId} />}
  </>;
}
