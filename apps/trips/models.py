from django.db import models

from apps.common.models import BaseModel


class TripRequest(BaseModel):
    current_location         = models.CharField(max_length=500)
    current_lat              = models.FloatField()
    current_lng              = models.FloatField()
    pickup_location          = models.CharField(max_length=500)
    pickup_lat               = models.FloatField()
    pickup_lng               = models.FloatField()
    dropoff_location         = models.CharField(max_length=500)
    dropoff_lat              = models.FloatField()
    dropoff_lng              = models.FloatField()
    current_cycle_used_hours = models.FloatField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.current_location} → {self.dropoff_location}"


class TripPlan(BaseModel):
    trip_request         = models.OneToOneField(
        TripRequest, on_delete=models.CASCADE, related_name="plan"
    )
    total_distance_miles = models.FloatField()
    total_driving_hours  = models.FloatField()
    total_days           = models.IntegerField()
    route_geometry       = models.JSONField()
    stops                = models.JSONField()
    eld_segments         = models.JSONField()
    daily_logs           = models.JSONField()
    cache_key            = models.CharField(max_length=64, db_index=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Plan for {self.trip_request} ({self.total_distance_miles:.0f} mi)"
