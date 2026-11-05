import pytest

import db


@pytest.fixture
def conn():
    conn = db.connect(":memory:")
    yield conn
    conn.close()
