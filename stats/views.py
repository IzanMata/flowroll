from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from athletes.models import AthleteProfile
from core.mixins import SwaggerSafeMixin
from core.permissions import IsAcademyMember, IsAcademyProfessor

from .models import AthleteMatchStats
from .selectors import get_academy_leaderboard, get_stats_for_athlete, get_stats_for_academy
from .serializers import AthleteMatchStatsSerializer
from .services import StatsService


class AthleteStatsViewSet(SwaggerSafeMixin, viewsets.ReadOnlyModelViewSet):
    """
    Read-only match statistics for athletes.

    All endpoints are scoped to an academy via ?academy=<id>.
    Reads require academy membership.
    """

    serializer_class = AthleteMatchStatsSerializer
    permission_classes = [IsAcademyMember]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AthleteMatchStats.objects.none()
        academy_id = self.request.query_params.get("academy")
        if not academy_id:
            return AthleteMatchStats.objects.none()
        return get_stats_for_academy(academy_id)

    @extend_schema(
        summary="Get match stats for a single athlete",
        description="Returns the cached match stats for an athlete. Returns 404 if not yet computed.",
    )
    @action(detail=False, methods=["get"], url_path="athlete/(?P<athlete_pk>[^/.]+)")
    def by_athlete(self, request, athlete_pk=None):
        # SEC: scope to the requested academy to prevent cross-tenant data leak
        academy_id = request.query_params.get("academy")
        athlete = get_object_or_404(AthleteProfile, pk=athlete_pk, academy_id=academy_id)
        stats = get_stats_for_athlete(athlete)
        if stats is None:
            return Response(
                {"detail": "No stats found. The athlete has not competed yet."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(AthleteMatchStatsSerializer(stats).data)

    @extend_schema(
        summary="Recompute stats for an athlete (professor only)",
        description="Triggers a full recomputation of match stats from match history.",
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="athlete/(?P<athlete_pk>[^/.]+)/recompute",
        permission_classes=[IsAcademyProfessor],
    )
    def recompute(self, request, athlete_pk=None):
        # SEC: scope to the requested academy — a professor at academy A must not
        # be able to trigger recomputes for athletes at academy B.
        academy_id = request.query_params.get("academy")
        athlete = get_object_or_404(AthleteProfile, pk=athlete_pk, academy_id=academy_id)
        stats = StatsService.recompute_for_athlete(athlete)
        return Response(AthleteMatchStatsSerializer(stats).data)

    @extend_schema(
        summary="Academy leaderboard — top athletes by wins",
        description="Returns the top 20 athletes in the academy ranked by wins.",
    )
    @action(detail=False, methods=["get"])
    def leaderboard(self, request):
        academy_id = request.query_params.get("academy")
        if not academy_id:
            return Response(
                {"detail": "academy query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        limit = min(int(request.query_params.get("limit", 20)), 100)
        stats_qs = get_academy_leaderboard(academy_id, limit=limit)
        return Response(AthleteMatchStatsSerializer(stats_qs, many=True).data)
