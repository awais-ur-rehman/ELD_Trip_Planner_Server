from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.routing.exceptions import GeocodingError, RoutingError

from .serializers import TripRequestSerializer
from .services import plan_trip_service


class TripPlanView(APIView):

    def post(self, request: Request) -> Response:
        serializer = TripRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"data": None, "error": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            plan_data = plan_trip_service(serializer.validated_data)
        except GeocodingError as exc:
            return Response(
                {"data": None, "error": str(exc)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except RoutingError as exc:
            return Response(
                {"data": None, "error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        http_status = (
            status.HTTP_200_OK
            if plan_data.get("cached")
            else status.HTTP_201_CREATED
        )

        return Response({"data": plan_data}, status=http_status)
