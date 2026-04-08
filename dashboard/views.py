"""
Academy Analytics Dashboard view.

GET /api/v1/dashboard/?academy=<id>

Returns a single JSON payload covering revenue, attendance, member stats,
membership retention, and top athletes for the requested academy.

Permission: IsAcademyProfessor (professors and owners).
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAcademyProfessor

from .selectors import get_academy_dashboard
from .serializers import AcademyDashboardSerializer


class AcademyDashboardView(APIView):
    """
    Academy analytics dashboard.

    Returns aggregated metrics for the requested academy. Requires professor
    or owner membership. Pass ?academy=<id> to identify the academy.
    """

    permission_classes = [IsAcademyProfessor]

    @extend_schema(
        summary="Academy analytics dashboard",
        description=(
            "Returns a single snapshot of key academy metrics: "
            "revenue (current & previous month), weekly attendance, "
            "member belt distribution, membership retention, and top athletes."
        ),
        parameters=[
            OpenApiParameter(
                name="academy",
                description="Academy ID (required)",
                required=True,
                type=int,
            ),
        ],
        responses={200: AcademyDashboardSerializer},
    )
    def get(self, request):
        academy_id = request.query_params.get("academy")
        if not academy_id:
            return Response(
                {"detail": "academy query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            academy_id = int(academy_id)
        except ValueError:
            return Response(
                {"detail": "academy must be a valid integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = get_academy_dashboard(academy_id)
        serializer = AcademyDashboardSerializer(data)
        return Response(serializer.data)
