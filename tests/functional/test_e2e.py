import uuid

READING = {"lat": 40.71, "lon": -74.0, "speed_kph": 42, "fuel_pct": 64, "engine_temp_c": 88}


def test_gateway_ready_with_all_upstreams(api):
    body = api.get("/readyz").json()
    assert body["status"] == "ready"
    assert body["upstreams"] == {"registry": "ok", "telemetry": "ok"}


def test_vehicle_lifecycle(api, vehicle):
    vid = vehicle["id"]
    assert vehicle["status"] == "idle"

    fetched = api.get(f"/api/vehicles/{vid}").json()
    assert fetched["capacity_kg"] == 900

    assert api.patch(f"/api/vehicles/{vid}/status", json={"status": "active"}).json()["status"] == "active"
    listed = api.get("/api/vehicles", params={"depot": "e2e", "status": "active"}).json()
    assert vid in [v["id"] for v in listed]


def test_duplicate_registration_is_rejected(api, vehicle):
    resp = api.post("/api/vehicles", json={"id": vehicle["id"], "model": "x", "depot": "e2e"})
    assert resp.status_code == 409


def test_validation_errors_surface_through_gateway(api):
    assert api.post("/api/vehicles", json={"id": "bad id", "model": "x", "depot": "d"}).status_code == 422
    vid = f"e2e-{uuid.uuid4().hex[:10]}"
    api.post("/api/vehicles", json={"id": vid, "model": "x", "depot": "e2e"})
    try:
        assert api.post(f"/api/vehicles/{vid}/telemetry", json={**READING, "lat": 123}).status_code == 422
    finally:
        api.delete(f"/api/vehicles/{vid}")


def test_telemetry_for_unknown_vehicle_is_rejected(api):
    assert api.post("/api/vehicles/does-not-exist/telemetry", json=READING).status_code == 404


def test_telemetry_ingest_history_and_summary(api, vehicle):
    vid = vehicle["id"]
    for i in range(5):
        resp = api.post(f"/api/vehicles/{vid}/telemetry",
                        json={**READING, "lat": 40.70 + i * 0.01, "fuel_pct": 60 - i})
        assert resp.status_code == 202

    history = api.get(f"/api/vehicles/{vid}/telemetry", params={"limit": 10}).json()
    assert len(history) == 5

    summary = api.get(f"/api/vehicles/{vid}/summary").json()
    assert summary["readings"] == 5
    assert summary["min_fuel_pct"] == 56
    assert 4.0 < summary["distance_km"] < 5.0  # 0.04 deg latitude ~ 4.45 km


def test_alerts_raised_for_hot_engine_and_low_fuel(api, vehicle):
    vid = vehicle["id"]
    api.post(f"/api/vehicles/{vid}/telemetry", json={**READING, "fuel_pct": 4, "engine_temp_c": 125})
    alerts = api.get(f"/api/vehicles/{vid}/summary").json()["alerts"]
    assert len(alerts) == 2


def test_retired_vehicle_cannot_report(api, vehicle):
    vid = vehicle["id"]
    assert api.patch(f"/api/vehicles/{vid}/status", json={"status": "retired"}).status_code == 200
    assert api.post(f"/api/vehicles/{vid}/telemetry", json=READING).status_code == 409
    assert api.patch(f"/api/vehicles/{vid}/status", json={"status": "active"}).status_code == 409


def test_fleet_overview_includes_latest_telemetry(api, vehicle):
    vid = vehicle["id"]
    api.post(f"/api/vehicles/{vid}/telemetry", json=READING)
    overview = api.get("/api/fleet/overview").json()
    entry = next(v for v in overview["vehicles"] if v["id"] == vid)
    assert entry["latest_telemetry"]["speed_kph"] == READING["speed_kph"]
    assert overview["stats"]["total"] >= 1


def test_route_optimisation_improves_on_input_order(api):
    # Points around a circle, given in a deliberately scrambled order.
    import math
    order = [0, 6, 2, 9, 4, 11, 1, 7, 3, 10, 5, 8]
    stops = [{"id": f"s{k}", "lat": 40.7 + 0.1 * math.sin(k * math.pi / 6),
              "lon": -74.0 + 0.1 * math.cos(k * math.pi / 6)} for k in order]
    resp = api.post("/api/routes/optimize", json={"depot": {"lat": 40.7, "lon": -74.0}, "stops": stops})
    assert resp.status_code == 200
    body = resp.json()
    assert sorted(body["ordered_stop_ids"]) == sorted(s["id"] for s in stops)
    assert body["improvement_pct"] > 20
