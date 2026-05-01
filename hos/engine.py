from __future__ import annotations

import logging
from datetime import datetime, timedelta

from .constants import (
    AVERAGE_SPEED_MPH,
    BREAK_DURATION_HOURS,
    BREAK_TRIGGER_HOURS,
    DROPOFF_DURATION_HOURS,
    FUEL_DURATION_HOURS,
    FUEL_INTERVAL_MILES,
    MAX_CYCLE_HOURS,
    MAX_DRIVING_PER_SHIFT,
    MAX_WINDOW_HOURS,
    PICKUP_DURATION_HOURS,
    POST_TRIP_HOURS,
    PRE_TRIP_HOURS,
    REQUIRED_REST_HOURS,
    TICK_HOURS,
)
from .types import DriverState, DutyStatus, Segment, Stop, StopType

logger = logging.getLogger(__name__)


def plan_trip(
    current_lat:  float, current_lng:  float, current_name:  str,
    pickup_lat:   float, pickup_lng:   float, pickup_name:   str,
    dropoff_lat:  float, dropoff_lng:  float, dropoff_name:  str,
    cycle_used_hours: float,
    route_legs: list[dict],
    start_time: datetime | None = None,
) -> dict:
    if start_time is None:
        start_time = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        if start_time < datetime.now():
            start_time += timedelta(days=1)

    state = DriverState(
        current_time=start_time,
        current_lat=current_lat,
        current_lng=current_lng,
        current_location=current_name,
        cycle_hours_used=cycle_used_hours,
    )

    state.stops.append(Stop(
        type=StopType.CURRENT,
        label=f"Start — {current_name}",
        lat=current_lat,
        lng=current_lng,
        arrival_time=start_time,
        duration_minutes=0,
        location_name=current_name,
    ))

    _add_segment(state, DutyStatus.ON_DUTY_NOT_DRIVING, PRE_TRIP_HOURS,
                 is_stationary=True, activity="Pre-trip / TIV")

    _drive_leg(state, route_legs[0], dest_name=pickup_name,
               dest_lat=pickup_lat, dest_lng=pickup_lng)

    state.stops.append(Stop(
        type=StopType.PICKUP,
        label=f"Pickup — {pickup_name}",
        lat=pickup_lat,
        lng=pickup_lng,
        arrival_time=state.current_time,
        duration_minutes=int(PICKUP_DURATION_HOURS * 60),
        location_name=pickup_name,
    ))
    _add_segment(state, DutyStatus.ON_DUTY_NOT_DRIVING, PICKUP_DURATION_HOURS,
                 is_stationary=True, activity="Pickup")

    _drive_leg(state, route_legs[1], dest_name=dropoff_name,
               dest_lat=dropoff_lat, dest_lng=dropoff_lng)

    state.stops.append(Stop(
        type=StopType.DROPOFF,
        label=f"Dropoff — {dropoff_name}",
        lat=dropoff_lat,
        lng=dropoff_lng,
        arrival_time=state.current_time,
        duration_minutes=int(DROPOFF_DURATION_HOURS * 60),
        location_name=dropoff_name,
    ))
    _add_segment(state, DutyStatus.ON_DUTY_NOT_DRIVING, DROPOFF_DURATION_HOURS,
                 is_stationary=True, activity="Delivery")
    _add_segment(state, DutyStatus.ON_DUTY_NOT_DRIVING, POST_TRIP_HOURS,
                 is_stationary=True, activity="Post-trip / TIV")

    merged      = _merge_segments(state.segments)
    total_drive = sum(s.duration_hours for s in merged if s.status == DutyStatus.DRIVING)

    return {
        "total_distance_miles": round(sum(leg["distance_miles"] for leg in route_legs), 1),
        "total_driving_hours":  round(total_drive, 2),
        "stops":                [_serialize_stop(s)    for s in state.stops],
        "eld_segments":         [_serialize_segment(s) for s in merged],
        "_merged_segments":     merged,
    }


