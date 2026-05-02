from __future__ import annotations

import time
import uuid
import logging

from django.db import transaction

from apps.eld.services import build_daily_logs
from apps.routing.clients import NOMINATIM_RATE_DELAY, geocode_address, get_route_with_legs
from hos.engine import plan_trip

from .cache import get_cached_plan, make_cache_key, set_cached_plan
from .models import TripPlan, TripRequest

logger = logging.getLogger(__name__)


def plan_trip_service(validated_data: dict) -> dict:
    """
    Orchestrates geocoding → cache check → routing → HOS simulation →
    ELD log building → DB persistence → cache write.

    Raises:
        apps.routing.exceptions.GeocodingError  — location not found
        apps.routing.exceptions.RoutingError    — OSRM request failed
    """
    d = validated_data

    c_lat,  c_lng,  c_name  = geocode_address(d["current_location"])
    time.sleep(NOMINATIM_RATE_DELAY)
    p_lat,  p_lng,  p_name  = geocode_address(d["pickup_location"])
    time.sleep(NOMINATIM_RATE_DELAY)
    dr_lat, dr_lng, dr_name = geocode_address(d["dropoff_location"])

    cache_key = make_cache_key(
        c_lat, c_lng, p_lat, p_lng, dr_lat, dr_lng,
        d["current_cycle_used_hours"],
    )

    cached = get_cached_plan(cache_key)
    if cached:
        return {**cached, "cached": True}

    route_data = get_route_with_legs([(c_lat, c_lng), (p_lat, p_lng), (dr_lat, dr_lng)])
    leg1       = route_data["legs"][0]
    leg2       = route_data["legs"][1]

    hos_result = plan_trip(
        current_lat=c_lat,   current_lng=c_lng,   current_name=c_name,
        pickup_lat=p_lat,    pickup_lng=p_lng,    pickup_name=p_name,
        dropoff_lat=dr_lat,  dropoff_lng=dr_lng,  dropoff_name=dr_name,
        cycle_used_hours=d["current_cycle_used_hours"],
        route_legs=[leg1, leg2],
    )

    merged_segments = hos_result.pop("_merged_segments")
    daily_logs      = build_daily_logs(merged_segments)

    _fill_daily_miles(daily_logs, hos_result["total_driving_hours"], hos_result["total_distance_miles"])

    plan_data = {
        **hos_result,
        "trip_id":    str(uuid.uuid4()),
        "route":      route_data["geometry"],
        "daily_logs": daily_logs,
        "total_days": len(daily_logs),
        "cached":     False,
    }

    _persist(d, c_lat, c_lng, p_lat, p_lng, dr_lat, dr_lng, plan_data, cache_key)
    set_cached_plan(cache_key, plan_data)

    return plan_data


def _fill_daily_miles(
    daily_logs: list[dict],
    total_driving_hours: float,
    total_distance_miles: float,
) -> None:
    for log in daily_logs:
        day_drive = log["totals"]["driving"]
        if total_driving_hours > 0:
            log["total_miles_today"] = round(
                total_distance_miles * day_drive / total_driving_hours
            )
        else:
            log["total_miles_today"] = 0


def _persist(
    validated_data: dict,
    c_lat: float, c_lng: float,
    p_lat: float, p_lng: float,
    dr_lat: float, dr_lng: float,
    plan_data: dict,
    cache_key: str,
) -> None:
    d = validated_data

    with transaction.atomic():
        trip_req = TripRequest.objects.create(
            current_location=d["current_location"],
            current_lat=c_lat, current_lng=c_lng,
            pickup_location=d["pickup_location"],
            pickup_lat=p_lat,  pickup_lng=p_lng,
            dropoff_location=d["dropoff_location"],
            dropoff_lat=dr_lat, dropoff_lng=dr_lng,
            current_cycle_used_hours=d["current_cycle_used_hours"],
        )

        TripPlan.objects.create(
            trip_request=trip_req,
            total_distance_miles=plan_data["total_distance_miles"],
            total_driving_hours=plan_data["total_driving_hours"],
            total_days=plan_data["total_days"],
            route_geometry=plan_data["route"],
            stops=plan_data["stops"],
            eld_segments=plan_data["eld_segments"],
            daily_logs=plan_data["daily_logs"],
            cache_key=cache_key,
        )
