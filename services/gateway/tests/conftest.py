import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "common"))

from app.main import app  # noqa: E402
from app.upstream import Upstreams  # noqa: E402


class FakeBackends:
    """In-memory stand-ins for the registry and telemetry services."""

    def __init__(self) -> None:
        self.vehicles: dict[str, dict] = {}
        self.telemetry: dict[str, list[dict]] = {}
        self.down: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        host, path, method = request.url.host, request.url.path, request.method
        if host in self.down:
            raise httpx.ConnectError("connection refused", request=request)
        if path == "/healthz":
            return httpx.Response(200, json={"status": "ok"})
        if host == "registry":
            return self._registry(method, path, request)
        return self._telemetry(method, path, request)

    def _registry(self, method, path, request):
        parts = path.strip("/").split("/")
        if path == "/vehicles" and method == "POST":
            body = json.loads(request.content)
            if body["id"] in self.vehicles:
                return httpx.Response(409, json={"detail": "exists"})
            self.vehicles[body["id"]] = {**body, "status": "idle"}
            return httpx.Response(201, json=self.vehicles[body["id"]])
        if path == "/vehicles":
            return httpx.Response(200, json=list(self.vehicles.values()))
        if path == "/vehicles/stats":
            return httpx.Response(200, json={"total": len(self.vehicles), "by_status": {}})
        vid = parts[1]
        if vid not in self.vehicles:
            return httpx.Response(404, json={"detail": "not found"})
        if method == "PATCH":
            self.vehicles[vid]["status"] = json.loads(request.content)["status"]
            return httpx.Response(200, json=self.vehicles[vid])
        if method == "DELETE":
            del self.vehicles[vid]
            return httpx.Response(204)
        return httpx.Response(200, json=self.vehicles[vid])

    def _telemetry(self, method, path, request):
        if path == "/telemetry/latest":
            ids = request.url.params["ids"].split(",")
            return httpx.Response(200, json={i: (self.telemetry.get(i) or [None])[-1] for i in ids})
        if path == "/routes/optimize":
            stops = json.loads(request.content)["stops"]
            return httpx.Response(200, json={"ordered_stop_ids": [s["id"] for s in stops]})
        vid = path.split("/")[2]
        if method == "POST":
            self.telemetry.setdefault(vid, []).append({**json.loads(request.content), "vehicle_id": vid})
            return httpx.Response(202, json={"accepted": True})
        return httpx.Response(200, json=self.telemetry.get(vid, []))


@pytest.fixture()
def backends():
    return FakeBackends()


@pytest.fixture()
def client(backends):
    app.state.upstreams = Upstreams("http://registry", "http://telemetry", transport=httpx.MockTransport(backends))
    with TestClient(app) as c:
        yield c
    app.state.upstreams = None
