"""FleetSync load profile.

Simulates a fleet of vehicles streaming telemetry, dispatchers polling the fleet
overview, and planners requesting CPU-heavy route optimisations. The route traffic
is what pushes the telemetry Deployment past its HPA CPU target.

Run headless against a port-forwarded gateway:
    locust -f tests/performance/locustfile.py --host http://localhost:8080 \
        --headless -u 50 -r 5 -t 5m --csv results/fleetsync

Tunables (env vars): FLEET_SIZE, ROUTE_STOPS, ROUTE_WEIGHT.
"""

from __future__ import annotations

import math
import os
import random
import uuid

from locust import HttpUser, LoadTestShape, between, events, task

FLEET_SIZE = int(os.getenv("FLEET_SIZE", "50"))
ROUTE_STOPS = int(os.getenv("ROUTE_STOPS", "120"))
ROUTE_WEIGHT = int(os.getenv("ROUTE_WEIGHT", "3"))
RUN_ID = uuid.uuid4().hex[:6]
DEPOT = (40.7128, -74.0060)

FLEET = [f"load-{RUN_ID}-{i:03d}" for i in range(FLEET_SIZE)]


@events.test_start.add_listener
def register_fleet(environment, **_kwargs):
    """Register the simulated fleet once before users start."""
    import httpx

    host = environment.host or "http://localhost:8080"
    with httpx.Client(base_url=host, timeout=30) as client:
        for vid in FLEET:
            client.post("/api/vehicles", json={"id": vid, "model": "LoadVan", "depot": f"load-{RUN_ID}"})
            client.patch(f"/api/vehicles/{vid}/status", json={"status": "active"})


@events.test_stop.add_listener
def remove_fleet(environment, **_kwargs):
    import httpx

    host = environment.host or "http://localhost:8080"
    with httpx.Client(base_url=host, timeout=30) as client:
        for vid in FLEET:
            client.delete(f"/api/vehicles/{vid}")


class FleetUser(HttpUser):
    wait_time = between(0.2, 1.0)

    def on_start(self) -> None:
        self.vid = random.choice(FLEET)
        self.lat, self.lon = DEPOT
        self.fuel = 100.0

    @task(10)
    def send_telemetry(self) -> None:
        heading = random.uniform(0, 2 * math.pi)
        self.lat += 0.002 * math.sin(heading)
        self.lon += 0.002 * math.cos(heading)
        self.fuel = max(0.0, self.fuel - random.uniform(0, 0.3))
        if self.fuel < 5:
            self.fuel = 100.0
        self.client.post(
            f"/api/vehicles/{self.vid}/telemetry",
            json={
                "lat": round(self.lat, 6),
                "lon": round(self.lon, 6),
                "speed_kph": round(random.uniform(0, 90), 1),
                "fuel_pct": round(self.fuel, 1),
                "engine_temp_c": round(random.gauss(92, 6), 1),
            },
            name="/api/vehicles/[id]/telemetry",
        )

    @task(2)
    def vehicle_summary(self) -> None:
        self.client.get(f"/api/vehicles/{self.vid}/summary", name="/api/vehicles/[id]/summary")

    @task(1)
    def fleet_overview(self) -> None:
        self.client.get("/api/fleet/overview")

    @task(ROUTE_WEIGHT)
    def optimise_route(self) -> None:
        stops = [
            {"id": f"stop-{i}", "lat": DEPOT[0] + random.uniform(-0.2, 0.2), "lon": DEPOT[1] + random.uniform(-0.2, 0.2)}
            for i in range(ROUTE_STOPS)
        ]
        with self.client.post(
            "/api/routes/optimize",
            json={"depot": {"lat": DEPOT[0], "lon": DEPOT[1]}, "stops": stops, "max_passes": 50},
            catch_response=True,
        ) as resp:
            if resp.status_code == 200 and len(resp.json().get("ordered_stop_ids", [])) != ROUTE_STOPS:
                resp.failure("route response did not include every stop")


if os.getenv("LOAD_SHAPE") == "step":
    # Locust auto-uses any LoadTestShape it finds in the module, so only define one
    # when explicitly requested; otherwise -u/-r/-t on the command line apply.

    class StepLoad(LoadTestShape):
        """Ramp in steps so the HPA has time to react between plateaus, then cool down."""

        stages = [
            (60, 10, 2),    # (until second, users, spawn rate)
            (180, 30, 5),
            (300, 60, 5),
            (420, 60, 5),
            (480, 5, 10),   # cool-down so scale-in starts to show
        ]

        def tick(self):
            run_time = self.get_run_time()
            for until, users, rate in self.stages:
                if run_time < until:
                    return users, rate
            return None
