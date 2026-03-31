from django.db import transaction
from django.db.models import F
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsAcademyMember, IsAcademyProfessor

from .models import Match, MatchEvent
from .serializers import MatchEventSerializer, MatchSerializer


class MatchViewSet(viewsets.ModelViewSet):
    """
    Read (list/retrieve) requires academy membership.
    Write (create/update/delete/add_event/finish_match) requires professor role.
    Without ?academy=, returns an empty queryset — no permission error.
    """

    serializer_class = MatchSerializer

    def get_permissions(self):
        academy_id = self.request.query_params.get("academy")
        if not academy_id:
            # No academy scoping — empty queryset, only auth required.
            return [IsAuthenticated()]
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAcademyMember()]
        return [IsAcademyProfessor()]

    def get_queryset(self):
        """Return matches scoped to ?academy. Returns empty queryset if param is absent."""
        academy_id = self.request.query_params.get("academy")
        if not academy_id:
            return Match.objects.none()
        return (
            Match.objects.filter(academy_id=academy_id)
            .select_related("athlete_a", "athlete_b", "winner")
            .prefetch_related("events")
        )

    @extend_schema(
        request=None,
        responses=MatchSerializer,
        summary="Record a scoring event in a match",
        description=(
            "Add a POINTS, ADVANTAGE, PENALTY, or SUBMISSION event. "
            "The athlete must be one of the two match participants. "
            "Score increments use F() to prevent lost-update races."
        ),
    )
    @action(detail=True, methods=["post"])
    def add_event(self, request, pk=None):
        # Validate input before acquiring any lock
        event_serializer = MatchEventSerializer(data=request.data)
        event_serializer.is_valid(raise_exception=True)

        athlete_id = event_serializer.validated_data["athlete"].id
        event_type = event_serializer.validated_data["event_type"]
        points = event_serializer.validated_data.get("points_awarded", 0)

        with transaction.atomic():
            # H-4 fix: re-fetch the match inside the atomic block with
            # select_for_update() so the participant check and score update
            # are performed against a consistent, locked row.
            match = Match.objects.select_for_update().get(pk=pk)
            self.check_object_permissions(request, match)

            if athlete_id not in (match.athlete_a_id, match.athlete_b_id):
                return Response(
                    {"detail": "Athlete is not a participant in this match."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            event_serializer.save(match=match)
            if event_type == MatchEvent.TypeChoices.POINTS:
                if athlete_id == match.athlete_a_id:
                    Match.objects.filter(pk=match.pk).update(
                        score_a=F("score_a") + points
                    )
                elif athlete_id == match.athlete_b_id:
                    Match.objects.filter(pk=match.pk).update(
                        score_b=F("score_b") + points
                    )

        match.refresh_from_db()
        return Response(MatchSerializer(match).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Finish a match and declare the winner",
        description=(
            "Mark the match as finished. winner_id must be athlete_a or athlete_b; "
            "any other value returns 400."
        ),
    )
    @action(detail=True, methods=["post"])
    def finish_match(self, request, pk=None):
        match = self.get_object()
        winner_id = request.data.get("winner_id")

        if not winner_id:
            return Response(
                {"error": "winner_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # winner_id must be one of the two participants; compare as integers to
        # avoid silent mismatches from string/int type coercion.
        try:
            winner_id = int(winner_id)
        except (TypeError, ValueError):
            return Response(
                {"error": "winner_id must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if winner_id not in (match.athlete_a_id, match.athlete_b_id):
            return Response(
                {"error": "winner_id must be one of the match participants."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Use update() with update_fields to avoid overwriting concurrent score
        # changes made by add_event between get_object() and this save().
        Match.objects.filter(pk=match.pk).update(is_finished=True, winner_id=winner_id)
        match.refresh_from_db()
        return Response(MatchSerializer(match).data, status=status.HTTP_200_OK)
