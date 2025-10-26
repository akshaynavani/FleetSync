VAN = {"id": "VAN-001", "model": "Transit", "depot": "north", "capacity_kg": 1500}


def register(client, **overrides):
    body = {**VAN, **overrides}
    return client.post("/vehicles", json=body)


def test_health_and_ready(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").status_code == 200


def test_register_and_fetch(client):
    resp = register(client)
    assert resp.status_code == 201
    assert resp.json()["status"] == "idle"
    got = client.get("/vehicles/VAN-001").json()
    assert got["model"] == "Transit"
    assert got["capacity_kg"] == 1500


def test_duplicate_registration_conflicts(client):
    register(client)
    assert register(client).status_code == 409


def test_invalid_id_rejected(client):
    assert register(client, id="bad id!").status_code == 422


def test_unknown_vehicle_404(client):
    assert client.get("/vehicles/nope").status_code == 404
    assert client.delete("/vehicles/nope").status_code == 404


def test_list_filters_by_depot_and_status(client):
    register(client)
    register(client, id="VAN-002", depot="south")
    register(client, id="VAN-003")
    client.patch("/vehicles/VAN-003/status", json={"status": "active"})

    north = client.get("/vehicles", params={"depot": "north"}).json()
    assert [v["id"] for v in north] == ["VAN-001", "VAN-003"]
    active = client.get("/vehicles", params={"status": "active"}).json()
    assert [v["id"] for v in active] == ["VAN-003"]


def test_status_transitions(client):
    register(client)
    assert client.patch("/vehicles/VAN-001/status", json={"status": "maintenance"}).status_code == 200
    assert client.patch("/vehicles/VAN-001/status", json={"status": "retired"}).status_code == 200
    # Retired is terminal.
    resp = client.patch("/vehicles/VAN-001/status", json={"status": "active"})
    assert resp.status_code == 409


def test_stats(client):
    register(client)
    register(client, id="VAN-002")
    client.patch("/vehicles/VAN-002/status", json={"status": "active"})
    stats = client.get("/vehicles/stats").json()
    assert stats["total"] == 2
    assert stats["by_status"]["active"] == 1
    assert stats["by_status"]["idle"] == 1


def test_delete_removes_from_indexes(client, store):
    register(client)
    assert client.delete("/vehicles/VAN-001").status_code == 204
    assert client.get("/vehicles").json() == []
    assert not store.r.smembers("depot:north")


def test_metrics_exposed(client):
    client.get("/healthz")
    body = client.get("/metrics").text
    assert "fleetsync_http_requests_total" in body
