"""Recheck saved state benchmark predictions without changing the benchmark.

Reads existing cases/panels, runs the unchanged model at their historical origins,
and writes only a new equivalence record. No fitting, selection or database use.
"""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=Path('reports/xgboost_only_states_20261025'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    from models import state_forecast as state
    import db.connection
    cases = pd.read_csv(args.report/'cases.csv')
    checked = []
    with patch.object(db.connection, 'get_connection', side_effect=AssertionError('No database access')):
        for row in cases.itertuples():
            result = state.forecast_state_twelve_months(row.state_id, row.as_of)
            assert result['status'] == 'forecast'
            predicted = result['forecast'][int(row.horizon)-1]
            assert predicted['target_date'] == row.target_month
            assert predicted['predicted_gwl'] == row.xgboost
            assert result['estimated_current_gwl_m_bgl'] == row.estimated_anchor
            assert result['panel_id'] == row.panel_id
            assert result['contributing_districts_count'] == row.n_districts
            assert result['district_coverage_pct'] == row.coverage_pct
            checked.append(dict(state_id=row.state_id, as_of=row.as_of, horizon=int(row.horizon),
                                target_month=row.target_month, predicted_gwl=predicted['predicted_gwl']))
            print(f'Exact match {row.state_id} {row.as_of} M+{row.horizon}', flush=True)
    output = {'status':'exact_saved_prediction_match', 'case_count':len(checked),
              'state_count':int(cases.state_id.nunique()), 'as_of_dates':sorted(cases.as_of.unique().tolist()),
              'comparison':'Exact target date, XGBoost prediction, estimated anchor, panel hash/count/coverage.',
              'evaluation_rerun':False, 'cases':checked,
              'preserved_report_sha256':{name:hashlib.sha256((args.report/name).read_bytes()).hexdigest()
                                        for name in ('cases.csv','evaluation.json','panels.json')}}
    with (args.output/'equivalence.json').open('x',encoding='utf-8') as stream:
        json.dump(output,stream,indent=2,allow_nan=False)


if __name__ == '__main__':
    main()
