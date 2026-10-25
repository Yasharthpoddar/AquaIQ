"""District navigation must survive unavailable scoring and training assets."""
from api.app import create_app
from api.routes import district
from models.district_registry import get_registry


def test_catalog_lists_entire_registry_without_database_or_inference(monkeypatch):
    from db import connection
    def forbidden(*args, **kwargs):
        raise AssertionError('Registry navigation must not query scores or run inference.')
    monkeypatch.setattr(connection, 'get_connection', forbidden)
    monkeypatch.setattr(district, 'compute_crisis_score', forbidden)
    response=create_app({'TESTING':True}).test_client().get('/api/districts')
    assert response.status_code==200
    data=response.json;registered=get_registry()
    assert data['total']==len(registered)==len(data['districts'])
    assert {row['district_id'] for row in data['districts']}=={row['district_id'] for row in registered}
    assert all(row['name'] and row['state'] and row['state_id']==row['district_id'][:2] for row in data['districts'])
    assert all('score' not in row and 'tier' not in row for row in data['districts'])


def test_broken_registry_is_a_service_error_not_an_empty_success(monkeypatch):
    def invalid(): raise ValueError('Conflicting registry metadata')
    monkeypatch.setattr(district,'get_registry',invalid)
    response=create_app({'TESTING':True}).test_client().get('/api/districts')
    assert response.status_code==503 and response.json['status']=='unavailable'
