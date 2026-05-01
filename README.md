# ELD Trip Planner — Backend

Django REST API that plans FMCSA-compliant trucking trips. Give it three locations and current cycle hours — it returns a complete ELD plan with stop schedule, route geometry, and daily log data ready to render.

---

## What it does

1. Geocodes the three locations via Nominatim (OpenStreetMap)
2. Fetches driving routes from OSRM (free, no API key)
3. Runs a tick-based HOS simulation enforcing all 5 FMCSA rules
4. Builds per-day ELD log grid data (entries, totals, remarks)
5. Persists to PostgreSQL and caches the result in Redis for 24 hours

The same trip submitted twice returns the cached result immediately — no re-computation.

---

## FMCSA rules enforced

| Rule | CFR Reference |
|---|---|
| 11-hour driving limit per shift | § 395.3(a)(3) |
| 14-hour on-duty window | § 395.3(a)(2) |
| 10-hour rest requirement | § 395.3(a)(1) |
| 30-minute break after 8 cumulative hours | § 395.3(a)(3)(ii) |
| 70-hour/8-day cycle cap | § 395.3(b) |

---

## Requirements

- Docker and Docker Compose

That's it for running the API. No local Python setup needed.

For running tests locally: Python 3.12+ and pip.

---

## Running with Docker

```bash
cp .env.template .env
docker compose up --build
```

API is at `http://localhost:8000`.

The first startup runs migrations automatically. PostgreSQL and Redis must be healthy before the backend starts (healthchecks enforce this).

To stop:
```bash
docker compose down
```

To wipe the database too:
```bash
docker compose down -v
```

---

## Running tests locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/development.txt
pytest
```

Tests use SQLite in-memory and a dummy cache — no Docker, no Postgres, no Redis needed.

```
62 tests across 4 modules:
  hos/           — 12 tests (HOS algorithm accuracy)
  apps/routing/  — 11 tests (geocoding + routing clients)
  apps/eld/      — 14 tests (log builder + midnight splits)
  apps/trips/    — 25 tests (views + services + selectors)
```

---

## Environment variables

Copy `.env.template` to `.env` and fill in:

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | — | Django secret key. Use a long random string in prod |
| `DATABASE_URL` | Yes | postgres://eld_user:eld_pass@localhost:5432/eld_planner | Full Postgres connection URL |
| `REDIS_URL` | Yes | redis://localhost:6379/0 | Redis connection URL |
| `DEBUG` | No | False | Set `True` for development |
| `DJANGO_SETTINGS_MODULE` | No | config.settings.production | Use `config.settings.development` locally |
| `ALLOWED_HOSTS` | No | localhost,127.0.0.1 | Comma-separated list |
| `CORS_ALLOWED_ORIGINS` | No | http://localhost:3000 | Comma-separated allowed origins |

---

## API

### `GET /health/`

Returns `200 OK` when the server is up. Use this to check if the backend is reachable before making trip requests.

```json
{ "status": "ok" }
```

---

### `POST /api/trips/plan/`

Plans a trip and returns the full ELD log schedule.

**Request body:**

```json
{
  "current_location": "Dallas, TX",
  "pickup_location": "Fort Worth, TX",
  "dropoff_location": "Memphis, TN",
  "current_cycle_used_hours": 14.5
}
```

| Field | Type | Constraints |
|---|---|---|
| `current_location` | string | Any city/address Nominatim can geocode |
| `pickup_location` | string | Must differ from current and dropoff |
| `dropoff_location` | string | Must differ from current and pickup |
| `current_cycle_used_hours` | float | `0.0` – `70.0` |

**Success response — 201 Created (new plan) or 200 OK (cached):**

```json
{
  "data": {
    "trip_id": "3f8a2b1c-...",
    "total_distance_miles": 580.1,
    "total_driving_hours": 10.5,
    "total_days": 1,
    "cached": false,
    "route": {
      "type": "LineString",
      "coordinates": [[-96.797, 32.776], [-90.048, 35.149]]
    },
    "stops": [...],
    "eld_segments": [...],
    "daily_logs": [...]
  }
}
```

**Error responses:**

| Status | When |
|---|---|
| 400 Bad Request | Validation failed (missing fields, cycle hours out of range, duplicate locations) |
| 422 Unprocessable Entity | A location could not be geocoded |
| 503 Service Unavailable | OSRM routing API unavailable |

Error shape:
```json
{
  "data": null,
  "error": "Location not found: 'ZZZ NotARealPlace'"
}
```

---

## Response field reference

### `route`

GeoJSON `LineString` covering the full trip (current → pickup → dropoff). Feed directly to Leaflet's `L.geoJSON()` or react-leaflet's `<Polyline>`.

```
coordinates: [[lng, lat], [lng, lat], ...]   ← note: GeoJSON is [lng, lat] order
```

### `stops`

Ordered array of all stops on the route. Use this for map markers and the stop timeline.

```json
{
  "type": "fuel",
  "label": "Fuel Stop",
  "lat": 33.44,
  "lng": -94.05,
  "arrival_time_iso": "2024-01-15T14:30:00",
  "duration_minutes": 30,
  "location_name": "Texarkana, TX"
}
```

| `type` value | Meaning | Suggested marker color |
|---|---|---|
| `"current"` | Driver's starting location | `#10B981` (green) |
| `"pickup"` | Cargo pickup | `#F5A524` (amber) |
| `"dropoff"` | Cargo delivery | `#EF4444` (red) |
| `"fuel"` | Fuel stop (every ~1000 mi) | `#3B82F6` (blue) |
| `"rest_10hr"` | Mandatory 10-hour rest | `#8B5CF6` (purple) |
| `"break_30min"` | 30-minute break | `#6B7280` (gray) |

