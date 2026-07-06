"""
Fixtures specific to integration tests
"""
import pytest

from etl.config import load_config
from etl.db import get_connection


@pytest.fixture(scope="session")
def db_config():
    return load_config()


@pytest.fixture
def db_conn(db_config):
    with get_connection(db_config) as conn:
        yield conn
