from django.db import transaction
from django.db.models import F
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import IsAcademyProfessor

from .models import Match, MatchEvent
from .serializers import MatchEventSerializer, MatchSerializer


class MatchViewSet(viewsets.ModelViewSet):
    """
    H-4 fixes applied:
      - IsAcademyProfessor permission on all endpoints
      - Queryset scoped to the academy in the query param
      - winner_id validated to be a match participant
      - Score increments use F() to avoid lost-update race conditions
      - add_event uses raise_exception=True (I-1 fix)
    """

    serializer_class = MatchSerializer
    permission_classes = [IsAcademyProfessor]

    def get_queryset(self):
        academy_id = self.request.query_params.get("academy")
        if not academy_id:
            return Match.objects.none()
        return (
            Match.objects.filter(academy_id=academy_id)
            .select_related("athlete_a", "athlete_b", "winner")
            .prefetch_related("events")
        )

    @action(detail=True, methods=["post"])
    def add_event(self, request, pk=None):
        match = self.get_object()
        event_serializer = MatchEventSerializer(data=request.data)
        event_serializer.is_valid(raise_exception=True)  # I-1 fix

        athlete_id = event_serializer.validated_data["athlete"].id
        event_type = event_serializer.validated_data["event_type"]
        points = event_serializer.validated_data.get("points_awarded", 0)

        # H-4 fix: validate athlete is a participant in this specific match
        if athlete_id not in (match.athlete_a_id, match.athlete_b_id):
            return Response(
                {"detail": "Athlete is not a participant in this match."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            event_serializer.save(match=match)
            # H-4 fix: use F() to avoid lost-update race on concurrent score events
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

    @action(detail=True, methods=["post"])
    def finish_match(self, request, pk=None):
        match = self.get_object()
        winner_id = request.data.get("winner_id")

        if not winner_id:
            return Response(
                {"error": "winner_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # H-4 fix: winner must be one of the two participants
        valid_participant_ids = {str(match.athlete_a_id), str(match.athlete_b_id)}
        if str(winner_id) not in valid_participant_ids:
            return Response(
                {"error": "winner_id must be one of the match participants."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        match.is_finished = True
        match.winner_id = winner_id
        match.save()
        return Response(MatchSerializer(match).data, status=status.HTTP_200_OK)
