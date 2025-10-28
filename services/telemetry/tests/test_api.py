READING = {"lat": 40.0, "lon": -73.0, "speed_kph": 60, "fuel_pct": 80, "engine_temp_c": 90}


def ingest(client, vid="VAN-001", **overrides):
    return client.post(f"/telemetry/{vid}", json={**READING, **overrides})


def test_ingest_and_latest(client):
    assert ingest(client).status_code == 202
    assert ingest(client, speed_kph=75).status_code == 202
    latest = client.get("/telemetry/VAN-001/latest").json()
    assert latest["speed_kph"] == 75
    assert latest["vehicle_id"] == "VAN-001"


def test_history_is_capped(client):
    for i in range(8):
        ingest(client, speed_kph=i)
    history = client.get("/telemetry/VAN-001", params={"limit": 50}).json()
    assert len(history) == 5
    assert history[0]["speed_kph"] == 7  # most recent first


def test_rejects_out_of_range(client):
    assert ingest(client, lat=95).status_code == 422
    assert ingest(client, fuel_pct=-1).status_code == 422


def test_summary_and_alerts(client):
    ingest(client, lat=40.0, recorded_at="2026-01-01T00:00:00Z")
    ingest(client, lat=40.1, fuel_pct=5, engine_temp_c=120, recorded_at="2026-01-01T00:05:00Z")
    s = client.get("/telemetry/VAN-001/summary").json()
    assert s["readings"] == 2
    assert 11 < s["distance_km"] < 11.3  # 0.1 deg latitude ~ 11.1 km
    assert s["min_fuel_pct"] == 5
    assert len(s["alerts"]) == 2


def test_summary_404_without_data(client):
    assert client.get("/telemetry/ghost/summary").status_code == 404
    assert client.get("/telemetry/ghost/latest").status_code == 404


def test_latest_many(client):
    ingest(client, "A")
    resp = client.get("/telemetry/latest", params={"ids": "A,B"}).json()
    assert resp["A"]["vehicle_id"] == "A"
    assert resp["B"] is None


def test_stats_counts_ingest(client):
    ingest(client)
    ingest(client)
    assert client.get("/telemetry/stats").json()["ingested_total"] == 2


def test_route_optimize(client):
    body = {
        "depot": {"lat": 0, "lon": 0},
        "stops": [{"id": f"s{i}", "lat": 0, "lon": x / 10} for i, x in enumerate([3, 1, 2])],
    }
    resp = client.post("/routes/optimize", json=body).json()
    assert sorted(resp["ordered_stop_ids"]) == ["s0", "s1", "s2"]
    assert resp["distance_km"] <= resp["baseline_km"]
