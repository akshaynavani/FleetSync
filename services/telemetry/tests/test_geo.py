import math
import random

from app import geo


def test_haversine_known_distance():
    # London -> Paris is roughly 343 km.
    d = geo.haversine_km((51.5074, -0.1278), (48.8566, 2.3522))
    assert 340 < d < 347


def test_haversine_zero():
    assert geo.haversine_km((10.0, 10.0), (10.0, 10.0)) == 0


def test_optimise_empty():
    assert geo.optimise_route((0, 0), [])["order"] == []


def test_optimise_visits_every_stop_once():
    rng = random.Random(7)
    stops = [(rng.uniform(40, 41), rng.uniform(-74, -73)) for _ in range(30)]
    result = geo.optimise_route((40.5, -73.5), stops)
    assert sorted(result["order"]) == list(range(30))


def test_optimise_never_worse_than_baseline():
    rng = random.Random(42)
    stops = [(rng.uniform(0, 1), rng.uniform(0, 1)) for _ in range(40)]
    result = geo.optimise_route((0.5, 0.5), stops)
    assert result["distance_km"] <= result["baseline_km"] + 1e-6


def test_optimise_collinear_points_in_order():
    # Stops on a line, given shuffled; optimal round trip walks them in order.
    stops = [(0.0, x / 10) for x in (3, 1, 4, 2, 5)]
    result = geo.optimise_route((0.0, 0.0), stops)
    lons = [stops[i][1] for i in result["order"]]
    assert lons == sorted(lons) or lons == sorted(lons, reverse=True)
    assert math.isclose(result["distance_km"], 2 * geo.haversine_km((0, 0), (0, 0.5)), rel_tol=1e-6)
