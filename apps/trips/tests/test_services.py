from unittest.mock import MagicMock, patch

import pytest

GEOCODE_RESULTS = [
    (32.77, -96.79, "Dallas, TX, USA"),
    (32.75, -97.33, "Fort Worth, TX, USA"),
    (35.14, -90.04, "Memphis, TN, USA"),
]

LEG1 = {"distance_miles": 33.0,  "duration_hours": 0.6, "geometry": {"type": "LineString", "coordinates": []}}
LEG2 = {"distance_miles": 453.0, "duration_hours": 8.2, "geometry": {"type": "LineString", "coordinates": []}}
FULL = {"distance_miles": 486.0, "duration_hours": 8.8, "geometry": {"type": "LineString", "coordinates": [[-96.79, 32.77], [-90.04, 35.14]]}}

VALID_INPUT = {
    "current_location":         "Dallas, TX",
    "pickup_location":          "Fort Worth, TX",
    "dropoff_location":         "Memphis, TN",
    "current_cycle_used_hours": 14.5,
}


def _mock_geocode(address: str):
    mapping = {
        "Dallas, TX":    GEOCODE_RESULTS[0],
        "Fort Worth, TX": GEOCODE_RESULTS[1],
        "Memphis, TN":   GEOCODE_RESULTS[2],
    }
    return mapping[address]


def _mock_get_route(waypoints):
    if len(waypoints) == 3:
        return FULL
    first = waypoints[0]
    if first == (32.77, -96.79):
        return LEG1
    return LEG2


@pytest.fixture
def mock_externals():
    with (
        patch("apps.trips.services.geocode_address", side_effect=_mock_geocode),
        patch("apps.trips.services.get_route",       side_effect=_mock_get_route),
        patch("apps.trips.services.get_cached_plan", return_value=None),
        patch("apps.trips.services.set_cached_plan"),
    ):
        yield


# ── Core flow ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_service_returns_plan_dict(mock_externals):
    from apps.trips.services import plan_trip_service
    result = plan_trip_service(VALID_INPUT)

    assert "trip_id" in result
    assert "route" in result
    assert "stops" in result
    assert "eld_segments" in result
    assert "daily_logs" in result
    assert result["cached"] is False


@pytest.mark.django_db
def test_service_creates_db_records(mock_externals):
    from apps.trips.models import TripPlan, TripRequest
    from apps.trips.services import plan_trip_service

    plan_trip_service(VALID_INPUT)

    assert TripRequest.objects.count() == 1
    assert TripPlan.objects.count() == 1


@pytest.mark.django_db
def test_service_db_record_stores_correct_locations(mock_externals):
    from apps.trips.models import TripRequest
    from apps.trips.services import plan_trip_service

    plan_trip_service(VALID_INPUT)

    req = TripRequest.objects.first()
    assert req.current_location == "Dallas, TX"
    assert req.pickup_location  == "Fort Worth, TX"
    assert req.dropoff_location == "Memphis, TN"


@pytest.mark.django_db
def test_service_total_days_matches_daily_logs(mock_externals):
    from apps.trips.services import plan_trip_service
    result = plan_trip_service(VALID_INPUT)

    assert result["total_days"] == len(result["daily_logs"])


@pytest.mark.django_db
def test_service_daily_miles_distributed(mock_externals):
    from apps.trips.services import plan_trip_service
    result = plan_trip_service(VALID_INPUT)

    total = sum(log["total_miles_today"] for log in result["daily_logs"])
    assert abs(total - result["total_distance_miles"]) <= len(result["daily_logs"])


# ── Cache hit ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_cache_hit_skips_routing_and_db():
    cached_plan = {**{"trip_id": "cached-id", "cached": True}}

    with (
        patch("apps.trips.services.geocode_address", side_effect=_mock_geocode),
        patch("apps.trips.services.get_route")         as mock_route,
        patch("apps.trips.services.get_cached_plan",   return_value=cached_plan),
        patch("apps.trips.services.set_cached_plan")   as mock_set,
    ):
        from apps.trips.services import plan_trip_service
        result = plan_trip_service(VALID_INPUT)

    mock_route.assert_not_called()
    mock_set.assert_not_called()
    assert result["cached"] is True
    assert result["trip_id"] == "cached-id"


# ── External errors propagate ────────────────────────────────────────────────

@pytest.mark.django_db
def test_geocoding_error_propagates():
    from apps.routing.exceptions import GeocodingError
    from apps.trips.services import plan_trip_service

    with patch("apps.trips.services.geocode_address", side_effect=GeocodingError("not found")):
        with pytest.raises(GeocodingError):
            plan_trip_service(VALID_INPUT)


@pytest.mark.django_db
def test_routing_error_propagates():
    from apps.routing.exceptions import RoutingError
    from apps.trips.services import plan_trip_service

    with (
        patch("apps.trips.services.geocode_address", side_effect=_mock_geocode),
        patch("apps.trips.services.get_cached_plan", return_value=None),
        patch("apps.trips.services.get_route",       side_effect=RoutingError("OSRM down")),
    ):
        with pytest.raises(RoutingError):
            plan_trip_service(VALID_INPUT)
