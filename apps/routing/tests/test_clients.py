from unittest.mock import MagicMock, patch

import pytest

from apps.routing.clients import geocode_address, get_route, get_route_with_legs
from apps.routing.exceptions import GeocodingError, RoutingError


NOMINATIM_HIT = [
    {
        "lat": "32.7767",
        "lon": "-96.7970",
        "display_name": "Dallas, Dallas County, Texas, United States",
    }
]

OSRM_HIT = {
    "code": "Ok",
    "routes": [
        {
            "distance": 933840.0,  # metres → 580.1 miles
            "duration": 61200.0,   # seconds → 17 hours
            "geometry": {
                "type": "LineString",
                "coordinates": [[-96.797, 32.776], [-90.048, 35.149]],
            },
            "legs": [],
        }
    ],
}

OSRM_HIT_WITH_LEGS = {
    "code": "Ok",
    "routes": [
        {
            "distance": 986840.0,
            "duration": 56880.0,
            "geometry": {
                "type": "LineString",
                "coordinates": [[-96.79, 32.77], [-97.33, 32.75], [-90.04, 35.14]],
            },
            "legs": [
                {"distance": 53108.0, "duration": 2160.0},   # ~33 mi / ~0.6 hr
                {"distance": 729025.0, "duration": 29520.0},  # ~453 mi / ~8.2 hr
            ],
        }
    ],
}


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# ── geocode_address ──────────────────────────────────────────────────────────

@patch("apps.routing.clients.httpx.Client")
def test_geocode_returns_lat_lng_name(mock_client_cls):
    mock_client_cls.return_value.__enter__.return_value.get.return_value = (
        _mock_response(NOMINATIM_HIT)
    )

    lat, lng, name = geocode_address("Dallas, TX")

    assert lat == pytest.approx(32.7767)
    assert lng == pytest.approx(-96.797)
    assert "Dallas" in name


@patch("apps.routing.clients.httpx.Client")
def test_geocode_raises_on_empty_response(mock_client_cls):
    mock_client_cls.return_value.__enter__.return_value.get.return_value = (
        _mock_response([])
    )

    with pytest.raises(GeocodingError, match="Location not found"):
        geocode_address("ZZZ NotARealPlace 99999")


@patch("apps.routing.clients.httpx.Client")
def test_geocode_raises_on_http_error(mock_client_cls):
    import httpx as _httpx

    mock_resp = _mock_response({}, status_code=500)
    mock_resp.raise_for_status.side_effect = _httpx.HTTPStatusError(
        "500", request=MagicMock(), response=mock_resp
    )
    mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp

    with pytest.raises(GeocodingError, match="Geocoding request failed"):
        geocode_address("Dallas, TX")


# ── get_route ────────────────────────────────────────────────────────────────

@patch("apps.routing.clients.httpx.Client")
def test_get_route_returns_distance_duration_geometry(mock_client_cls):
    mock_client_cls.return_value.__enter__.return_value.get.return_value = (
        _mock_response(OSRM_HIT)
    )

    result = get_route([(32.77, -96.79), (35.14, -90.04)])

    assert result["distance_miles"] == pytest.approx(580.1, abs=0.5)
    assert result["duration_hours"] == pytest.approx(17.0, abs=0.1)
    assert result["geometry"]["type"] == "LineString"
    assert isinstance(result["geometry"]["coordinates"], list)


@patch("apps.routing.clients.httpx.Client")
def test_get_route_coord_order_is_lng_lat(mock_client_cls):
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return _mock_response(OSRM_HIT)

    mock_client_cls.return_value.__enter__.return_value.get.side_effect = fake_get

    get_route([(32.77, -96.79), (35.14, -90.04)])

    assert "-96.79,32.77" in captured["url"]
    assert "-90.04,35.14" in captured["url"]


@patch("apps.routing.clients.httpx.Client")
def test_get_route_raises_on_osrm_error_code(mock_client_cls):
    mock_client_cls.return_value.__enter__.return_value.get.return_value = (
        _mock_response({"code": "NoRoute", "routes": []})
    )

    with pytest.raises(RoutingError, match="NoRoute"):
        get_route([(32.77, -96.79), (35.14, -90.04)])


@patch("apps.routing.clients.httpx.Client")
def test_get_route_raises_on_empty_routes(mock_client_cls):
    mock_client_cls.return_value.__enter__.return_value.get.return_value = (
        _mock_response({"code": "Ok", "routes": []})
    )

    with pytest.raises(RoutingError):
        get_route([(32.77, -96.79), (35.14, -90.04)])


@patch("apps.routing.clients.httpx.Client")
def test_get_route_raises_on_http_error(mock_client_cls):
    import httpx as _httpx

    mock_resp = _mock_response({}, status_code=503)
    mock_resp.raise_for_status.side_effect = _httpx.HTTPStatusError(
        "503", request=MagicMock(), response=mock_resp
    )
    mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp

    with pytest.raises(RoutingError, match="Routing request failed"):
        get_route([(32.77, -96.79), (35.14, -90.04)])


@patch("apps.routing.clients.httpx.Client")
def test_get_route_three_waypoints(mock_client_cls):
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return _mock_response(OSRM_HIT)

    mock_client_cls.return_value.__enter__.return_value.get.side_effect = fake_get

    get_route([(32.77, -96.79), (32.75, -97.33), (35.14, -90.04)])

    assert captured["url"].count(";") == 2


# ── get_route_with_legs ──────────────────────────────────────────────────────

@patch("apps.routing.clients.httpx.Client")
def test_get_route_with_legs_returns_geometry_and_legs(mock_client_cls):
    mock_client_cls.return_value.__enter__.return_value.get.return_value = (
        _mock_response(OSRM_HIT_WITH_LEGS)
    )

    result = get_route_with_legs([(32.77, -96.79), (32.75, -97.33), (35.14, -90.04)])

    assert result["geometry"]["type"] == "LineString"
    assert len(result["legs"]) == 2
    assert result["legs"][0]["distance_miles"] == pytest.approx(33.0, abs=0.5)
    assert result["legs"][1]["distance_miles"] == pytest.approx(453.0, abs=0.5)


@patch("apps.routing.clients.httpx.Client")
def test_get_route_with_legs_raises_on_osrm_error(mock_client_cls):
    mock_client_cls.return_value.__enter__.return_value.get.return_value = (
        _mock_response({"code": "NoRoute", "routes": []})
    )

    with pytest.raises(RoutingError, match="NoRoute"):
        get_route_with_legs([(32.77, -96.79), (32.75, -97.33), (35.14, -90.04)])
