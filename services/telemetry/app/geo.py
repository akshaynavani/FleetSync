"""Geodesic helpers and route optimisation.

Route optimisation is deliberately done in pure Python: it is the CPU-bound
workload that drives the telemetry Deployment's HorizontalPodAutoscaler.
"""

from __future__ import annotations

import math
from typing import Sequence

EARTH_RADIUS_KM = 6371.0088

Point = tuple[float, float]  # (lat, lon)


def haversine_km(a: Point, b: Point) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def path_length_km(points: Sequence[Point]) -> float:
    return sum(haversine_km(points[i], points[i + 1]) for i in range(len(points) - 1))


def _distance_matrix(points: Sequence[Point]) -> list[list[float]]:
    n = len(points)
    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine_km(points[i], points[j])
            dist[i][j] = dist[j][i] = d
    return dist


def _tour_length(tour: Sequence[int], dist: list[list[float]]) -> float:
    return sum(dist[tour[i]][tour[i + 1]] for i in range(len(tour) - 1))


def nearest_neighbour(dist: list[list[float]]) -> list[int]:
    """Greedy closed tour starting and ending at node 0 (the depot)."""
    n = len(dist)
    unvisited = set(range(1, n))
    tour = [0]
    while unvisited:
        last = tour[-1]
        nxt = min(unvisited, key=lambda j: dist[last][j])
        tour.append(nxt)
        unvisited.remove(nxt)
    tour.append(0)
    return tour


def two_opt(tour: list[int], dist: list[list[float]], max_passes: int) -> tuple[list[int], int]:
    """Improve a closed tour with 2-opt edge swaps. Endpoints (depot) stay fixed."""
    best = tour[:]
    passes = 0
    improved = True
    while improved and passes < max_passes:
        improved = False
        passes += 1
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best) - 1):
                a, b = best[i - 1], best[i]
                c, d = best[j], best[j + 1]
                delta = dist[a][c] + dist[b][d] - dist[a][b] - dist[c][d]
                if delta < -1e-9:
                    best[i : j + 1] = reversed(best[i : j + 1])
                    improved = True
    return best, passes


def optimise_route(depot: Point, stops: Sequence[Point], max_passes: int = 50) -> dict:
    """Return the visiting order of ``stops`` (indices into the input) for a depot round trip."""
    if not stops:
        return {"order": [], "distance_km": 0.0, "baseline_km": 0.0, "passes": 0}
    points = [depot, *stops]
    dist = _distance_matrix(points)
    baseline = _tour_length([0, *range(1, len(points)), 0], dist)
    greedy = nearest_neighbour(dist)
    tour, passes = two_opt(greedy, dist, max_passes)
    return {
        "order": [idx - 1 for idx in tour[1:-1]],
        "distance_km": round(_tour_length(tour, dist), 3),
        "baseline_km": round(baseline, 3),
        "passes": passes,
    }
