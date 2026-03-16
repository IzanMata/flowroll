from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from athletes.models import AthleteProfile
from core.permissions import IsAcademyProfessor

from . import selectors
from .filters import MatchupFilter, TimerPresetFilter
from .models import Matchup, TimerPreset, TimerSession, WeightClass
from .serializers import (
    MatchupSerializer,
    PairAthletesSerializer,
    TimerPresetSerializer,
    TimerSessionSerializer,
    WeightClassSerializer,
)
from .services import MatchmakingService, TimerService


class WeightClassViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WeightClass.objects.all()
    serializer_class = WeightClassSerializer
    search_fields = ["name"]
    ordering_fields = ["min_weight"]


class TimerPresetViewSet(viewsets.ModelViewSet):
    serializer_class = TimerPresetSerializer
    filterset_class = TimerPresetFilter

    def get_queryset(self):
        return selectors.get_presets_for_academy(
            self.request.query_params.get("academy", 0)
        )

    @action(detail=True, methods=["post"])
    def start_session(self, request, pk=None):
        preset = self.get_object()
        session = TimerSession.objects.create(preset=preset)
        TimerService.start(session)
        return Response(TimerSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class TimerSessionViewSet(viewsets.ModelViewSet):
    serializer_class = TimerSessionSerializer

    def get_queryset(self):
        return selectors.get_active_sessions(self.request.query_params.get("academy", 0))

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
    serializer_class = MatchupSerializer
    filterset_class = MatchupFilter
    ordering_fields = ["round_number", "created_at"]

    def get_queryset(self):
        return selectors.get_matchups_for_academy(
            self.request.query_params.get("academy", 0)
        )

    @extend_schema(request=PairAthletesSerializer, responses=MatchupSerializer(many=True))
    @action(detail=False, methods=["post"], permission_classes=[IsAcademyProfessor])
    def pair_athletes(self, request):
        serializer = PairAthletesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        athletes = list(AthleteProfile.objects.filter(pk__in=d["athlete_ids"]))
        if len(athletes) != len(d["athlete_ids"]):
            return Response({"detail": "One or more athletes not found."}, status=404)

        from academies.models import Academy
        academy = get_object_or_404(Academy, pk=d["academy_id"])
        weight_class = None
        if d.get("weight_class_id"):
            weight_class = get_object_or_404(WeightClass, pk=d["weight_class_id"])

        if d["match_format"] == Matchup.MatchFormat.TOURNAMENT:
            matchups = MatchmakingService.pair_for_tournament(athletes, academy, weight_class)
        else:
            try:
                matchups = MatchmakingService.pair_for_survival(athletes, academy, weight_class)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(MatchupSerializer(matchups, many=True).data, status=status.HTTP_201_CREATED)
