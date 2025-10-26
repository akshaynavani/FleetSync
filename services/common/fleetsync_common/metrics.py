"""Prometheus request metrics exposed on /metrics for every service."""

from __future__ import annotations

import time

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest


def install_metrics(app: FastAPI, service: str) -> CollectorRegistry:
    """Attach request counters/latency histograms and a /metrics route to ``app``.

    A dedicated registry per app keeps metrics isolated, which matters when tests
    create several app instances in one process.
    """
    registry = CollectorRegistry()
    requests = Counter(
        "fleetsync_http_requests_total",
        "HTTP requests handled",
        ["service", "method", "route", "status"],
        registry=registry,
    )
    latency = Histogram(
        "fleetsync_http_request_duration_seconds",
        "HTTP request latency",
        ["service", "method", "route"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
        registry=registry,
    )

    @app.middleware("http")
    async def _record(request: Request, call_next):  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", "unmatched")
            if path != "/metrics":
                requests.labels(service, request.method, path, str(status)).inc()
                latency.labels(service, request.method, path).observe(time.perf_counter() - start)

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return registry
