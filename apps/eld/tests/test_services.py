from datetime import datetime, timedelta

import pytest

from apps.eld.services import build_daily_logs
from hos.engine import plan_trip
from hos.types import DutyStatus, Segment


def _seg(status: DutyStatus, start: datetime, hours: float, **kwargs) -> Segment:
    return Segment(
        status=status,
        start_time=start,
        end_time=start + timedelta(hours=hours),
        location_name=kwargs.get("location", "Somewhere, TX"),
        is_stationary=kwargs.get("is_stationary", False),
        activity_label=kwargs.get("activity", None),
    )


def _engine_segments(leg1_miles: float, leg2_miles: float, cycle: float = 0.0) -> list[Segment]:
    result = plan_trip(
        current_lat=32.77, current_lng=-96.79, current_name="Dallas, TX",
        pickup_lat=32.75,  pickup_lng=-97.33,  pickup_name="Fort Worth, TX",
        dropoff_lat=35.15, dropoff_lng=-90.04, dropoff_name="Memphis, TN",
        cycle_used_hours=cycle,
        route_legs=[
            {"distance_miles": leg1_miles, "waypoints": []},
            {"distance_miles": leg2_miles, "waypoints": []},
        ],
        start_time=datetime(2024, 1, 15, 8, 0, 0),
    )
    return result["_merged_segments"]


# ── Structure ────────────────────────────────────────────────────────────────

def test_empty_segments_returns_empty():
    assert build_daily_logs([]) == []


def test_single_day_trip_returns_one_log():
    segs = _engine_segments(30, 150)
    logs = build_daily_logs(segs)
    assert len(logs) == 1


def test_multi_day_trip_returns_multiple_logs():
    segs = _engine_segments(50, 1200)
    logs = build_daily_logs(segs)
    assert len(logs) >= 2


def test_day_numbers_are_sequential():
    segs = _engine_segments(50, 1200)
    logs = build_daily_logs(segs)
    numbers = [log["day_number"] for log in logs]
    assert numbers == list(range(1, len(logs) + 1))


def test_dates_are_consecutive():
    segs = _engine_segments(50, 1200)
    logs = build_daily_logs(segs)
    for i in range(1, len(logs)):
        prev = datetime.fromisoformat(logs[i - 1]["date"]).date()
        curr = datetime.fromisoformat(logs[i]["date"]).date()
        assert (curr - prev).days == 1


# ── Totals always sum to 24 ──────────────────────────────────────────────────

def test_each_day_totals_sum_to_24():
    segs = _engine_segments(50, 1200)
    logs = build_daily_logs(segs)
    for log in logs:
        total = sum(log["totals"].values())
        assert abs(total - 24.0) < 0.01, f"Day {log['day_number']} totals = {total}"


def test_short_trip_totals_sum_to_24():
    segs = _engine_segments(30, 150)
    logs = build_daily_logs(segs)
    for log in logs:
        total = sum(log["totals"].values())
        assert abs(total - 24.0) < 0.01


def test_totals_keys_are_all_four_statuses():
    segs = _engine_segments(30, 150)
    logs = build_daily_logs(segs)
    expected = {"off_duty", "sleeper_berth", "driving", "on_duty_not_driving"}
    for log in logs:
        assert set(log["totals"].keys()) == expected


# ── Midnight split ───────────────────────────────────────────────────────────

def test_segment_crossing_midnight_is_split():
    # 4-hour driving segment starting at 23:00 — crosses midnight
    night_start = datetime(2024, 1, 15, 23, 0, 0)
    segs = [_seg(DutyStatus.DRIVING, night_start, 4.0)]
    logs = build_daily_logs(segs)

    assert len(logs) == 2

    day1_drive = logs[0]["totals"]["driving"]
    day2_drive = logs[1]["totals"]["driving"]

    assert abs(day1_drive - 1.0) < 0.01   # 23:00 → 00:00
    assert abs(day2_drive - 3.0) < 0.01   # 00:00 → 03:00


def test_midnight_split_totals_still_24_each():
    night_start = datetime(2024, 1, 15, 22, 0, 0)
    segs = [_seg(DutyStatus.DRIVING, night_start, 6.0)]
    logs = build_daily_logs(segs)
    for log in logs:
        assert abs(sum(log["totals"].values()) - 24.0) < 0.01


# ── Remarks ──────────────────────────────────────────────────────────────────

def test_remarks_generated_at_status_transitions():
    start = datetime(2024, 1, 15, 8, 0, 0)
    segs = [
        _seg(DutyStatus.ON_DUTY_NOT_DRIVING, start,               0.5, activity="Pre-trip / TIV"),
        _seg(DutyStatus.DRIVING,             start + timedelta(hours=0.5), 4.0),
        _seg(DutyStatus.OFF_DUTY,            start + timedelta(hours=4.5), 0.5, activity="30-min break"),
    ]
    logs = build_daily_logs(segs)
    assert len(logs[0]["remarks"]) == 3


def test_no_duplicate_remarks_for_same_consecutive_status():
    start = datetime(2024, 1, 15, 8, 0, 0)
    segs = [
        _seg(DutyStatus.DRIVING, start,                         2.0),
        _seg(DutyStatus.DRIVING, start + timedelta(hours=2.0),  2.0),
    ]
    logs = build_daily_logs(segs)
    # Two consecutive driving segs = one remark entry, not two
    driving_remarks = [r for r in logs[0]["remarks"] if r["activity"] is None]
    assert len(driving_remarks) == 1


# ── Entries ──────────────────────────────────────────────────────────────────

def test_entries_start_end_within_0_and_24():
    segs = _engine_segments(50, 800)
    logs = build_daily_logs(segs)
    for log in logs:
        for entry in log["entries"]:
            assert 0.0 <= entry["start_hour"] <= 24.0
            assert 0.0 <= entry["end_hour"]   <= 24.0
            assert entry["start_hour"] < entry["end_hour"]


def test_from_and_to_location_populated():
    segs = _engine_segments(50, 400)
    logs = build_daily_logs(segs)
    for log in logs:
        assert log["from_location"]
        assert log["to_location"]
