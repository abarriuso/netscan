"""Timestamps for the API: always with the server's UTC offset.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

NetScan stores naive local times (``datetime.now()``) in SQLite. Sent as-is,
"2026-10-27T10:00:00" is read by the browser as *its own* local time — so a
server in UTC (the default of a Proxmox LXC) and a browser in Europe/Madrid
disagree by an hour on every "x min ago", uptime duration and event order.
Everything the API emits goes through :func:`iso` / :func:`localize`, which
attach the server's offset ("…T10:00:00+00:00"), so any browser converts it
to its own zone correctly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def aware(dt: datetime) -> datetime:
    """A naive server-local datetime as an aware one (no conversion)."""
    return dt.astimezone() if dt.tzinfo is None else dt


def iso(dt: datetime | None, timespec: str = "seconds") -> str | None:
    """ISO 8601 with the UTC offset, or None."""
    if dt is None:
        return None
    return aware(dt).isoformat(timespec=timespec)


def now_iso(timespec: str = "seconds") -> str:
    return datetime.now().astimezone().isoformat(timespec=timespec)


def localize(obj: Any) -> Any:
    """Recursively replace datetimes (and naive ISO strings is NOT attempted:
    only real datetime objects) with offset-carrying ISO strings."""
    if isinstance(obj, datetime):
        return iso(obj)
    if isinstance(obj, dict):
        return {k: localize(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [localize(v) for v in obj]
    return obj
