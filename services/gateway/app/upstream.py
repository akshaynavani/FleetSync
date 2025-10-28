"""Thin async HTTP client for the registry and telemetry services."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, status


class Upstreams:
    def __init__(self, registry_url: str, telemetry_url: str, timeout_s: float = 5.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.registry = httpx.AsyncClient(base_url=registry_url, timeout=timeout_s, transport=transport)
        self.telemetry = httpx.AsyncClient(base_url=telemetry_url, timeout=timeout_s, transport=transport)

    async def aclose(self) -> None:
        await self.registry.aclose()
        await self.telemetry.aclose()

    @staticmethod
    async def call(client: httpx.AsyncClient, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Issue a request, mapping transport failures to 502/504 for the caller."""
        try:
            return await client.request(method, path, **kwargs)
        except httpx.TimeoutException:
            raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, f"upstream {client.base_url} timed out")
        except httpx.HTTPError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"upstream {client.base_url} unreachable: {exc}")
