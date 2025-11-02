"""Thin async HTTP client for the registry and telemetry services."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, status


class Upstreams:
    def __init__(self, registry_url: str, telemetry_url: str, timeout_s: float = 5.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        # Short keep-alive expiry: kube-proxy balances per TCP connection, so long-lived
        # pooled connections would keep hammering the old pods after the HPA scales out.
        limits = httpx.Limits(max_connections=200, max_keepalive_connections=50, keepalive_expiry=5.0)
        common = {"timeout": timeout_s, "limits": limits, "transport": transport}
        self.registry = httpx.AsyncClient(base_url=registry_url, **common)
        self.telemetry = httpx.AsyncClient(base_url=telemetry_url, **common)

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
