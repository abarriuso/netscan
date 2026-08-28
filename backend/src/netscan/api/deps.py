"""Shared API state.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from netscan.config import Settings, load_settings
from netscan.db.store import InventoryStore
from netscan.scanner import tools


def _find_frontend_dist() -> Path | None:
    """Locate the built dashboard bundle, if present, for static serving."""
    here = Path(__file__).resolve()
    # backend/src/netscan/api/deps.py -> repo root is parents[4]
    candidates = [
        here.parents[4] / "frontend" / "dist",
        Path.cwd() / "frontend" / "dist",
    ]
    for cand in candidates:
        if (cand / "index.html").is_file():
            return cand
    return None


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = InventoryStore(settings.db_url, str(settings.data_dir))
        self.scan_lock = threading.Lock()
        self.scan_progress: dict[str, object] = {"stage": "idle", "done": 0, "total": 0}
        self.ws_clients: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self._capabilities: tools.Capabilities | None = None
        # Server runtime bookkeeping (exposed via /api/system + /api/status).
        self.started_at = time.time()
        self.requests_served = 0
        self.scans_completed = 0
        self.last_scan_duration_s: float | None = None
        self.frontend_dist: Path | None = _find_frontend_dist()
        # Failed-auth timestamps per client IP (rate limiting; see api/app.py).
        self.auth_failures: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=50))

    def capabilities(self, refresh: bool = False) -> tools.Capabilities:
        """Cached capability detection — binaries don't change between requests."""
        if self._capabilities is None or refresh:
            self._capabilities = tools.Capabilities.detect()
        return self._capabilities

    def progress_callback(self, stage: str, done: int, total: int) -> None:
        self.scan_progress = {"stage": stage, "done": done, "total": total}
        if self.loop:
            self.loop.call_soon_threadsafe(self._broadcast)

    def _broadcast(self) -> None:
        for queue in list(self.ws_clients):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(self.scan_progress)


_state: AppState | None = None


def init_state(settings: Settings | None = None) -> AppState:
    global _state
    _state = AppState(settings or load_settings())
    return _state


def get_state() -> AppState:
    assert _state is not None, "AppState not initialized"
    return _state
