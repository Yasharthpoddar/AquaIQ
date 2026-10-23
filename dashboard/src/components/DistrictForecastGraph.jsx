import ExperimentalScenario from './ExperimentalScenario';

// The main district workflow now has one clear graph: the next twelve calendar months.
// The older direct M+12 research endpoint remains available for automated/research tooling,
// but is no longer presented as an alternate end-user graph.
export default function DistrictForecastGraph({ districtId }) {
  return <ExperimentalScenario key={districtId} districtId={districtId} />;
}
