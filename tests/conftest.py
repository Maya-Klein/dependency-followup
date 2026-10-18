import pytest

from app.storage.db import get_engine


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def engine(db_url):
    return get_engine(db_url)
