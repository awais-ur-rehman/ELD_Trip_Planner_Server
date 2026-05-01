# ELD Trip Planner — Backend

Django REST API for FMCSA-compliant trip planning. Takes a current location, pickup, and dropoff — returns a full ELD log plan with rest stops, fuel stops, and 30-min breaks already figured out.

## What it does

You give it three locations and how many cycle hours the driver has already used. It geocodes them, fetches the route from OSRM, runs the HOS simulation, and returns everything the frontend needs: the route geometry, a list of stops (with timestamps and coordinates), and per-day ELD log data ready to render on canvas.

All HOS rules are from 49 CFR Part 395:
- 11-hour driving limit per shift
- 14-hour on-duty window
- 10-hour rest requirement
- 30-minute break after 8 cumulative hours
- 70-hour/8-day cycle cap

Routes are cached in Redis for 24 hours. Same trip with same cycle hours will never re-compute.

## Project structure

```
server/
├── config/              Django settings (base / dev / prod split)
├── hos/                 HOS algorithm — pure Python, no Django deps
│   ├── constants.py     FMCSA regulation values
│   ├── types.py         Dataclasses: Segment, Stop, DriverState
│   └── engine.py        Tick-based driving simulation
├── apps/
│   ├── common/          Base model, shared exceptions
│   ├── routing/         Nominatim + OSRM HTTP clients
│   ├── eld/             Segments → daily log grid conversion
│   └── trips/           Models, API views, orchestration
└── requirements/        base / development / production split
```

## Running locally

You need Docker. That's it.

```bash
cp .env.template .env
# fill in .env (see below)
docker compose up --build
```

API runs at `http://localhost:8000`.

## Running tests

```bash
pip install -r requirements/development.txt
pytest
```

HOS engine tests run without Django — no database, no Redis needed.

## Environment variables

```
DJANGO_SETTINGS_MODULE=config.settings.development
SECRET_KEY=your-secret-key
DEBUG=True
DATABASE_URL=postgres://eld_user:eld_pass@localhost:5432/eld_planner
REDIS_URL=redis://localhost:6379/0
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

## API

### `POST /api/trips/plan/`

Request:
```json
{
  "current_location": "Dallas, TX",
  "pickup_location": "Fort Worth, TX",
  "dropoff_location": "Memphis, TN",
  "current_cycle_used_hours": 14.5
}
```

Response:
```json
{
  "data": {
    "trip_id": "uuid",
    "total_distance_miles": 580.1,
    "total_driving_hours": 10.5,
    "total_days": 1,
    "cached": false,
    "route": { "type": "LineString", "coordinates": [[...]] },
    "stops": [...],
    "eld_segments": [...],
    "daily_logs": [...]
  }
}
```

Errors come back as `{ "data": null, "error": "..." }` with the appropriate HTTP status.

## Stack

- Django 5 + Django REST Framework
- PostgreSQL 16
- Redis 7
- httpx for external API calls (OSRM, Nominatim)
- pytest for tests
