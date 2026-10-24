import ExperimentalScenario from './ExperimentalScenario';

export default function DistrictForecastGraph({ districtId }) {
  // Legacy origin_month/view queries do not change the district's product.
  // The direct M+12 APIs and research components remain intact for audit use.
  return <ExperimentalScenario key={districtId} districtId={districtId} />;
}
