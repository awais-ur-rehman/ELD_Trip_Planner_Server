import uuid

import pytest

from apps.trips.models import TripPlan, TripRequest


def _make_trip_request(**kwargs) -> TripRequest:
    defaults = dict(
        current_location="Dallas, TX",   current_lat=32.77, current_lng=-96.79,
        pickup_location="Fort Worth, TX", pickup_lat=32.75,  pickup_lng=-97.33,
        dropoff_location="Memphis, TN",  dropoff_lat=35.14, dropoff_lng=-90.04,
        current_cycle_used_hours=14.5,
    )
    defaults.update(kwargs)
    return TripRequest.objects.create(**defaults)


def _make_trip_plan(trip_request: TripRequest, **kwargs) -> TripPlan:
    defaults = dict(
        trip_request=trip_request,
        total_distance_miles=486.0,
        total_driving_hours=8.8,
        total_days=1,
        route_geometry={"type": "LineString", "coordinates": []},
        stops=[],
        eld_segments=[],
        daily_logs=[],
        cache_key="trip:abc123",
    )
    defaults.update(kwargs)
    return TripPlan.objects.create(**defaults)


# ── get_trip_request_by_id ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_trip_request_by_id_returns_object():
    from apps.trips.selectors import get_trip_request_by_id

    req = _make_trip_request()
    result = get_trip_request_by_id(req.pk)

    assert result.pk == req.pk
    assert result.current_location == "Dallas, TX"


@pytest.mark.django_db
def test_get_trip_request_by_id_404_on_missing():
    from django.http import Http404
    from apps.trips.selectors import get_trip_request_by_id

    with pytest.raises(Http404):
        get_trip_request_by_id(uuid.uuid4())


@pytest.mark.django_db
def test_get_trip_request_selects_related_plan():
    from apps.trips.selectors import get_trip_request_by_id

    req  = _make_trip_request()
    plan = _make_trip_plan(req)

    result = get_trip_request_by_id(req.pk)
    assert result.plan.pk == plan.pk


# ── get_trip_plan_by_cache_key ───────────────────────────────────────────────

@pytest.mark.django_db
def test_get_trip_plan_by_cache_key_returns_match():
    from apps.trips.selectors import get_trip_plan_by_cache_key

    req  = _make_trip_request()
    plan = _make_trip_plan(req, cache_key="trip:xyz999")

    result = get_trip_plan_by_cache_key("trip:xyz999")
    assert result is not None
    assert result.pk == plan.pk


@pytest.mark.django_db
def test_get_trip_plan_by_cache_key_returns_none_on_miss():
    from apps.trips.selectors import get_trip_plan_by_cache_key

    result = get_trip_plan_by_cache_key("trip:doesnotexist")
    assert result is None


# ── get_recent_trip_requests ─────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_recent_trip_requests_returns_ordered_list():
    from apps.trips.selectors import get_recent_trip_requests

    for _ in range(3):
        _make_trip_request()

    results = get_recent_trip_requests(limit=10)

    assert len(results) == 3
    created_times = [r.created_at for r in results]
    assert created_times == sorted(created_times, reverse=True)


@pytest.mark.django_db
def test_get_recent_trip_requests_respects_limit():
    from apps.trips.selectors import get_recent_trip_requests

    for _ in range(5):
        _make_trip_request()

    results = get_recent_trip_requests(limit=2)
    assert len(results) == 2
