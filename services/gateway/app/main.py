"""FleetSync API gateway: the single public entrypoint in front of the fleet services."""

from __future__ import annotations

import asyncio
import socket
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response, status

from fleetsync_common import configure_logging, env_int, env_str, install_metrics

from .upstream import Upstreams

SERVICE = "gateway"
log = configure_logging(SERVICE, env_str("LOG_LEVEL", "INFO"))


def build_upstreams() -> Upstreams:
    return Upstreams(
        registry_url=env_str("REGISTRY_URL", "http://localhost:8000"),
        telemetry_url=env_str("TELEMETRY_URL", "http://localhost:8001"),
        timeout_s=env_int("UPSTREAM_TIMEOUT_S", 10),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    if getattr(app.state, "upstreams", None) is None:
        app.state.upstreams = build_upstreams()
    yield
    await app.state.upstreams.aclose()


app = FastAPI(title="FleetSync Gateway", version="1.0.0", lifespan=lifespan)
app.state.upstreams = None
install_metrics(app, SERVICE)


def get_upstreams(request: Request) -> Upstreams:
    return request.app.state.upstreams


def relay(resp: httpx.Response) -> Response:
    """Pass an upstream response straight through to the client."""
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )


# --------------------------------------------------------------------------- health


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok", "service": SERVICE, "pod": socket.gethostname()}


@app.get("/readyz", include_in_schema=False)
async def readyz(response: Response, up: Upstreams = Depends(get_upstreams)) -> dict:
    checks: dict[str, str] = {}
    for name, client in (("registry", up.registry), ("telemetry", up.telemetry)):
        try:
            r = await client.get("/healthz")
            checks[name] = "ok" if r.status_code == 200 else f"status {r.status_code}"
        except httpx.HTTPError as exc:
            checks[name] = f"error: {exc.__class__.__name__}"
    ready = all(v == "ok" for v in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready else "degraded", "upstreams": checks}


# --------------------------------------------------------------------------- vehicles


@app.post("/api/vehicles", status_code=status.HTTP_201_CREATED)
async def register_vehicle(body: dict[str, Any] = Body(...), up: Upstreams = Depends(get_upstreams)) -> Response:
    return relay(await up.call(up.registry, "POST", "/vehicles", json=body))


@app.get("/api/vehicles")
async def list_vehicles(request: Request, up: Upstreams = Depends(get_upstreams)) -> Response:
    return relay(await up.call(up.registry, "GET", "/vehicles", params=dict(request.query_params)))


@app.get("/api/vehicles/{vehicle_id}")
async def get_vehicle(vehicle_id: str, up: Upstreams = Depends(get_upstreams)) -> Response:
    return relay(await up.call(up.registry, "GET", f"/vehicles/{vehicle_id}"))


@app.patch("/api/vehicles/{vehicle_id}/status")
async def update_status(vehicle_id: str, body: dict[str, Any] = Body(...),
                        up: Upstreams = Depends(get_upstreams)) -> Response:
    return relay(await up.call(up.registry, "PATCH", f"/vehicles/{vehicle_id}/status", json=body))


@app.delete("/api/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle(vehicle_id: str, up: Upstreams = Depends(get_upstreams)) -> Response:
    resp = await up.call(up.registry, "DELETE", f"/vehicles/{vehicle_id}")
    if resp.status_code == 204:
        return Response(status_code=204)
    return relay(resp)


# --------------------------------------------------------------------------- telemetry


@app.post("/api/vehicles/{vehicle_id}/telemetry", status_code=status.HTTP_202_ACCEPTED)
async def ingest_telemetry(vehicle_id: str, body: dict[str, Any] = Body(...),
                           up: Upstreams = Depends(get_upstreams)) -> Response:
    vehicle = await up.call(up.registry, "GET", f"/vehicles/{vehicle_id}")
    if vehicle.status_code == 404:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"vehicle {vehicle_id} is not registered")
    if vehicle.status_code != 200:
        return relay(vehicle)
    if vehicle.json().get("status") == "retired":
        raise HTTPException(status.HTTP_409_CONFLICT, f"vehicle {vehicle_id} is retired")
    return relay(await up.call(up.telemetry, "POST", f"/telemetry/{vehicle_id}", json=body))


@app.get("/api/vehicles/{vehicle_id}/telemetry")
async def telemetry_history(vehicle_id: str, request: Request, up: Upstreams = Depends(get_upstreams)) -> Response:
    return relay(await up.call(up.telemetry, "GET", f"/telemetry/{vehicle_id}", params=dict(request.query_params)))


@app.get("/api/vehicles/{vehicle_id}/summary")
async def telemetry_summary(vehicle_id: str, up: Upstreams = Depends(get_upstreams)) -> Response:
    return relay(await up.call(up.telemetry, "GET", f"/telemetry/{vehicle_id}/summary"))


@app.post("/api/routes/optimize")
async def optimise_route(body: dict[str, Any] = Body(...), up: Upstreams = Depends(get_upstreams)) -> Response:
    return relay(await up.call(up.telemetry, "POST", "/routes/optimize", json=body))


# --------------------------------------------------------------------------- fleet overview


@app.get("/api/fleet/overview")
async def fleet_overview(up: Upstreams = Depends(get_upstreams)) -> dict:
    """Aggregate registry state and the latest telemetry for every vehicle."""
    vehicles_resp, stats_resp = await asyncio.gather(
        up.call(up.registry, "GET", "/vehicles"),
        up.call(up.registry, "GET", "/vehicles/stats"),
    )
    if vehicles_resp.status_code != 200 or stats_resp.status_code != 200:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "registry returned an error")
    vehicles = vehicles_resp.json()

    latest: dict[str, Any] = {}
    if vehicles:
        ids = ",".join(v["id"] for v in vehicles)
        latest_resp = await up.call(up.telemetry, "GET", "/telemetry/latest", params={"ids": ids})
        if latest_resp.status_code == 200:
            latest = latest_resp.json()

    reporting = sum(1 for v in vehicles if latest.get(v["id"]))
    return {
        "stats": stats_resp.json(),
        "reporting_vehicles": reporting,
        "vehicles": [{**v, "latest_telemetry": latest.get(v["id"])} for v in vehicles],
        "served_by": socket.gethostname(),
    }
