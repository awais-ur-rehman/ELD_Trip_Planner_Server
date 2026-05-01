from rest_framework import serializers


class TripRequestSerializer(serializers.Serializer):
    current_location         = serializers.CharField(max_length=500)
    pickup_location          = serializers.CharField(max_length=500)
    dropoff_location         = serializers.CharField(max_length=500)
    current_cycle_used_hours = serializers.FloatField(min_value=0.0, max_value=70.0)

    def validate_current_location(self, value: str) -> str:
        return value.strip()

    def validate_pickup_location(self, value: str) -> str:
        return value.strip()

    def validate_dropoff_location(self, value: str) -> str:
        return value.strip()

    def validate(self, data: dict) -> dict:
        locations = (
            data.get("current_location"),
            data.get("pickup_location"),
            data.get("dropoff_location"),
        )
        if len(set(locations)) != 3:
            raise serializers.ValidationError(
                "current_location, pickup_location, and dropoff_location must all be different."
            )
        return data
