"""FleetSync telemetry service: ingest vehicle readings and plan delivery routes."""

from __future__ import annotations

import os
import socket
import time
from datetime import datetime, timezone

import redis
from fastapi import Depends, FastAPI, HTTPException, Query, Response, status

from fleetsync_common import configure_logging, env_int, env_str, install_metrics

from . import geo
from .models import Reading, RouteRequest, RouteResponse, StoredReading, Summary
from .store import TelemetryStore

SERVICE = "telemetry"
log = configure_logging(SERVICE, env_str("LOG_LEVEL", "INFO"))

ENGINE_TEMP_ALERT_C = float(env_str("ENGINE_TEMP_ALERT_C", "110"))
LOW_FUEL_ALERT_PCT = float(env_str("LOW_FUEL_ALERT_PCT", "10"))

app = FastAPI(title="FleetSync Telemetry", version="1.0.0")
install_metrics(app, SERVICE)

_store: TelemetryStore | None = None


def get_store() -> TelemetryStore:
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
        _store = TelemetryStore(client, history_limit=env_int("TELEMETRY_HISTORY_LIMIT", 500))
    return _store


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok", "service": SERVICE, "pod": socket.gethostname()}


@app.get("/readyz", include_in_schema=False)
def readyz(response: Response, store: TelemetryStore = Depends(get_store)) -> dict:
    try:
        store.ping()
    except redis.RedisError as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "reason": str(exc)}
    return {"status": "ready"}


@app.post("/telemetry/{vehicle_id}", status_code=status.HTTP_202_ACCEPTED)
def ingest(vehicle_id: str, reading: Reading, store: TelemetryStore = Depends(get_store)) -> dict:
    stored = StoredReading(
        **reading.model_dump(exclude={"recorded_at"}),
        vehicle_id=vehicle_id,
        recorded_at=reading.recorded_at or datetime.now(timezone.utc),
    )
    store.append(stored)
    return {"accepted": True, "vehicle_id": vehicle_id, "recorded_at": stored.recorded_at}


@app.get("/telemetry/stats")
def stats(store: TelemetryStore = Depends(get_store)) -> dict:
    return {"ingested_total": store.ingested_total(), "pod": socket.gethostname()}


@app.get("/telemetry/latest")
def latest_many(ids: str = Query(..., description="Comma separated vehicle ids"),
                store: TelemetryStore = Depends(get_store)) -> dict:
    vehicle_ids = [v for v in (s.strip() for s in ids.split(",")) if v]
    return {vid: r.model_dump(mode="json") if r else None for vid, r in store.latest_many(vehicle_ids).items()}


@app.get("/telemetry/{vehicle_id}", response_model=list[StoredReading])
def history(vehicle_id: str, limit: int = Query(default=50, ge=1, le=500),
            store: TelemetryStore = Depends(get_store)) -> list[StoredReading]:
    return store.history(vehicle_id, limit)


@app.get("/telemetry/{vehicle_id}/latest", response_model=StoredReading)
def latest(vehicle_id: str, store: TelemetryStore = Depends(get_store)) -> StoredReading:
    reading = store.latest(vehicle_id)
    if reading is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no telemetry for {vehicle_id}")
    return reading


@app.get("/telemetry/{vehicle_id}/summary", response_model=Summary)
def summary(vehicle_id: str, limit: int = Query(default=500, ge=1, le=500),
            store: TelemetryStore = Depends(get_store)) -> Summary:
    readings = store.history(vehicle_id, limit)
    if not readings:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no telemetry for {vehicle_id}")
    chronological = sorted(readings, key=lambda r: r.recorded_at)
    latest_reading = chronological[-1]
    alerts: list[str] = []
    if latest_reading.engine_temp_c >= ENGINE_TEMP_ALERT_C:
        alerts.append(f"engine temperature {latest_reading.engine_temp_c:.1f}C above {ENGINE_TEMP_ALERT_C:.0f}C")
    if latest_reading.fuel_pct <= LOW_FUEL_ALERT_PCT:
        alerts.append(f"fuel at {latest_reading.fuel_pct:.1f}% (threshold {LOW_FUEL_ALERT_PCT:.0f}%)")
    return Summary(
        vehicle_id=vehicle_id,
        readings=len(readings),
        avg_speed_kph=round(sum(r.speed_kph for r in readings) / len(readings), 2),
        max_engine_temp_c=max(r.engine_temp_c for r in readings),
        min_fuel_pct=min(r.fuel_pct for r in readings),
        distance_km=round(geo.path_length_km([(r.lat, r.lon) for r in chronological]), 3),
        alerts=alerts,
    )


@app.post("/routes/optimize", response_model=RouteResponse)
def optimise(body: RouteRequest) -> RouteResponse:
    start = time.perf_counter()
    result = geo.optimise_route(
        (body.depot.lat, body.depot.lon),
        [(s.lat, s.lon) for s in body.stops],
        max_passes=body.max_passes,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    baseline = result["baseline_km"]
    improvement = 0.0 if baseline == 0 else (baseline - result["distance_km"]) / baseline * 100
    return RouteResponse(
        ordered_stop_ids=[body.stops[i].id for i in result["order"]],
        distance_km=result["distance_km"],
        baseline_km=baseline,
        improvement_pct=round(improvement, 2),
        passes=result["passes"],
        compute_ms=round(elapsed_ms, 2),
    )
