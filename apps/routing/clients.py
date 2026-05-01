from __future__ import annotations

import logging

import httpx

from .exceptions import GeocodingError, RoutingError

logger = logging.getLogger(__name__)

NOMINATIM_URL        = "https://nominatim.openstreetmap.org/search"
OSRM_BASE_URL        = "http://router.project-osrm.org/route/v1/driving"
NOMINATIM_RATE_DELAY = 1.1  # seconds — Nominatim ToS: max 1 req/sec


def geocode_address(address: str) -> tuple[float, float, str]:
    params  = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": "SpotterAI-ELDPlanner/1.0"}

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(NOMINATIM_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise GeocodingError(f"Geocoding request failed for {address!r}: {exc}") from exc

    if not data:
        raise GeocodingError(f"Location not found: {address!r}")

    result = data[0]
    return float(result["lat"]), float(result["lon"]), result["display_name"]


def get_route(waypoints: list[tuple[float, float]]) -> dict:
    coords = ";".join(f"{lng},{lat}" for lat, lng in waypoints)
    url    = f"{OSRM_BASE_URL}/{coords}"
    params = {"overview": "full", "geometries": "geojson", "steps": "false"}

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise RoutingError(f"Routing request failed: {exc}") from exc

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"OSRM returned no valid route: code={data.get('code')!r}")

    route = data["routes"][0]
    return {
        "distance_miles": route["distance"] * 0.000621371,
        "duration_hours": route["duration"] / 3600,
        "geometry":       route["geometry"],
    }


def get_route_with_legs(waypoints: list[tuple[float, float]]) -> dict:
    """
    Single OSRM call for a multi-waypoint route.

    Returns the full route geometry plus per-leg distance and duration,
    avoiding N separate requests when planning a multi-stop trip.
    """
    coords = ";".join(f"{lng},{lat}" for lat, lng in waypoints)
    url    = f"{OSRM_BASE_URL}/{coords}"
    params = {"overview": "full", "geometries": "geojson", "steps": "false"}

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise RoutingError(f"Routing request failed: {exc}") from exc

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"OSRM returned no valid route: code={data.get('code')!r}")

    route = data["routes"][0]
    return {
        "geometry": route["geometry"],
        "legs": [
            {
                "distance_miles": leg["distance"] * 0.000621371,
                "duration_hours": leg["duration"] / 3600,
            }
            for leg in route["legs"]
        ],
    }
