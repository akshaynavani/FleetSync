import sys
from pathlib import Path

import fakeredis
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "common"))

from app.main import app, get_store  # noqa: E402
from app.store import TelemetryStore  # noqa: E402


@pytest.fixture()
def store():
    return TelemetryStore(fakeredis.FakeRedis(decode_responses=True), history_limit=5)


@pytest.fixture()
def client(store):
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()
