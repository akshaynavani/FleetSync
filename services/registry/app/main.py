"""FleetSync registry service: source of truth for vehicles in the fleet."""

from __future__ import annotations

import os
import socket

import redis
from fastapi import Depends, FastAPI, HTTPException, Query, Response, status

from fleetsync_common import configure_logging, env_int, env_str, install_metrics

from .models import StatusUpdate, Vehicle, VehicleCreate, VehicleStatus
from .store import InvalidTransition, VehicleExists, VehicleNotFound, VehicleStore

SERVICE = "registry"
log = configure_logging(SERVICE, env_str("LOG_LEVEL", "INFO"))

app = FastAPI(title="FleetSync Registry", version="1.0.0")
install_metrics(app, SERVICE)

_store: VehicleStore | None = None


def get_store() -> VehicleStore:
    global _store
    if _store is None:
        client = redis.Redis(
            host=env_str("REDIS_HOST", "localhost"),
            port=env_int("REDIS_PORT", 6379),
            password=os.getenv("REDIS_PASSWORD") or None,
            db=env_int("REDIS_DB", 0),
            socket_timeout=2,
            socket_connect_timeout=2,
            decode_responses=True,
        )
        _store = VehicleStore(client)
    return _store


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok", "service": SERVICE, "pod": socket.gethostname()}


@app.get("/readyz", include_in_schema=False)
def readyz(response: Response, store: VehicleStore = Depends(get_store)) -> dict:
    try:
        store.ping()
    except redis.RedisError as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "reason": str(exc)}
    return {"status": "ready"}


@app.post("/vehicles", response_model=Vehicle, status_code=status.HTTP_201_CREATED)
def create_vehicle(body: VehicleCreate, store: VehicleStore = Depends(get_store)) -> Vehicle:
    try:
        vehicle = store.create(body)
    except VehicleExists:
        raise HTTPException(status.HTTP_409_CONFLICT, f"vehicle {body.id} already registered")
    log.info("vehicle registered", extra={"extra_fields": {"vehicle_id": body.id, "depot": body.depot}})
    return vehicle


@app.get("/vehicles", response_model=list[Vehicle])
def list_vehicles(
    depot: str | None = Query(default=None),
    status_filter: VehicleStatus | None = Query(default=None, alias="status"),
    store: VehicleStore = Depends(get_store),
) -> list[Vehicle]:
    return store.list(depot=depot, status=status_filter)


@app.get("/vehicles/stats")
def vehicle_stats(store: VehicleStore = Depends(get_store)) -> dict:
    counts = store.count_by_status()
    return {"total": sum(counts.values()), "by_status": counts}


@app.get("/vehicles/{vehicle_id}", response_model=Vehicle)
def get_vehicle(vehicle_id: str, store: VehicleStore = Depends(get_store)) -> Vehicle:
    try:
        return store.get(vehicle_id)
    except VehicleNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"vehicle {vehicle_id} not found")


@app.patch("/vehicles/{vehicle_id}/status", response_model=Vehicle)
def update_status(vehicle_id: str, body: StatusUpdate, store: VehicleStore = Depends(get_store)) -> Vehicle:
    try:
        vehicle = store.set_status(vehicle_id, body.status)
    except VehicleNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"vehicle {vehicle_id} not found")
    except InvalidTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    log.info("vehicle status changed", extra={"extra_fields": {"vehicle_id": vehicle_id, "status": body.status.value}})
    return vehicle


@app.delete("/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(vehicle_id: str, store: VehicleStore = Depends(get_store)) -> Response:
    try:
        store.delete(vehicle_id)
    except VehicleNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"vehicle {vehicle_id} not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
