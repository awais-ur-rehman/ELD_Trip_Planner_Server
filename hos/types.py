from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DutyStatus(str, Enum):
    OFF_DUTY            = "off_duty"
    SLEEPER_BERTH       = "sleeper_berth"
    DRIVING             = "driving"
    ON_DUTY_NOT_DRIVING = "on_duty_not_driving"


class StopType(str, Enum):
    CURRENT = "current"
    PICKUP  = "pickup"
    DROPOFF = "dropoff"
    FUEL    = "fuel"
    REST    = "rest_10hr"
    BREAK   = "break_30min"


@dataclass
class Segment:
    status:         DutyStatus
    start_time:     datetime
    end_time:       datetime
    location_name:  str
    is_stationary:  bool       = False
    activity_label: str | None = None

    @property
    def duration_hours(self) -> float:
        return (self.end_time - self.start_time).total_seconds() / 3600


@dataclass
class Stop:
    type:             StopType
    label:            str
    lat:              float
    lng:              float
    arrival_time:     datetime
    duration_minutes: int
    location_name:    str


@dataclass
class DriverState:
    current_time:     datetime
    current_lat:      float
    current_lng:      float
    current_location: str

    shift_drive_hours:            float           = 0.0
    shift_window_start:           datetime | None = None
    cumulative_drive_since_break: float           = 0.0

    cycle_hours_used: float = 0.0

    miles_driven:     float = 0.0
    miles_since_fuel: float = 0.0

    segments: list[Segment] = field(default_factory=list)
    stops:    list[Stop]    = field(default_factory=list)
