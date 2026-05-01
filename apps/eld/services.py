from __future__ import annotations

from datetime import date, datetime, timedelta

from hos.types import DutyStatus, Segment

_STATUSES = ("off_duty", "sleeper_berth", "driving", "on_duty_not_driving")


def build_daily_logs(segments: list[Segment]) -> list[dict]:
    if not segments:
        return []

    trip_start = segments[0].start_time.date()
    trip_end   = segments[-1].end_time.date()

    logs = []
    current_day = trip_start
    day_number  = 1

    while current_day <= trip_end:
        entries = _clip_segments_to_day(segments, current_day)
        if entries:
            logs.append(_build_day_log(current_day, entries, day_number))
            day_number += 1
        current_day += timedelta(days=1)

    return logs


def _clip_segments_to_day(segments: list[Segment], day: date) -> list[dict]:
    day_start = datetime.combine(day, datetime.min.time())
    day_end   = day_start + timedelta(days=1)
    result    = []

    for seg in segments:
        if seg.end_time <= day_start or seg.start_time >= day_end:
            continue

        clipped_start = max(seg.start_time, day_start)
        clipped_end   = min(seg.end_time,   day_end)

        result.append({
            "status":         seg.status.value,
            "start_hour":     round((clipped_start - day_start).total_seconds() / 3600, 4),
            "end_hour":       round((clipped_end   - day_start).total_seconds() / 3600, 4),
            "is_stationary":  seg.is_stationary,
            "activity_label": seg.activity_label,
            "location_name":  seg.location_name,
        })

    return result


def _build_day_log(day: date, entries: list[dict], day_number: int) -> dict:
    totals  = {s: 0.0 for s in _STATUSES}
    remarks = []
    prev_status = None

    for entry in entries:
        duration = round(entry["end_hour"] - entry["start_hour"], 4)
        totals[entry["status"]] = round(totals[entry["status"]] + duration, 4)

        if entry["status"] != prev_status:
            remarks.append({
                "time_hour": entry["start_hour"],
                "location":  entry["location_name"],
                "activity":  entry["activity_label"],
            })
        prev_status = entry["status"]

    total_accounted = round(sum(totals.values()), 4)
    if total_accounted < 24.0:
        # Pad start of day with off-duty (driver was resting before trip started
        # or the trip started mid-day)
        totals["off_duty"] = round(totals["off_duty"] + (24.0 - total_accounted), 4)

    return {
        "date":              day.isoformat(),
        "day_number":        day_number,
        "from_location":     entries[0]["location_name"],
        "to_location":       entries[-1]["location_name"],
        "total_miles_today": 0,  # filled in by trips.services after route data is available
        "entries":           entries,
        "remarks":           remarks,
        "totals":            {k: round(v, 3) for k, v in totals.items()},
    }
