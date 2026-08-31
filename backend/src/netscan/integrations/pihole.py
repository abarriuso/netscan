"""Pi-hole API client (v6 only — v5's API is a different shape and is end-of-life).

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

Implemented against Pi-hole v6's documented REST API shape (session-based
auth: POST /api/auth with a password returns a session id used as the `sid`
header on every subsequent call). Not yet verified against a live Pi-hole
instance — field lookups use .get() defensively like AdGuardClient, so an
API detail this got wrong degrades to a missing field rather than a crash;
collect_all() below also isolates any instance's failure from the rest.
"""

from __future__ import annotations

from typing import Any

import httpx

from netscan.config import PiholeInstance


class PiholeClient:
    def __init__(self, cfg: PiholeInstance, timeout: float = 10.0) -> None:
        self.cfg = cfg
        scheme = "https" if cfg.use_ssl else "http"
        self.base = f"{scheme}://{cfg.host}:{cfg.port}/api"
        self._client = httpx.Client(verify=cfg.verify_ssl, timeout=timeout)
        self._sid: str | None = None

    def _authenticate(self) -> None:
        resp = self._client.post(f"{self.base}/auth", json={"password": self.cfg.password})
        resp.raise_for_status()
        session = resp.json().get("session", {})
        if not session.get("valid"):
            raise RuntimeError("Pi-hole: autenticación rechazada (contraseña incorrecta)")
        self._sid = session.get("sid")

    def _get(self, path: str) -> Any:
        if self._sid is None:
            self._authenticate()
        resp = self._client.get(f"{self.base}{path}", headers={"sid": self._sid or ""})
        if resp.status_code == 401:
            # Session expired mid-poll — re-auth once and retry.
            self._authenticate()
            resp = self._client.get(f"{self.base}{path}", headers={"sid": self._sid or ""})
        resp.raise_for_status()
        return resp.json()

    def summary(self) -> dict[str, Any]:
        stats = self._get("/stats/summary")
        queries = stats.get("queries", {})
        gravity = stats.get("gravity", {})
        return {
            "name": self.cfg.name,
            "host": self.cfg.host,
            "num_dns_queries": queries.get("total", 0),
            "num_blocked_filtering": queries.get("blocked", 0),
            "percent_blocked": queries.get("percent_blocked", 0),
            "domains_being_blocked": gravity.get("domains_being_blocked", 0),
            "unique_clients": queries.get("unique_clients", 0),
        }


def collect_all(instances: list[PiholeInstance]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cfg in instances:
        if not cfg.enabled:
            continue
        try:
            out.append(PiholeClient(cfg).summary())
        except Exception as exc:
            out.append({"name": cfg.name, "host": cfg.host, "error": str(exc)})
    return out
