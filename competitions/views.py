from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from athletes.models import AthleteProfile
from core.mixins import AcademyFilterMixin, SwaggerSafeMixin
from core.permissions import IsAcademyMember, IsAcademyProfessor

from .models import Tournament, TournamentDivision, TournamentMatch, TournamentParticipant
from .selectors import (get_divisions_for_tournament, get_participants_for_tournament,
                        get_tournament_bracket, get_tournaments_for_academy)
from .serializers import (RecordMatchResultSerializer, RegisterParticipantSerializer,
                           TournamentDivisionSerializer, TournamentMatchSerializer,
                           TournamentParticipantSerializer, TournamentSerializer)
from .services import TournamentService


class TournamentViewSet(SwaggerSafeMixin, AcademyFilterMixin, viewsets.ModelViewSet):
    """
    Tournament CRUD scoped to an academy.

    Reads require academy membership; writes require professor role.
    """

    serializer_class = TournamentSerializer

    def get_permissions(self):
        academy_id = self.request.query_params.get("academy")
        if not academy_id:
            return [IsAuthenticated()]
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAcademyMember()]
        return [IsAcademyProfessor()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Tournament.objects.none()
        academy_id = self.request.query_params.get("academy")
        if not academy_id:
            return Tournament.objects.none()
        status_filter = self.request.query_params.get("status")
        return get_tournaments_for_academy(academy_id, status=status_filter)

    def perform_create(self, serializer):
        from academies.models import Academy

        academy_id = self.request.query_params.get("academy")
        academy = get_object_or_404(Academy, pk=academy_id)
        serializer.save(academy=academy)

    @extend_schema(
        request=None,
        responses=TournamentSerializer,
        summary="Open a tournament for registration",
    )
    @action(detail=True, methods=["post"], permission_classes=[IsAcademyProfessor])
    def open(self, request, pk=None):
        tournament = self.get_object()
        try:
            tournament = TournamentService.open_registration(tournament)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TournamentSerializer(tournament).data)

    @extend_schema(
        request=RegisterParticipantSerializer,
        responses=TournamentParticipantSerializer,
        summary="Register an athlete for this tournament",
    )
    @action(detail=True, methods=["post"], permission_classes=[IsAcademyMember])
    def register(self, request, pk=None):
        tournament = self.get_object()
        serializer = RegisterParticipantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        athlete = get_object_or_404(AthleteProfile, pk=serializer.validated_data["athlete_id"])
        division = None
        division_id = serializer.validated_data.get("division_id")
        if division_id:
            division = get_object_or_404(TournamentDivision, pk=division_id, tournament=tournament)

        try:
            participant = TournamentService.register_participant(tournament, athlete, division)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TournamentParticipantSerializer(participant).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=None,
        responses=TournamentMatchSerializer(many=True),
        summary="Generate first-round bracket for this tournament",
    )
    @action(detail=True, methods=["post"], permission_classes=[IsAcademyProfessor])
    def generate_bracket(self, request, pk=None):
        tournament = self.get_object()
        try:
            matches = TournamentService.generate_bracket(tournament)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TournamentMatchSerializer(matches, many=True).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=None,
        responses=TournamentMatchSerializer(many=True),
        summary="List all matches in this tournament's bracket",
    )
    @action(detail=True, methods=["get"], permission_classes=[IsAcademyMember])
    def bracket(self, request, pk=None):
        tournament = self.get_object()
        matches = get_tournament_bracket(tournament.pk)
        return Response(TournamentMatchSerializer(matches, many=True).data)

    @extend_schema(
        request=None,
        responses=TournamentParticipantSerializer(many=True),
        summary="List all participants in this tournament",
    )
    @action(detail=True, methods=["get"], permission_classes=[IsAcademyMember])
    def participants(self, request, pk=None):
        tournament = self.get_object()
        division_id = request.query_params.get("division")
        qs = get_participants_for_tournament(tournament.pk, division_id=division_id)
        return Response(TournamentParticipantSerializer(qs, many=True).data)

    @extend_schema(
        request=None,
        responses=TournamentSerializer,
        summary="Complete a tournament",
    )
    @action(detail=True, methods=["post"], permission_classes=[IsAcademyProfessor])
    def complete(self, request, pk=None):
        tournament = self.get_object()
        try:
            tournament = TournamentService.complete_tournament(tournament)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TournamentSerializer(tournament).data)


class TournamentMatchViewSet(viewsets.GenericViewSet):
    """
    Actions on individual tournament matches (record results).
    """

    serializer_class = TournamentMatchSerializer
    queryset = TournamentMatch.objects.select_related(
        "athlete_a__user", "athlete_b__user", "winner__user", "division", "tournament"
    )

    def get_permissions(self):
        return [IsAcademyProfessor()]

    @extend_schema(
        request=RecordMatchResultSerializer,
        responses=TournamentMatchSerializer,
        summary="Record the result of a tournament match",
    )
    @action(detail=True, methods=["post"])
    def result(self, request, pk=None):
        match = self.get_object()
        serializer = RecordMatchResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        winner_id = serializer.validated_data["winner_id"]
        winner = get_object_or_404(AthleteProfile, pk=winner_id)

        try:
            match = TournamentService.record_match_result(
                match=match,
                winner=winner,
                score_a=serializer.validated_data["score_a"],
                score_b=serializer.validated_data["score_b"],
                notes=serializer.validated_data["notes"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TournamentMatchSerializer(match).data)


class TournamentDivisionViewSet(SwaggerSafeMixin, viewsets.ModelViewSet):
    """CRUD for tournament divisions."""

    serializer_class = TournamentDivisionSerializer

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAcademyMember()]
        return [IsAcademyProfessor()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TournamentDivision.objects.none()
        tournament_pk = self.kwargs.get("tournament_pk") or self.request.query_params.get("tournament")
        if not tournament_pk:
            return TournamentDivision.objects.none()
        return get_divisions_for_tournament(tournament_pk)

    def perform_create(self, serializer):
        tournament_pk = self.kwargs.get("tournament_pk") or self.request.query_params.get("tournament")
        tournament = get_object_or_404(Tournament, pk=tournament_pk)
        serializer.save(tournament=tournament)
