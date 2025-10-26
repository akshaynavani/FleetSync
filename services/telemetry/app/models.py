from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Reading(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    speed_kph: float = Field(ge=0, le=300)
    fuel_pct: float = Field(ge=0, le=100)
    engine_temp_c: float = Field(ge=-50, le=200)
    recorded_at: datetime | None = None


class StoredReading(Reading):
    vehicle_id: str
    recorded_at: datetime


class Summary(BaseModel):
    vehicle_id: str
    readings: int
    avg_speed_kph: float
    max_engine_temp_c: float
    min_fuel_pct: float
    distance_km: float
    alerts: list[str]


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Stop(Location):
    id: str = Field(min_length=1, max_length=64)


class RouteRequest(BaseModel):
    depot: Location
    stops: list[Stop] = Field(max_length=250)
    max_passes: int = Field(default=50, ge=1, le=500)


class RouteResponse(BaseModel):
    ordered_stop_ids: list[str]
    distance_km: float
    baseline_km: float
    improvement_pct: float
    passes: int
    compute_ms: float
