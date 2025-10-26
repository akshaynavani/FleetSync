from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class VehicleStatus(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


# Allowed status transitions. Retired vehicles are terminal.
TRANSITIONS: dict[VehicleStatus, set[VehicleStatus]] = {
    VehicleStatus.ACTIVE: {VehicleStatus.IDLE, VehicleStatus.MAINTENANCE, VehicleStatus.RETIRED},
    VehicleStatus.IDLE: {VehicleStatus.ACTIVE, VehicleStatus.MAINTENANCE, VehicleStatus.RETIRED},
    VehicleStatus.MAINTENANCE: {VehicleStatus.IDLE, VehicleStatus.ACTIVE, VehicleStatus.RETIRED},
    VehicleStatus.RETIRED: set(),
}


class VehicleCreate(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$", description="Fleet-unique vehicle identifier")
    model: str = Field(min_length=1, max_length=128)
    depot: str = Field(min_length=1, max_length=64)
    capacity_kg: int = Field(ge=0, le=100_000, default=1000)


class Vehicle(VehicleCreate):
    status: VehicleStatus = VehicleStatus.IDLE
    created_at: datetime
    updated_at: datetime


class StatusUpdate(BaseModel):
    status: VehicleStatus
