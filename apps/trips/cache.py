from __future__ import annotations

import hashlib
import json
import logging

from django.core.cache import cache

logger    = logging.getLogger(__name__)
CACHE_TTL = 60 * 60 * 24  # 24 hours


def make_cache_key(
    c_lat: float, c_lng: float,
    p_lat: float, p_lng: float,
    d_lat: float, d_lng: float,
    cycle_hours: float,
) -> str:
    payload = json.dumps(
        {
            "c": [round(c_lat, 3), round(c_lng, 3)],
            "p": [round(p_lat, 3), round(p_lng, 3)],
            "d": [round(d_lat, 3), round(d_lng, 3)],
            "h": round(cycle_hours, 1),
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"trip:{digest}"


def get_cached_plan(key: str) -> dict | None:
    try:
        return cache.get(key)
    except Exception:
        logger.warning("Redis read failed for key %s", key, exc_info=True)
        return None


def set_cached_plan(key: str, data: dict) -> None:
    try:
        cache.set(key, data, timeout=CACHE_TTL)
    except Exception:
        logger.warning("Redis write failed for key %s", key, exc_info=True)
