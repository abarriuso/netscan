"""TrueNAS (CORE/SCALE) REST API v2.0 client.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

from typing import Any

import httpx

from netscan.config import TrueNASInstance


class TrueNASClient:
    def __init__(self, cfg: TrueNASInstance, timeout: float = 10.0) -> None:
        self.cfg = cfg
        scheme = "https" if cfg.use_ssl else "http"
        self.base = f"{scheme}://{cfg.host}:{cfg.port}/api/v2.0"
        self._client = httpx.Client(
            verify=cfg.verify_ssl,
            timeout=timeout,
            headers={"Authorization": f"Bearer {cfg.api_key}"},
        )

    def _get(self, path: str) -> Any:
        resp = self._client.get(f"{self.base}{path}")
        resp.raise_for_status()
        return resp.json()

    def system_info(self) -> dict[str, Any]:
        return dict(self._get("/system/info") or {})

    def pools(self) -> list[dict[str, Any]]:
        return list(self._get("/pool") or [])

    def disks(self) -> list[dict[str, Any]]:
        return list(self._get("/disk") or [])

    def alerts(self) -> list[dict[str, Any]]:
        return list(self._get("/alert/list") or [])

    def smart_summary(self) -> list[dict[str, Any]]:
        """SMART test results per disk (best effort across CORE/SCALE)."""
        try:
            return list(self._get("/smart/test/results?limit=100") or [])
        except httpx.HTTPError:
            return []

    def summary(self) -> dict[str, Any]:
        info = self.system_info()
        pools = self.pools()
        return {
            "name": self.cfg.name,
            "host": self.cfg.host,
            "version": info.get("version", ""),
            "hostname": info.get("hostname", ""),
            "uptime_seconds": info.get("uptime_seconds", 0),
            "loadavg": info.get("loadavg", []),
            "physmem": info.get("physmem", 0),
            "cores": info.get("cores", 0),
            "pools": pools,
            "pools_healthy": sum(1 for p in pools if p.get("status") == "ONLINE"),
            "pools_total": len(pools),
            "disks": self.disks(),
            "alerts": self.alerts(),
        }


def collect_all(instances: list[TrueNASInstance]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cfg in instances:
        if not cfg.enabled:
            continue
        try:
            out.append(TrueNASClient(cfg).summary())
        except Exception as exc:
            out.append({"name": cfg.name, "host": cfg.host, "error": str(exc)})
    return out
