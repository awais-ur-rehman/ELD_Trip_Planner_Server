from datetime import datetime

import pytest

from hos.constants import (
    AVERAGE_SPEED_MPH,
    BREAK_TRIGGER_HOURS,
    FUEL_INTERVAL_MILES,
    MAX_CYCLE_HOURS,
    MAX_DRIVING_PER_SHIFT,
    MAX_WINDOW_HOURS,
    REQUIRED_REST_HOURS,
)
from hos.engine import plan_trip
from hos.types import DutyStatus


START = datetime(2024, 1, 15, 8, 0, 0)


def _make_leg(miles: float) -> dict:
    return {"distance_miles": miles, "waypoints": []}


def _run(leg1_miles: float, leg2_miles: float, cycle_used: float = 0.0) -> dict:
    return plan_trip(
        current_lat=32.77,  current_lng=-96.79,  current_name="Dallas, TX",
        pickup_lat=32.75,   pickup_lng=-97.33,   pickup_name="Fort Worth, TX",
        dropoff_lat=35.15,  dropoff_lng=-90.04,  dropoff_name="Memphis, TN",
        cycle_used_hours=cycle_used,
        route_legs=[_make_leg(leg1_miles), _make_leg(leg2_miles)],
        start_time=START,
    )


def _driving_segments(result: dict) -> list[dict]:
    return [s for s in result["eld_segments"] if s["status"] == DutyStatus.DRIVING]


def _shift_groups(result: dict) -> list[list[dict]]:
    groups: list[list[dict]] = []
    current: list[dict] = []
    for seg in result["eld_segments"]:
        if seg["status"] == DutyStatus.OFF_DUTY and seg["activity_label"] == "10-hr rest":
            if current:
                groups.append(current)
            current = []
        else:
            current.append(seg)
    if current:
        groups.append(current)
    return groups


def test_11hr_driving_limit_enforced():
    result = _run(leg1_miles=50, leg2_miles=1500)
    for group in _shift_groups(result):
        drive_hours = sum(
            s["duration_hours"] for s in group if s["status"] == DutyStatus.DRIVING
        )
        assert drive_hours <= MAX_DRIVING_PER_SHIFT + 0.01


def test_14hr_window_triggers_rest():
    result = _run(leg1_miles=50, leg2_miles=1500)
    rest_stops = [s for s in result["stops"] if s["type"] == "rest_10hr"]
    assert len(rest_stops) >= 1


def test_rest_duration_exactly_10_hours():
    result = _run(leg1_miles=50, leg2_miles=1500)
    rest_segs = [
        s for s in result["eld_segments"]
        if s["status"] == DutyStatus.OFF_DUTY and s["activity_label"] == "10-hr rest"
    ]
    for seg in rest_segs:
        assert abs(seg["duration_hours"] - REQUIRED_REST_HOURS) < 0.01


def test_30min_break_resets_only_break_counter():
    result = _run(leg1_miles=50, leg2_miles=1500)
    segs = result["eld_segments"]

    for i, seg in enumerate(segs):
        if seg["status"] == DutyStatus.OFF_DUTY and seg["activity_label"] == "30-min break":
            post_break_drive = 0.0
            for j in range(i + 1, len(segs)):
                if segs[j]["status"] == DutyStatus.DRIVING:
                    post_break_drive += segs[j]["duration_hours"]
                elif segs[j]["activity_label"] in ("30-min break", "10-hr rest"):
                    break
            assert post_break_drive <= BREAK_TRIGGER_HOURS + 0.01


def test_break_does_not_reset_window():
    result = _run(leg1_miles=50, leg2_miles=700)
    segs = result["eld_segments"]

    for i, seg in enumerate(segs):
        if seg["status"] == DutyStatus.OFF_DUTY and seg["activity_label"] == "30-min break":
            window_start_idx = next(
                (j for j in range(i - 1, -1, -1) if segs[j]["activity_label"] != "30-min break"),
                None,
            )
            if window_start_idx is not None:
                window_start = datetime.fromisoformat(segs[0]["start_time_iso"])
                break_end    = datetime.fromisoformat(seg["end_time_iso"])
                elapsed = (break_end - window_start).total_seconds() / 3600
                assert elapsed < MAX_WINDOW_HOURS + 0.5


def test_fuel_stop_every_1000_miles():
    result = _run(leg1_miles=50, leg2_miles=2500)
    fuel_stops = [s for s in result["stops"] if s["type"] == "fuel"]
    total_miles = result["total_distance_miles"]
    expected_min = int(total_miles / FUEL_INTERVAL_MILES)
    assert len(fuel_stops) >= expected_min


def test_cycle_hours_respected():
    result = _run(leg1_miles=50, leg2_miles=800, cycle_used=65.0)
    drive_segs = _driving_segments(result)
    total_new_drive = sum(s["duration_hours"] for s in drive_segs)
    assert total_new_drive <= (MAX_CYCLE_HOURS - 65.0) + 0.1


def test_short_trip_no_rest_needed():
    result = _run(leg1_miles=30, leg2_miles=150)
    rest_stops = [s for s in result["stops"] if s["type"] == "rest_10hr"]
    assert len(rest_stops) == 0


def test_multi_day_trip_generates_multiple_log_days():
    result = _run(leg1_miles=50, leg2_miles=1200)
    rest_segs = [
        s for s in result["eld_segments"]
        if s["status"] == DutyStatus.OFF_DUTY and s["activity_label"] == "10-hr rest"
    ]
    assert len(rest_segs) >= 1


def test_stops_ordered_chronologically():
    result = _run(leg1_miles=50, leg2_miles=800)
    stops = result["stops"]
    times = [datetime.fromisoformat(s["arrival_time_iso"]) for s in stops]
    assert times == sorted(times)


def test_total_distance_is_sum_of_legs():
    result = _run(leg1_miles=123.4, leg2_miles=456.7)
    assert abs(result["total_distance_miles"] - 580.1) < 0.2


def test_driving_hours_match_segments():
    result = _run(leg1_miles=50, leg2_miles=400)
    drive_segs = _driving_segments(result)
    seg_total = sum(s["duration_hours"] for s in drive_segs)
    assert abs(result["total_driving_hours"] - seg_total) < 0.01
