from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Match, MatchEvent
from .serializers import MatchEventSerializer, MatchSerializer


class MatchViewSet(viewsets.ModelViewSet):

    queryset = Match.objects.all()
    serializer_class = MatchSerializer

    @action(detail=True, methods=["post"])
    def add_event(self, request, pk=None):

        match = self.get_object()
        event_serializer = MatchEventSerializer(data=request.data)

        if event_serializer.is_valid():
            athlete_id = event_serializer.validated_data["athlete"].id
            event_type = event_serializer.validated_data["event_type"]
            points = event_serializer.validated_data.get("points_awarded", 0)

            with transaction.atomic():

                event_serializer.save(match=match)

                if athlete_id == match.athlete_a.id:
                    if event_type == "POINTS":
                        match.score_a += points
                elif athlete_id == match.athlete_b.id:
                    if event_type == "POINTS":
                        match.score_b += points

                match.save()

            return Response(MatchSerializer(match).data, status=status.HTTP_201_CREATED)

        return Response(event_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def finish_match(self, request, pk=None):
        match = self.get_object()
        winner_id = request.data.get("winner_id")

        if not winner_id:
            return Response(
                {"error": "winner_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        match.is_finished = True
        match.winner_id = winner_id
        match.save()

        return Response(MatchSerializer(match).data, status=status.HTTP_200_OK)
