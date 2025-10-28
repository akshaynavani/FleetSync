VAN = {"id": "VAN-001", "model": "Transit", "depot": "north"}
READING = {"lat": 1, "lon": 2, "speed_kph": 50, "fuel_pct": 70, "engine_temp_c": 90}


def test_ready_when_upstreams_healthy(client):
    assert client.get("/readyz").json()["status"] == "ready"


def test_ready_degraded_when_upstream_down(client, backends):
    backends.down.add("telemetry")
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["upstreams"]["registry"] == "ok"


def test_vehicle_crud_is_proxied(client):
    assert client.post("/api/vehicles", json=VAN).status_code == 201
    assert client.post("/api/vehicles", json=VAN).status_code == 409
    assert client.get("/api/vehicles/VAN-001").json()["model"] == "Transit"
    assert client.patch("/api/vehicles/VAN-001/status", json={"status": "active"}).json()["status"] == "active"
    assert client.delete("/api/vehicles/VAN-001").status_code == 204
    assert client.get("/api/vehicles/VAN-001").status_code == 404


def test_telemetry_requires_registered_vehicle(client):
    resp = client.post("/api/vehicles/GHOST/telemetry", json=READING)
    assert resp.status_code == 404


def test_telemetry_rejected_for_retired_vehicle(client, backends):
    client.post("/api/vehicles", json=VAN)
    backends.vehicles["VAN-001"]["status"] = "retired"
    assert client.post("/api/vehicles/VAN-001/telemetry", json=READING).status_code == 409


def test_telemetry_forwarded(client, backends):
    client.post("/api/vehicles", json=VAN)
    assert client.post("/api/vehicles/VAN-001/telemetry", json=READING).status_code == 202
    assert backends.telemetry["VAN-001"][0]["speed_kph"] == 50


def test_fleet_overview_merges_latest_telemetry(client):
    client.post("/api/vehicles", json=VAN)
    client.post("/api/vehicles", json={**VAN, "id": "VAN-002"})
    client.post("/api/vehicles/VAN-001/telemetry", json=READING)
    overview = client.get("/api/fleet/overview").json()
    assert overview["reporting_vehicles"] == 1
    by_id = {v["id"]: v for v in overview["vehicles"]}
    assert by_id["VAN-001"]["latest_telemetry"]["fuel_pct"] == 70
    assert by_id["VAN-002"]["latest_telemetry"] is None


def test_upstream_down_maps_to_502(client, backends):
    backends.down.add("registry")
    assert client.get("/api/vehicles").status_code == 502


def test_route_optimize_proxied(client):
    body = {"depot": {"lat": 0, "lon": 0}, "stops": [{"id": "a", "lat": 1, "lon": 1}]}
    assert client.post("/api/routes/optimize", json=body).json()["ordered_stop_ids"] == ["a"]
