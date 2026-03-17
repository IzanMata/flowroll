from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from athletes.models import AthleteProfile
from core.permissions import IsAcademyMember, IsAcademyProfessor

from . import selectors
from .filters import MatchupFilter, TimerPresetFilter
from .models import Matchup, TimerPreset, TimerSession, WeightClass
from .serializers import (MatchupSerializer, PairAthletesSerializer,
                          TimerPresetSerializer, TimerSessionSerializer,
                          WeightClassSerializer)
from .services import MatchmakingService, TimerService


class WeightClassViewSet(viewsets.ReadOnlyModelViewSet):
    """Weight classes are platform-wide reference data — read-only."""

    queryset = WeightClass.objects.all()
    serializer_class = WeightClassSerializer
    search_fields = ["name"]
    ordering_fields = ["min_weight"]


class TimerPresetViewSet(viewsets.ModelViewSet):
    """
    M-4 fix: timer presets are academy-scoped; access restricted to
    academy members; mutations restricted to professors/owners.
    """

    serializer_class = TimerPresetSerializer
    filterset_class = TimerPresetFilter

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TimerPreset.objects.none()
        return selectors.get_presets_for_academy(
            self.request.query_params.get("academy", 0)
        )

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAcademyMember()]
        return [IsAcademyProfessor()]

    @action(detail=True, methods=["post"])
    def start_session(self, request, pk=None):
        preset = self.get_object()
        session = TimerSession.objects.create(preset=preset)
        TimerService.start(session)
        return Response(
            TimerSessionSerializer(session).data, status=status.HTTP_201_CREATED
        )


class TimerSessionViewSet(viewsets.ModelViewSet):
    """
    M-4 fix: timer sessions are scoped to academy; access restricted to members.
    """

    serializer_class = TimerSessionSerializer
    permission_classes = [IsAcademyMember]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TimerSession.objects.none()
        return selectors.get_active_sessions(
            self.request.query_params.get("academy", 0)
        )

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        session = self.get_object()
        try:
            TimerService.pause(session)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TimerSessionSerializer(session).data)

    @action(detail=True, methods=["post"])
    def finish(self, request, pk=None):
        session = self.get_object()
        TimerService.finish(session)
        return Response(TimerSessionSerializer(session).data)


class MatchupViewSet(viewsets.ModelViewSet):
    """
    M-3/M-4 fix: matchups scoped to academy; pair_athletes validates that
    all supplied athlete IDs belong to the requested academy.
    """

    serializer_class = MatchupSerializer
    filterset_class = MatchupFilter
    ordering_fields = ["round_number", "created_at"]
    permission_classes = [IsAcademyMember]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Matchup.objects.none()
        return selectors.get_matchups_for_academy(
            self.request.query_params.get("academy", 0)
        )

    @extend_schema(
        request=PairAthletesSerializer, responses=MatchupSerializer(many=True)
    )
    @action(detail=False, methods=["post"], permission_classes=[IsAcademyProfessor])
    def pair_athletes(self, request):
        serializer = PairAthletesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        from academies.models import Academy

        academy = get_object_or_404(Academy, pk=d["academy_id"])

        # M-3 fix: filter athletes by BOTH pk list AND academy, so a professor
        # cannot inject athletes from a foreign academy into a matchup.
        athletes = list(
            AthleteProfile.objects.filter(
                pk__in=d["athlete_ids"],
                academy=academy,
            )
        )
        if len(athletes) != len(d["athlete_ids"]):
            return Response(
                {
                    "detail": (
                        "One or more athletes not found, or do not belong "
                        "to the specified academy."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        weight_class = None
        if d.get("weight_class_id"):
            weight_class = get_object_or_404(WeightClass, pk=d["weight_class_id"])

        if d["match_format"] == Matchup.MatchFormat.TOURNAMENT:
            matchups = MatchmakingService.pair_for_tournament(
                athletes, academy, weight_class
            )
        else:
            try:
                matchups = MatchmakingService.pair_for_survival(
                    athletes, academy, weight_class
                )
            except ValueError as exc:
                return Response(
                    {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
                )

        return Response(
            MatchupSerializer(matchups, many=True).data, status=status.HTTP_201_CREATED
        )
