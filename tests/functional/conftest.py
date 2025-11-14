"""End-to-end functional tests against a running FleetSync gateway.

Point FLEETSYNC_URL at the gateway, e.g. after
    kubectl -n fleetsync-dev port-forward svc/gateway 8080:8080
or `docker compose up`. Tests are skipped when the gateway is unreachable.
"""

import os
import uuid

import httpx
import pytest

BASE_URL = os.getenv("FLEETSYNC_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def api():
    client = httpx.Client(base_url=BASE_URL, timeout=30)
    try:
        client.get("/healthz").raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(f"FleetSync gateway not reachable at {BASE_URL}: {exc}")
    yield client
    client.close()


@pytest.fixture()
def vehicle(api):
    """Register a throwaway vehicle and clean it up afterwards."""
    vid = f"e2e-{uuid.uuid4().hex[:10]}"
    resp = api.post("/api/vehicles", json={"id": vid, "model": "E2E Van", "depot": "e2e", "capacity_kg": 900})
    assert resp.status_code == 201, resp.text
    yield resp.json()
    api.delete(f"/api/vehicles/{vid}")
