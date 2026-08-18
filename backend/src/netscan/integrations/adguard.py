"""AdGuard Home API client.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

from typing import Any

import httpx

from netscan.config import AdGuardInstance


class AdGuardClient:
    def __init__(self, cfg: AdGuardInstance, timeout: float = 10.0) -> None:
        self.cfg = cfg
        scheme = "https" if cfg.use_ssl else "http"
        self.base = f"{scheme}://{cfg.host}:{cfg.port}/control"
        self._client = httpx.Client(
            verify=False,
            timeout=timeout,
            auth=(cfg.username, cfg.password) if cfg.username else None,
        )

    def _get(self, path: str) -> Any:
        resp = self._client.get(f"{self.base}{path}")
        resp.raise_for_status()
        return resp.json()

    def status(self) -> dict[str, Any]:
        return dict(self._get("/status") or {})

    def stats(self) -> dict[str, Any]:
        return dict(self._get("/stats") or {})

    def clients(self) -> list[dict[str, Any]]:
        data = self._get("/clients") or {}
        return list(data.get("clients", []))

    def summary(self) -> dict[str, Any]:
        stats = self.stats()
        return {
            "name": self.cfg.name,
            "host": self.cfg.host,
            "version": self.status().get("version", ""),
            "clients": self.clients(),
            "num_dns_queries": stats.get("num_dns_queries", 0),
            "num_blocked_filtering": stats.get("num_blocked_filtering", 0),
            "avg_processing_time": stats.get("avg_processing_time", 0),
            "top_queried_domains": stats.get("top_queried_domains", [])[:10],
            "top_blocked_domains": stats.get("top_blocked_domains", [])[:10],
        }


def collect_all(instances: list[AdGuardInstance]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cfg in instances:
        if not cfg.enabled:
            continue
        try:
            out.append(AdGuardClient(cfg).summary())
        except Exception as exc:
            out.append({"name": cfg.name, "host": cfg.host, "error": str(exc)})
    return out
