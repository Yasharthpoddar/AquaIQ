"""Audit-only localhost server: existing source, DB reads, no saved ML fitting.

The existing monthly scenario and legacy monthly route calculate a transient
NumPy seasonal/trend fit during normal serving. This is explicitly recorded as
existing endpoint behavior, not a new research fit or saved model artifact.
"""
from contextlib import ExitStack
from pathlib import Path
import sys
from unittest.mock import patch

import psycopg2
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
load_dotenv(ROOT/'.env')
original_connect=psycopg2.connect


def readonly_connection(*args,**kwargs):
    kwargs['options']=(kwargs.get('options','')+' -c default_transaction_read_only=on').strip()
    connection=original_connect(*args,**kwargs)
    connection.set_session(readonly=True)
    return connection


def no_fit(*args,**kwargs):
    raise RuntimeError('Active ML fitting is prohibited in this audit')


if __name__=='__main__':
    with ExitStack() as guards:
        guards.enter_context(patch('psycopg2.connect',readonly_connection))
        for target in ('xgboost.XGBRegressor.fit','sklearn.ensemble.HistGradientBoostingRegressor.fit',
                       'sklearn.ensemble.RandomForestRegressor.fit','sklearn.linear_model.LinearRegression.fit',
                       'sklearn.linear_model.Ridge.fit','sklearn.neural_network.MLPRegressor.fit'):
            guards.enter_context(patch(target,no_fit))
        from api.app import create_app
        app=create_app({'AQUAIQ_CORS_ORIGINS':'http://127.0.0.1:5183'})
        app.run(host='127.0.0.1',port=5053,debug=False,use_reloader=False)