def _drive_leg(
    state: DriverState,
    leg: dict,
    dest_name: str,
    dest_lat: float,
    dest_lng: float,
) -> None:
    miles_remaining = leg["distance_miles"]
    waypoints       = leg.get("waypoints", [])
    wp_idx          = 0

    while miles_remaining > 0.01:
        if state.cycle_hours_used >= MAX_CYCLE_HOURS:
            logger.warning("Cycle hours exhausted at %s", state.current_location)
            break

        if state.shift_window_start is not None:
            window_elapsed = (state.current_time - state.shift_window_start).total_seconds() / 3600
            if window_elapsed >= MAX_WINDOW_HOURS:
                _insert_rest(state)
                continue

        if state.shift_drive_hours >= MAX_DRIVING_PER_SHIFT:
            _insert_rest(state)
            continue

        if state.cumulative_drive_since_break >= BREAK_TRIGGER_HOURS:
            _insert_break(state)
            continue

        if state.miles_since_fuel >= FUEL_INTERVAL_MILES:
            _insert_fuel(state)
            continue

        if state.shift_window_start is None:
            state.shift_window_start = state.current_time

        window_elapsed    = (state.current_time - state.shift_window_start).total_seconds() / 3600
        remaining_window  = MAX_WINDOW_HOURS - window_elapsed
        remaining_shift   = MAX_DRIVING_PER_SHIFT - state.shift_drive_hours
        remaining_break   = BREAK_TRIGGER_HOURS - state.cumulative_drive_since_break
        max_drive_hours   = max(min(TICK_HOURS, remaining_shift, remaining_break, remaining_window), 0)

        miles = min(AVERAGE_SPEED_MPH * max_drive_hours, miles_remaining)
        hours = miles / AVERAGE_SPEED_MPH

        _add_segment(state, DutyStatus.DRIVING, hours)
        state.shift_drive_hours            += hours
        state.cumulative_drive_since_break += hours
        state.miles_driven                 += miles
        state.miles_since_fuel             += miles
        miles_remaining                    -= miles

        while wp_idx < len(waypoints) and waypoints[wp_idx]["miles_from_start"] <= state.miles_driven:
            wp = waypoints[wp_idx]
            state.current_lat      = wp["lat"]
            state.current_lng      = wp["lng"]
            state.current_location = wp.get("name", state.current_location)
            wp_idx += 1

    state.current_lat      = dest_lat
    state.current_lng      = dest_lng
    state.current_location = dest_name


def _add_segment(
    state: DriverState,
    status: DutyStatus,
    hours: float,
    is_stationary: bool = False,
    activity: str | None = None,
) -> None:
    start = state.current_time
    end   = start + timedelta(hours=hours)
    state.segments.append(Segment(
        status=status,
        start_time=start,
        end_time=end,
        location_name=state.current_location,
        is_stationary=is_stationary,
        activity_label=activity,
    ))
    state.current_time = end
    if status in (DutyStatus.DRIVING, DutyStatus.ON_DUTY_NOT_DRIVING):
        state.cycle_hours_used += hours


def _insert_rest(state: DriverState) -> None:
    state.stops.append(Stop(
        type=StopType.REST,
        label="10-Hour Rest",
        lat=state.current_lat,
        lng=state.current_lng,
        arrival_time=state.current_time,
        duration_minutes=int(REQUIRED_REST_HOURS * 60),
        location_name=state.current_location,
    ))
    _add_segment(state, DutyStatus.OFF_DUTY, REQUIRED_REST_HOURS, activity="10-hr rest")
    state.shift_drive_hours            = 0.0
    state.shift_window_start           = None
    state.cumulative_drive_since_break = 0.0


def _insert_break(state: DriverState) -> None:
    state.stops.append(Stop(
        type=StopType.BREAK,
        label="30-Min Break",
        lat=state.current_lat,
        lng=state.current_lng,
        arrival_time=state.current_time,
        duration_minutes=int(BREAK_DURATION_HOURS * 60),
        location_name=state.current_location,
    ))
    _add_segment(state, DutyStatus.OFF_DUTY, BREAK_DURATION_HOURS, activity="30-min break")
    # § 395.3(a)(3)(ii): break resets cumulative drive only — shift hours and window keep counting
    state.cumulative_drive_since_break = 0.0


def _insert_fuel(state: DriverState) -> None:
    state.stops.append(Stop(
        type=StopType.FUEL,
        label="Fuel Stop",
        lat=state.current_lat,
        lng=state.current_lng,
        arrival_time=state.current_time,
        duration_minutes=int(FUEL_DURATION_HOURS * 60),
        location_name=state.current_location,
    ))
    _add_segment(state, DutyStatus.ON_DUTY_NOT_DRIVING, FUEL_DURATION_HOURS,
                 is_stationary=True, activity="Fuel stop")
    state.miles_since_fuel = 0.0


def _merge_segments(segs: list[Segment]) -> list[Segment]:
    if not segs:
        return []
    merged = [segs[0]]
    for seg in segs[1:]:
        prev = merged[-1]
        if prev.status == seg.status and prev.activity_label == seg.activity_label:
            merged[-1] = Segment(
                status=prev.status,
                start_time=prev.start_time,
                end_time=seg.end_time,
                location_name=prev.location_name,
                is_stationary=prev.is_stationary,
                activity_label=prev.activity_label,
            )
        else:
            merged.append(seg)
    return merged


def _serialize_stop(s: Stop) -> dict:
    return {
        "type":             s.type.value,
        "label":            s.label,
        "lat":              s.lat,
        "lng":              s.lng,
        "arrival_time_iso": s.arrival_time.isoformat(),
        "duration_minutes": s.duration_minutes,
        "location_name":    s.location_name,
    }


def _serialize_segment(s: Segment) -> dict:
    return {
        "status":         s.status.value,
        "start_time_iso": s.start_time.isoformat(),
        "end_time_iso":   s.end_time.isoformat(),
        "location_name":  s.location_name,
        "is_stationary":  s.is_stationary,
        "activity_label": s.activity_label,
        "duration_hours": round(s.duration_hours, 3),
    }
