"""Redis-backed vehicle storage.

Each vehicle is a hash at ``vehicle:<id>``; the set ``vehicles`` indexes ids and
``depot:<name>`` sets index vehicles per depot.
"""

from __future__ import annotations

from datetime import datetime, timezone

import redis

from .models import TRANSITIONS, Vehicle, VehicleCreate, VehicleStatus


class VehicleExists(Exception):
    pass


class VehicleNotFound(Exception):
    pass


class InvalidTransition(Exception):
    def __init__(self, current: VehicleStatus, requested: VehicleStatus) -> None:
        super().__init__(f"cannot move vehicle from {current.value} to {requested.value}")
        self.current = current
        self.requested = requested


def _key(vehicle_id: str) -> str:
    return f"vehicle:{vehicle_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VehicleStore:
    def __init__(self, client: redis.Redis) -> None:
        self.r = client

    def ping(self) -> bool:
        return bool(self.r.ping())

    def create(self, data: VehicleCreate) -> Vehicle:
        now = _now()
        record = {
            "id": data.id,
            "model": data.model,
            "depot": data.depot,
            "capacity_kg": str(data.capacity_kg),
            "status": VehicleStatus.IDLE.value,
            "created_at": now,
            "updated_at": now,
        }
        # HSETNX on the id field makes creation atomic w.r.t. concurrent creators.
        if not self.r.hsetnx(_key(data.id), "id", data.id):
            raise VehicleExists(data.id)
        pipe = self.r.pipeline()
        pipe.hset(_key(data.id), mapping=record)
        pipe.sadd("vehicles", data.id)
        pipe.sadd(f"depot:{data.depot}", data.id)
        pipe.execute()
        return self._decode(record)

    def get(self, vehicle_id: str) -> Vehicle:
        raw = self.r.hgetall(_key(vehicle_id))
        if not raw or "status" not in self._text(raw):
            raise VehicleNotFound(vehicle_id)
        return self._decode(self._text(raw))

    def list(self, depot: str | None = None, status: VehicleStatus | None = None) -> list[Vehicle]:
        ids = self.r.smembers(f"depot:{depot}" if depot else "vehicles")
        pipe = self.r.pipeline()
        for vid in sorted(self._text_one(i) for i in ids):
            pipe.hgetall(_key(vid))
        vehicles = [self._decode(self._text(raw)) for raw in pipe.execute() if raw]
        if status:
            vehicles = [v for v in vehicles if v.status == status]
        return vehicles

    def set_status(self, vehicle_id: str, new_status: VehicleStatus) -> Vehicle:
        key = _key(vehicle_id)
        # Optimistic locking so two concurrent transitions cannot both win.
        with self.r.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    current_raw = pipe.hget(key, "status")
                    if current_raw is None:
                        raise VehicleNotFound(vehicle_id)
                    current = VehicleStatus(self._text_one(current_raw))
                    if new_status != current and new_status not in TRANSITIONS[current]:
                        raise InvalidTransition(current, new_status)
                    pipe.multi()
                    pipe.hset(key, mapping={"status": new_status.value, "updated_at": _now()})
                    pipe.execute()
                    break
                except redis.WatchError:
                    continue
        return self.get(vehicle_id)

    def delete(self, vehicle_id: str) -> None:
        vehicle = self.get(vehicle_id)
        pipe = self.r.pipeline()
        pipe.delete(_key(vehicle_id))
        pipe.srem("vehicles", vehicle_id)
        pipe.srem(f"depot:{vehicle.depot}", vehicle_id)
        pipe.execute()

    def count_by_status(self) -> dict[str, int]:
        counts = {s.value: 0 for s in VehicleStatus}
        for v in self.list():
            counts[v.status.value] += 1
        return counts

    @staticmethod
    def _text_one(value: bytes | str) -> str:
        return value.decode() if isinstance(value, bytes) else value

    @classmethod
    def _text(cls, raw: dict) -> dict[str, str]:
        return {cls._text_one(k): cls._text_one(v) for k, v in raw.items()}

    @staticmethod
    def _decode(record: dict[str, str]) -> Vehicle:
        return Vehicle(
            id=record["id"],
            model=record["model"],
            depot=record["depot"],
            capacity_kg=int(record["capacity_kg"]),
            status=VehicleStatus(record["status"]),
            created_at=datetime.fromisoformat(record["created_at"]),
            updated_at=datetime.fromisoformat(record["updated_at"]),
        )
