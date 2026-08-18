"""Proxmox VE API client (REST, API-token auth, raw httpx).

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

from typing import Any

import httpx

from netscan.config import ProxmoxInstance


class ProxmoxClient:
    def __init__(self, cfg: ProxmoxInstance, timeout: float = 10.0) -> None:
        self.cfg = cfg
        self.base = f"https://{cfg.host}:{cfg.port}/api2/json"
        self._client = httpx.Client(
            verify=cfg.verify_ssl,
            timeout=timeout,
            headers={"Authorization": f"PVEAPIToken={cfg.token_id}={cfg.token_secret}"},
        )

    def _get(self, path: str) -> Any:
        resp = self._client.get(f"{self.base}{path}")
        resp.raise_for_status()
        return resp.json().get("data")

    def version(self) -> dict[str, Any]:
        return dict(self._get("/version") or {})

    def nodes(self) -> list[dict[str, Any]]:
        return list(self._get("/nodes") or [])

    def cluster_resources(self) -> list[dict[str, Any]]:
        """All VMs, CTs, storages and nodes in one call."""
        return list(self._get("/cluster/resources") or [])

    def node_status(self, node: str) -> dict[str, Any]:
        return dict(self._get(f"/nodes/{node}/status") or {})

    def node_storage(self, node: str) -> list[dict[str, Any]]:
        return list(self._get(f"/nodes/{node}/storage") or [])

    def summary(self) -> dict[str, Any]:
        """Aggregated health view for the dashboard."""
        resources = self.cluster_resources()
        guests = [r for r in resources if r.get("type") in ("qemu", "lxc")]
        nodes = [r for r in resources if r.get("type") == "node"]
        return {
            "name": self.cfg.name,
            "host": self.cfg.host,
            "version": self.version().get("version", ""),
            "nodes": nodes,
            "guests": guests,
            "guests_running": sum(1 for g in guests if g.get("status") == "running"),
            "guests_total": len(guests),
        }


def collect_all(instances: list[ProxmoxInstance]) -> list[dict[str, Any]]:
    """Summaries for every enabled instance; failures are reported, not raised."""
    out: list[dict[str, Any]] = []
    for cfg in instances:
        if not cfg.enabled:
            continue
        try:
            out.append(ProxmoxClient(cfg).summary())
        except Exception as exc:  # network/auth errors must not break the API
            out.append({"name": cfg.name, "host": cfg.host, "error": str(exc)})
    return out