### `eld_segments`

Flat array of all duty-status segments for the entire trip, in chronological order. Used for the ELD canvas renderer — draw one horizontal line per segment.

```json
{
  "status": "driving",
  "start_time_iso": "2024-01-15T08:30:00",
  "end_time_iso": "2024-01-15T16:30:00",
  "location_name": "Dallas, TX",
  "is_stationary": false,
  "activity_label": null,
  "duration_hours": 8.0
}
```

| `status` value | ELD row | Line color |
|---|---|---|
| `"off_duty"` | Row 1 | `#6B7280` |
| `"sleeper_berth"` | Row 2 | `#8B5CF6` |
| `"driving"` | Row 3 | `#EF4444` |
| `"on_duty_not_driving"` | Row 4 | `#F5A524` |

`is_stationary: true` means the truck is stopped (pickup, dropoff, fuel). Draw the bracket below Row 4 for these segments.

### `daily_logs`

One entry per calendar day. Use for the ELD day tabs — each log maps to one paper log sheet.

```json
{
  "date": "2024-01-15",
  "day_number": 1,
  "from_location": "Dallas, TX",
  "to_location": "West Memphis, AR",
  "total_miles_today": 472,
  "entries": [...],
  "remarks": [...],
  "totals": {
    "off_duty": 9.5,
    "sleeper_berth": 0.0,
    "driving": 13.5,
    "on_duty_not_driving": 1.0
  }
}
```

`totals` always sums to exactly `24.0`.

**`entries`** — same structure as `eld_segments` but clipped to the day boundary (`start_hour` / `end_hour` are hours within the day, 0.0–24.0):

```json
{
  "status": "driving",
  "start_hour": 8.5,
  "end_hour": 16.5,
  "is_stationary": false,
  "activity_label": null,
  "location_name": "Dallas, TX"
}
```

**`remarks`** — status transition events used for the remarks band on the paper log:

```json
{
  "time_hour": 8.0,
  "location": "Dallas, TX",
  "activity": "Pre-trip / TIV"
}
```

`activity` is `null` for driving segments. Use `location` for driving entries instead.

---

## Project structure

```
server/
├── config/                Django project config
│   └── settings/
│       ├── base.py        shared settings
│       ├── development.py DEBUG=True, CORS open
│       ├── production.py  HTTPS headers, strict settings
│       └── test.py        SQLite, dummy cache
│
├── hos/                   HOS algorithm — zero Django dependencies
│   ├── constants.py       FMCSA regulation values
│   ├── types.py           Segment, Stop, DriverState dataclasses
│   └── engine.py          tick-based driving simulation
│
├── apps/
│   ├── common/            BaseModel (UUID pk + timestamps)
│   ├── routing/           Nominatim + OSRM HTTP clients
│   ├── eld/               segments → daily log grid conversion
│   └── trips/             models, API view, orchestration service
│
├── requirements/
│   ├── base.txt
│   ├── development.txt    + pytest
│   └── production.txt     + gunicorn
│
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh          runs migrations then starts server
└── pytest.ini
```

---

## Stack

| Layer | Technology |
|---|---|
| Framework | Django 5 + Django REST Framework |
| Database | PostgreSQL 16 |
| Cache | Redis 7 (24hr route cache) |
| HTTP client | httpx |
| Geocoding | Nominatim (OpenStreetMap) — free |
| Routing | OSRM public API — free, no key needed |
| Tests | pytest + pytest-django |
