from django.contrib import admin

from .models import TripPlan, TripRequest


@admin.register(TripRequest)
class TripRequestAdmin(admin.ModelAdmin):
    list_display  = ("id", "current_location", "pickup_location", "dropoff_location", "current_cycle_used_hours", "created_at")
    list_filter   = ("created_at",)
    search_fields = ("current_location", "pickup_location", "dropoff_location")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(TripPlan)
class TripPlanAdmin(admin.ModelAdmin):
    list_display  = ("id", "trip_request", "total_distance_miles", "total_driving_hours", "total_days", "created_at")
    list_filter   = ("created_at", "total_days")
    search_fields = ("trip_request__current_location", "trip_request__dropoff_location")
    readonly_fields = ("id", "created_at", "updated_at", "cache_key")
