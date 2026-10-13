"""Live DB tests are explicit; ordinary tests never probe a user's database."""
import pytest

def pytest_addoption(parser):
    parser.addoption('--integration',action='store_true',default=False,help='Run explicitly marked PostgreSQL integration tests.')

def pytest_collection_modifyitems(config,items):
    if config.getoption('--integration'):
        return
    marker=pytest.mark.skip(reason='Use --integration with an isolated PostgreSQL test database.')
    for item in items:
        if 'requires_db' in item.keywords:
            item.add_marker(marker)
