"""
Business logic for tournament and competition management.
"""

from __future__ import annotations

from typing import List, Optional

from django.db import transaction

from athletes.models import AthleteProfile
from core.models import Belt

from .models import (Tournament, TournamentDivision, TournamentMatch,
                     TournamentParticipant)

# Belt ordering used for seeding
BELT_ORDER = {
    Belt.BeltColor.WHITE: 1,
    Belt.BeltColor.BLUE: 2,
    Belt.BeltColor.PURPLE: 3,
    Belt.BeltColor.BROWN: 4,
    Belt.BeltColor.BLACK: 5,
}


def _seed_key(participant: TournamentParticipant):
    """Sort key: belt desc, stripes desc, weight asc for seeding."""
    belt_rank = BELT_ORDER.get(participant.belt_at_registration, 0)
    weight = participant.weight_at_registration or 999
    stripes = participant.athlete.stripes
    return (belt_rank, stripes, weight)


class TournamentService:
    """Handles the full lifecycle of tournaments: creation, registration, bracket generation."""

    @staticmethod
    @transaction.atomic
    def create_tournament(
        academy,
        name: str,
        date,
        description: str = "",
        location: str = "",
        format: str = Tournament.Format.BRACKET,
        max_participants: Optional[int] = None,
    ) -> Tournament:
        """Create a new tournament in DRAFT status."""
        return Tournament.objects.create(
            academy=academy,
            name=name,
            date=date,
            description=description,
            location=location,
            format=format,
            max_participants=max_participants,
            status=Tournament.Status.DRAFT,
        )

    @staticmethod
    @transaction.atomic
    def open_registration(tournament: Tournament) -> Tournament:
        """Open a DRAFT tournament for participant registration."""
        if tournament.status != Tournament.Status.DRAFT:
            raise ValueError("Only DRAFT tournaments can be opened for registration.")
        tournament.status = Tournament.Status.OPEN
        tournament.save(update_fields=["status"])
        return tournament

    @staticmethod
    @transaction.atomic
    def register_participant(
        tournament: Tournament,
        athlete: AthleteProfile,
        division: Optional[TournamentDivision] = None,
    ) -> TournamentParticipant:
        """
        Register an athlete for a tournament division.

        - Tournament must be OPEN.
        - Athlete must not already be registered.
        - If max_participants is set, refuses when the tournament is full.
        - Snapshots belt and weight at registration time.
        """
        if tournament.status != Tournament.Status.OPEN:
            raise ValueError("Registration is only available for OPEN tournaments.")

        if tournament.max_participants is not None:
            current_count = TournamentParticipant.objects.filter(
                tournament=tournament,
            ).exclude(status=TournamentParticipant.RegistrationStatus.WITHDRAWN).count()
            if current_count >= tournament.max_participants:
                raise ValueError("Tournament is full.")

        participant, created = TournamentParticipant.objects.get_or_create(
            tournament=tournament,
            athlete=athlete,
            defaults={
                "division": division,
                "status": TournamentParticipant.RegistrationStatus.CONFIRMED,
                "belt_at_registration": athlete.belt,
                "weight_at_registration": athlete.weight,
            },
        )
        if not created:
            if participant.status != TournamentParticipant.RegistrationStatus.WITHDRAWN:
                raise ValueError("Athlete is already registered for this tournament.")
            # Re-register a previously withdrawn participant
            participant.division = division
            participant.status = TournamentParticipant.RegistrationStatus.CONFIRMED
            participant.belt_at_registration = athlete.belt
            participant.weight_at_registration = athlete.weight
            participant.save(update_fields=["division", "status", "belt_at_registration", "weight_at_registration"])

        return participant

    @staticmethod
    @transaction.atomic
    def withdraw_participant(participant: TournamentParticipant) -> TournamentParticipant:
        """Withdraw a participant from a tournament."""
        if participant.status == TournamentParticipant.RegistrationStatus.WITHDRAWN:
            raise ValueError("Participant is already withdrawn.")
        participant.status = TournamentParticipant.RegistrationStatus.WITHDRAWN
        participant.save(update_fields=["status"])
        return participant

    @staticmethod
    @transaction.atomic
    def generate_bracket(tournament: Tournament) -> List[TournamentMatch]:
        """
        Seed participants and generate first-round bracket matchups.

        Athletes are sorted by (belt desc, stripes desc, weight asc) and paired
        with their nearest neighbour to minimise the skill gap. Odd-athlete
        divisions give a bye to the top seed (no match created for them).

        Transitions tournament status to IN_PROGRESS.
        Raises ValueError if tournament is not OPEN or has fewer than 2 confirmed participants.
        """
        if tournament.status != Tournament.Status.OPEN:
            raise ValueError("Bracket can only be generated for OPEN tournaments.")

        participants = list(
            TournamentParticipant.objects.filter(
                tournament=tournament,
                status=TournamentParticipant.RegistrationStatus.CONFIRMED,
            ).select_related("athlete__user")
        )

        if len(participants) < 2:
            raise ValueError(
                "At least 2 confirmed participants are required to generate a bracket."
            )

        # Assign seeds
        participants.sort(key=_seed_key, reverse=True)
        for idx, p in enumerate(participants, start=1):
            p.seed = idx
        TournamentParticipant.objects.bulk_update(participants, ["seed"])

        # Pair participants sequentially (nearest-neighbour)
        matches = []
        i = 0
        while i + 1 < len(participants):
            match = TournamentMatch.objects.create(
                tournament=tournament,
                division=participants[i].division,
                round_number=1,
                athlete_a=participants[i].athlete,
                athlete_b=participants[i + 1].athlete,
            )
            matches.append(match)
            i += 2

        tournament.status = Tournament.Status.IN_PROGRESS
        tournament.save(update_fields=["status"])
        return matches

    @staticmethod
    @transaction.atomic
    def record_match_result(
        match: TournamentMatch,
        winner: AthleteProfile,
        score_a: int = 0,
        score_b: int = 0,
        notes: str = "",
    ) -> TournamentMatch:
        """
        Record the result of a tournament match.

        Raises ValueError if the match is already finished or the winner
        is not one of the participants.
        """
        if match.is_finished:
            raise ValueError("Match is already finished.")
        if winner not in (match.athlete_a, match.athlete_b):
            raise ValueError("Winner must be one of the two match participants.")

        match.winner = winner
        match.score_a = score_a
        match.score_b = score_b
        match.is_finished = True
        match.notes = notes
        match.save(update_fields=["winner", "score_a", "score_b", "is_finished", "notes"])
        return match

    @staticmethod
    @transaction.atomic
    def complete_tournament(tournament: Tournament) -> Tournament:
        """Mark a tournament as COMPLETED."""
        if tournament.status != Tournament.Status.IN_PROGRESS:
            raise ValueError("Only IN_PROGRESS tournaments can be completed.")
        tournament.status = Tournament.Status.COMPLETED
        tournament.save(update_fields=["status"])
        return tournament
