"""Redis storage for telemetry: a capped list of readings per vehicle."""

from __future__ import annotations

import redis

from .models import StoredReading


class TelemetryStore:
    def __init__(self, client: redis.Redis, history_limit: int = 500) -> None:
        self.r = client
        self.history_limit = history_limit

    def ping(self) -> bool:
        return bool(self.r.ping())

    def append(self, reading: StoredReading) -> int:
        key = f"telemetry:{reading.vehicle_id}"
        pipe = self.r.pipeline()
        pipe.lpush(key, reading.model_dump_json())
        pipe.ltrim(key, 0, self.history_limit - 1)
        pipe.set(f"telemetry:latest:{reading.vehicle_id}", reading.model_dump_json())
        pipe.incr("telemetry:ingested_total")
        results = pipe.execute()
        return int(results[-1])

    def history(self, vehicle_id: str, limit: int) -> list[StoredReading]:
        """Most recent first."""
        raw = self.r.lrange(f"telemetry:{vehicle_id}", 0, max(0, limit - 1))
        return [StoredReading.model_validate_json(item) for item in raw]

    def latest(self, vehicle_id: str) -> StoredReading | None:
        raw = self.r.get(f"telemetry:latest:{vehicle_id}")
        return StoredReading.model_validate_json(raw) if raw else None

    def latest_many(self, vehicle_ids: list[str]) -> dict[str, StoredReading | None]:
        if not vehicle_ids:
            return {}
        raw = self.r.mget([f"telemetry:latest:{vid}" for vid in vehicle_ids])
        return {
            vid: StoredReading.model_validate_json(item) if item else None
            for vid, item in zip(vehicle_ids, raw)
        }

    def ingested_total(self) -> int:
        return int(self.r.get("telemetry:ingested_total") or 0)
