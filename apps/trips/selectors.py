from __future__ import annotations

import uuid

from django.shortcuts import get_object_or_404

from .models import TripPlan, TripRequest


def get_trip_request_by_id(trip_id: str | uuid.UUID) -> TripRequest:
    return get_object_or_404(
        TripRequest.objects.select_related("plan"),
        pk=trip_id,
    )


def get_trip_plan_by_cache_key(cache_key: str) -> TripPlan | None:
    return (
        TripPlan.objects
        .select_related("trip_request")
        .filter(cache_key=cache_key)
        .first()
    )


def get_recent_trip_requests(limit: int = 20) -> list[TripRequest]:
    return list(
        TripRequest.objects
        .select_related("plan")
        .order_by("-created_at")[:limit]
    )
