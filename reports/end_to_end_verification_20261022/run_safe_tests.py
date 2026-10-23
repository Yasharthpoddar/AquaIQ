"""Run reviewed synthetic/metadata tests with training and live DB forbidden."""
from contextlib import ExitStack
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

def forbidden(*args,**kwargs):
    raise RuntimeError('This audit test run forbids DB connections and all fitting')

if __name__=='__main__':
    import pytest
    with ExitStack() as guards:
        for target in ('psycopg2.connect','xgboost.XGBRegressor.fit','xgboost.XGBRegressor.load_model',
                       'sklearn.ensemble.HistGradientBoostingRegressor.fit','sklearn.ensemble.RandomForestRegressor.fit',
                       'sklearn.linear_model.LinearRegression.fit','sklearn.linear_model.Ridge.fit',
                       'sklearn.neural_network.MLPRegressor.fit','models.monthly_projection.fit_projection'):
            guards.enter_context(patch(target,forbidden))
        sys.exit(pytest.main(sys.argv[1:]))
