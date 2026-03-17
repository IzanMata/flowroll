"""
Matchmaking and timer business logic.

MatchmakingService pairs athletes for either Tournament (bracket) or
Survival (king-of-the-mat) formats, using belt level and weight as
primary sorting criteria.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from django.db import transaction

from athletes.models import AthleteProfile
from core.models import Belt

from .models import Matchup, WeightClass

# Belt ordering map used for numeric comparison
BELT_ORDER = {
    Belt.BeltColor.WHITE: 1,
    Belt.BeltColor.BLUE: 2,
    Belt.BeltColor.PURPLE: 3,
    Belt.BeltColor.BROWN: 4,
    Belt.BeltColor.BLACK: 5,
}


def _athlete_score(athlete: AthleteProfile) -> Tuple[int, int, float]:
    """Return (belt_order, stripes, weight) — used as sort key for pairing."""
    belt_rank = BELT_ORDER.get(athlete.belt, 0)
    return (belt_rank, athlete.stripes, athlete.weight or 0.0)


class MatchmakingService:
    """
    Pairs a list of AthleteProfiles into Matchup records.

    Pairing strategy
    ----------------
    Athletes are sorted by (belt, stripes, weight) and then paired
    sequentially with their nearest neighbour — this minimises the
    skill gap between opponents. If there is an odd number of athletes,
    the last athlete receives a bye (no matchup created).
    """

    @staticmethod
    def pair_for_tournament(
        athletes: List[AthleteProfile],
        academy,
        weight_class: Optional[WeightClass] = None,
        round_number: int = 1,
    ) -> List[Matchup]:
        """
        Create bracket-style matchups for a single round.
        Returns the list of created Matchup objects.
        """
        sorted_athletes = sorted(athletes, key=_athlete_score)
        matchups = []
        i = 0
        while i + 1 < len(sorted_athletes):
            m = Matchup.objects.create(
                academy=academy,
                athlete_a=sorted_athletes[i],
                athlete_b=sorted_athletes[i + 1],
                weight_class=weight_class,
                match_format=Matchup.MatchFormat.TOURNAMENT,
                round_number=round_number,
            )
            matchups.append(m)
            i += 2
        return matchups

    @staticmethod
    def pair_for_survival(
        athletes: List[AthleteProfile],
        academy,
        weight_class: Optional[WeightClass] = None,
    ) -> List[Matchup]:
        """
        Create the *first* matchup for a survival (king-of-the-mat) session.
        The defender is the athlete with the highest score; the first challenger
        is chosen from the remaining pool sorted by score.
        Returns a single-element list containing the first matchup.
        """
        if len(athletes) < 2:
            raise ValueError("Survival mode requires at least 2 athletes.")

        sorted_athletes = sorted(athletes, key=_athlete_score, reverse=True)
        defender = sorted_athletes[0]
        challenger = sorted_athletes[1]

        matchup = Matchup.objects.create(
            academy=academy,
            athlete_a=defender,
            athlete_b=challenger,
            weight_class=weight_class,
            match_format=Matchup.MatchFormat.SURVIVAL,
            round_number=1,
        )
        return [matchup]

    @staticmethod
    def advance_survival(
        completed_matchup: Matchup,
        remaining_challengers: List[AthleteProfile],
    ) -> Optional[Matchup]:
        """
        After a survival matchup finishes, create the next matchup.
        The winner defends against the next challenger.
        Returns None if there are no more challengers.
        """
        if completed_matchup.status != Matchup.MatchStatus.COMPLETED:
            raise ValueError("Cannot advance: matchup is not completed.")
        if not completed_matchup.winner:
            raise ValueError("Cannot advance: no winner set on completed matchup.")
        if not remaining_challengers:
            return None

        sorted_challengers = sorted(
            remaining_challengers, key=_athlete_score, reverse=True
        )
        next_challenger = sorted_challengers[0]

        return Matchup.objects.create(
            academy=completed_matchup.academy,
            athlete_a=completed_matchup.winner,
            athlete_b=next_challenger,
            weight_class=completed_matchup.weight_class,
            match_format=Matchup.MatchFormat.SURVIVAL,
            round_number=completed_matchup.round_number + 1,
        )

    @staticmethod
    def filter_by_weight_class(
        athletes: List[AthleteProfile],
        weight_class: WeightClass,
    ) -> List[AthleteProfile]:
        """Return only athletes whose weight falls within the weight class range."""
        return [
            a
            for a in athletes
            if (
                a.weight is not None  # noqa: W504
                and weight_class.min_weight <= a.weight <= weight_class.max_weight
            )
        ]


class TimerService:
    """Manages the lifecycle of a TimerSession (start, pause, resume, finish)."""

    @staticmethod
    @transaction.atomic
    def start(session) -> None:
        """
        Start (or resume) a timer session.

        Sets started_at to now and transitions status to RUNNING.
        Raises ValueError if the session is not in IDLE or PAUSED state.
        """
        from django.utils import timezone

        if session.status not in (session.Status.IDLE, session.Status.PAUSED):
            raise ValueError(f"Cannot start a timer in '{session.status}' state.")
        session.started_at = timezone.now()
        session.status = session.Status.RUNNING
        session.save(update_fields=["started_at", "status"])

    @staticmethod
    @transaction.atomic
    def pause(session) -> None:
        """
        Pause a running timer session, accumulating elapsed seconds.

        Records paused_at, transitions to PAUSED, and adds the elapsed delta
        to elapsed_seconds so resume/finish can compute total time accurately.
        Raises ValueError if the session is not RUNNING.
        """
        from django.utils import timezone

        if session.status != session.Status.RUNNING:
            raise ValueError("Can only pause a running timer.")
        session.paused_at = timezone.now()
        session.status = session.Status.PAUSED
        delta = (session.paused_at - session.started_at).seconds
        session.elapsed_seconds += delta
        session.save(update_fields=["paused_at", "status", "elapsed_seconds"])

    @staticmethod
    @transaction.atomic
    def finish(session) -> None:
        """Mark a timer session as FINISHED regardless of its current state."""
        session.status = session.Status.FINISHED
        session.save(update_fields=["status"])
