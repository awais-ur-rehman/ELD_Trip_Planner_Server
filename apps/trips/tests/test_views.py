from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

PLAN_URL = "/api/trips/plan/"

VALID_PAYLOAD = {
    "current_location":         "Dallas, TX",
    "pickup_location":          "Fort Worth, TX",
    "dropoff_location":         "Memphis, TN",
    "current_cycle_used_hours": 14.5,
}

MOCK_PLAN = {
    "trip_id":             "abc-123",
    "total_distance_miles": 580.1,
    "total_driving_hours":  10.5,
    "total_days":           1,
    "cached":               False,
    "route":                {"type": "LineString", "coordinates": []},
    "stops":                [],
    "eld_segments":         [],
    "daily_logs":           [],
}


@pytest.fixture
def client():
    return APIClient()


# ── Happy paths ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
@patch("apps.trips.views.plan_trip_service", return_value={**MOCK_PLAN, "cached": False})
def test_post_valid_returns_201(mock_service, client):
    resp = client.post(PLAN_URL, VALID_PAYLOAD, format="json")
    assert resp.status_code == 201
    assert resp.data["data"]["trip_id"] == "abc-123"


@pytest.mark.django_db
@patch("apps.trips.views.plan_trip_service", return_value={**MOCK_PLAN, "cached": True})
def test_cached_response_returns_200(mock_service, client):
    resp = client.post(PLAN_URL, VALID_PAYLOAD, format="json")
    assert resp.status_code == 200
    assert resp.data["data"]["cached"] is True


@pytest.mark.django_db
@patch("apps.trips.views.plan_trip_service", return_value={**MOCK_PLAN, "cached": False})
def test_response_wrapped_in_data_key(mock_service, client):
    resp = client.post(PLAN_URL, VALID_PAYLOAD, format="json")
    assert "data" in resp.data
    assert resp.data["data"] is not None


# ── Validation errors ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_missing_field_returns_400(client):
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "pickup_location"}
    resp = client.post(PLAN_URL, payload, format="json")
    assert resp.status_code == 400
    assert "error" in resp.data


@pytest.mark.django_db
def test_cycle_hours_above_70_returns_400(client):
    resp = client.post(
        PLAN_URL, {**VALID_PAYLOAD, "current_cycle_used_hours": 71.0}, format="json"
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_cycle_hours_negative_returns_400(client):
    resp = client.post(
        PLAN_URL, {**VALID_PAYLOAD, "current_cycle_used_hours": -1.0}, format="json"
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_duplicate_locations_returns_400(client):
    resp = client.post(
        PLAN_URL,
        {**VALID_PAYLOAD, "pickup_location": "Dallas, TX"},
        format="json",
    )
    assert resp.status_code == 400


# ── External service errors ──────────────────────────────────────────────────

@pytest.mark.django_db
@patch("apps.trips.views.plan_trip_service")
def test_geocoding_error_returns_422(mock_service, client):
    from apps.routing.exceptions import GeocodingError
    mock_service.side_effect = GeocodingError("Location not found: 'ZZZ'")

    resp = client.post(PLAN_URL, VALID_PAYLOAD, format="json")
    assert resp.status_code == 422
    assert "error" in resp.data


@pytest.mark.django_db
@patch("apps.trips.views.plan_trip_service")
def test_routing_error_returns_503(mock_service, client):
    from apps.routing.exceptions import RoutingError
    mock_service.side_effect = RoutingError("OSRM returned no valid route")

    resp = client.post(PLAN_URL, VALID_PAYLOAD, format="json")
    assert resp.status_code == 503
    assert "error" in resp.data


# ── Method not allowed ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_not_allowed(client):
    resp = client.get(PLAN_URL)
    assert resp.status_code == 405
