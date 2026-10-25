"""Local output isolation and complete score publication regressions."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock
import uuid
import pandas as pd
import pytest
from psycopg2 import sql
from db import scoring_storage
from db.connection import get_connection
from models import score_all


@pytest.mark.parametrize('name',['public','aquaiq_test_','aquaiq_test_bad;public','Other_schema'])
def test_only_explicit_test_namespaces_are_accepted(name):
    with pytest.raises(ValueError):scoring_storage.validate_test_schema(name)


def test_missing_private_tables_never_fall_back_to_public_outputs(monkeypatch):
    conn=MagicMock();cursor=conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value=(0,)
    monkeypatch.setattr(scoring_storage,'source_connection',lambda:conn)
    monkeypatch.setenv('AQUAIQ_SCORING_SCHEMA','aquaiq_test_missing')
    with pytest.raises(RuntimeError,match='unavailable'):scoring_storage.get_scoring_connection()
    conn.close.assert_called_once()
    assert cursor.execute.call_count==1  # no SET search_path or write attempted


def fixture_record(district='HR-Kaithal'):
    return dict(district_id=district,crisis_score=10,tier='Safe',components={},
        estimate_type='district_level',last_observed_date='2025-01-01',model_version='fixture',
        forecast_origin='2025-01-01',forecast=[{'month':'2025-07','predicted_gwl':5.}])


def mock_inputs(monkeypatch,records):
    monkeypatch.setattr(score_all,'read_frame',lambda *a:pd.DataFrame({'district_id':[r['district_id'] for r in records]}))
    monkeypatch.setattr(score_all,'feature_generation',lambda:'fixture-generation')
    monkeypatch.setattr(score_all,'scoring_signature',lambda:'fixture-signature')
    monkeypatch.setattr(score_all,'_load_bundle',lambda:(None,{'version':'fixture','model_sha256':'fixture-sha'}))
    by_id={r['district_id']:r for r in records}
    monkeypatch.setattr(score_all,'compute_crisis_score',lambda did,*a:deepcopy(by_id[did]))


@pytest.mark.parametrize('value,tier',[(float('nan'),'Safe'),(101,'Crisis'),(10.5,'Safe'),(10,'Crisis'),(None,'Safe')])
def test_invalid_or_mislabelled_scores_cannot_publish(monkeypatch,value,tier):
    record=fixture_record();record.update(crisis_score=value,tier=tier)
    mock_inputs(monkeypatch,[record]);conn=MagicMock()
    with pytest.raises(ValueError):score_all.score_all_districts('2025-12-31',connection=conn)
    conn.cursor.assert_not_called()


def test_changed_inputs_do_not_publish(monkeypatch):
    mock_inputs(monkeypatch,[fixture_record()]);conn=MagicMock()
    generations=iter(['fixture-generation','changed-generation'])
    monkeypatch.setattr(score_all,'feature_generation',lambda:next(generations))
    with pytest.raises(RuntimeError,match='changed'):score_all.score_all_districts('2025-12-31',connection=conn)
    conn.cursor.assert_not_called()


@pytest.fixture
def isolated_score_db():
    schema='aquaiq_test_scores_'+uuid.uuid4().hex
    conn=scoring_storage.initialize_test_schema(schema)
    try:yield conn,schema
    finally:
        conn.rollback()
        with conn:
            with conn.cursor() as cur:cur.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        conn.close()


@pytest.mark.requires_db
def test_migration_output_sequences_and_source_tables_are_isolated(isolated_score_db):
    conn,schema=isolated_score_db
    second=scoring_storage.initialize_test_schema(schema);second.close()
    with conn.cursor() as cur:
        cur.execute('SELECT table_name FROM information_schema.tables WHERE table_schema=%s',(schema,))
        names={r[0] for r in cur.fetchall()}
        assert names=={'scoring_runs','crisis_scores','predictions','schema_migrations'}
        for table in ['crisis_scores','predictions']:
            cur.execute('SELECT pg_get_serial_sequence(%s,%s)',(schema+'.'+table,'id'))
            assert cur.fetchone()[0].startswith(schema+'.')
        cur.execute('SELECT COUNT(*) FROM districts')  # resolves existing read-only public source
        assert cur.fetchone()[0]>0


@pytest.mark.requires_db
def test_complete_publication_api_reads_and_rollback_use_private_tables(isolated_score_db,monkeypatch):
    from api.app import create_app
    from api.routes import scores
    conn,schema=isolated_score_db
    source=get_connection()
    try:
        with source.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM public.scoring_runs');before=cur.fetchone()[0]
    finally:source.close()
    absent=fixture_record('AN-Nicobars');absent.update(crisis_score=None,tier=None,forecast=[],model_version=None)
    mock_inputs(monkeypatch,[fixture_record(),absent])
    assert score_all.score_all_districts('2025-12-31',connection=conn)==2
    monkeypatch.setenv('AQUAIQ_SCORING_SCHEMA',schema)
    monkeypatch.setattr(scores,'_load_bundle',score_all._load_bundle)
    monkeypatch.setattr(scores,'feature_generation',score_all.feature_generation)
    monkeypatch.setattr(scores,'scoring_signature',score_all.scoring_signature)
    client=create_app({'TESTING':True}).test_client()
    data=client.get('/api/scores').json
    assert data['status']=='success' and data['total']==2 and data['tier_counts']['Unknown']==1
    alerts=client.get('/api/alerts?limit=1000').json
    assert alerts['count']==2 and alerts['alerts'][-1]['score'] is None
    assert client.get('/api/alerts?tier=Safe').json['count']==1
    # Fail after the run header is inserted but before score rows can commit.
    with conn:
        with conn.cursor() as cur:
            cur.execute("""CREATE FUNCTION reject_score() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Injected scoring write failure'; END $$""")
            cur.execute('CREATE TRIGGER reject_score BEFORE INSERT ON crisis_scores FOR EACH ROW EXECUTE FUNCTION reject_score()')
    with pytest.raises(Exception,match='Injected'):
        score_all.score_all_districts('2025-12-30',connection=conn)
    data=client.get('/api/scores').json
    assert data['status']=='success' and data['total']==2
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM scoring_runs');assert cur.fetchone()[0]==1
        cur.execute('SELECT COUNT(*) FROM public.scoring_runs');assert cur.fetchone()[0]==before
