"""
Tests for matches/services.py: MatchService.

Covers:
  - create_match: creates record, rejects self-match
  - add_event: records event, updates scores with F(), rejects non-participant, rejects finished match
  - finish_match: sets winner/is_finished, rejects invalid winner, rejects already-finished match
"""

import pytest

from matches.models import Match, MatchEvent
from matches.services import MatchService
from factories import AcademyFactory, AthleteProfileFactory, MatchFactory, UserFactory


@pytest.fixture
def match_academy(db):
    return AcademyFactory()


@pytest.fixture
def user_a(db):
    return UserFactory(username="svc_fighter_a")


@pytest.fixture
def user_b(db):
    return UserFactory(username="svc_fighter_b")


@pytest.fixture
def live_match(db, match_academy, user_a, user_b):
    """An unfinished match between user_a and user_b."""
    return Match.objects.create(
        academy=match_academy,
        athlete_a=user_a,
        athlete_b=user_b,
        is_finished=False,
    )


# ─── create_match ─────────────────────────────────────────────────────────────


class TestMatchServiceCreate:
    def test_create_match_saves_to_db(self, db, match_academy, user_a, user_b):
        match = MatchService.create_match(match_academy, user_a, user_b)
        assert match.pk is not None
        assert match.is_finished is False
        assert match.score_a == 0
        assert match.score_b == 0

    def test_create_match_custom_duration(self, db, match_academy, user_a, user_b):
        match = MatchService.create_match(match_academy, user_a, user_b, duration_seconds=600)
        assert match.duration_seconds == 600

    def test_create_match_self_raises(self, db, match_academy, user_a):
        with pytest.raises(ValueError, match="themselves"):
            MatchService.create_match(match_academy, user_a, user_a)


# ─── add_event ────────────────────────────────────────────────────────────────


class TestMatchServiceAddEvent:
    def test_add_points_event_increments_score_a(self, db, live_match, user_a):
        MatchService.add_event(
            match_pk=live_match.pk,
            athlete_id=user_a.pk,
            event_type=MatchEvent.TypeChoices.POINTS,
            timestamp=30,
            action_description="takedown",
            points_awarded=2,
        )
        live_match.refresh_from_db()
        assert live_match.score_a == 2
        assert live_match.score_b == 0

    def test_add_points_event_increments_score_b(self, db, live_match, user_b):
        MatchService.add_event(
            match_pk=live_match.pk,
            athlete_id=user_b.pk,
            event_type=MatchEvent.TypeChoices.POINTS,
            timestamp=60,
            action_description="sweep",
            points_awarded=2,
        )
        live_match.refresh_from_db()
        assert live_match.score_b == 2
        assert live_match.score_a == 0

    def test_add_multiple_events_accumulates_score(self, db, live_match, user_a):
        for pts in [2, 3]:
            MatchService.add_event(
                match_pk=live_match.pk,
                athlete_id=user_a.pk,
                event_type=MatchEvent.TypeChoices.POINTS,
                timestamp=10,
                action_description="points",
                points_awarded=pts,
            )
        live_match.refresh_from_db()
        assert live_match.score_a == 5

    def test_add_non_points_event_does_not_change_score(self, db, live_match, user_a):
        MatchService.add_event(
            match_pk=live_match.pk,
            athlete_id=user_a.pk,
            event_type=MatchEvent.TypeChoices.ADVANTAGE,
            timestamp=45,
            action_description="near sweep",
            points_awarded=0,
        )
        live_match.refresh_from_db()
        assert live_match.score_a == 0

    def test_add_event_creates_matchevent_record(self, db, live_match, user_a):
        MatchService.add_event(
            match_pk=live_match.pk,
            athlete_id=user_a.pk,
            event_type=MatchEvent.TypeChoices.SUBMISSION,
            timestamp=120,
            action_description="armbar",
        )
        assert MatchEvent.objects.filter(
            match=live_match, athlete=user_a, event_type="SUBMISSION"
        ).exists()

    def test_add_event_rejects_non_participant(self, db, live_match):
        outsider = UserFactory(username="outsider_evt")
        with pytest.raises(ValueError, match="not a participant"):
            MatchService.add_event(
                match_pk=live_match.pk,
                athlete_id=outsider.pk,
                event_type=MatchEvent.TypeChoices.POINTS,
                timestamp=10,
                action_description="takedown",
                points_awarded=2,
            )

    def test_add_event_rejects_finished_match(self, db, match_academy, user_a, user_b):
        finished = Match.objects.create(
            academy=match_academy,
            athlete_a=user_a,
            athlete_b=user_b,
            is_finished=True,
            winner=user_a,
        )
        with pytest.raises(ValueError, match="finished"):
            MatchService.add_event(
                match_pk=finished.pk,
                athlete_id=user_a.pk,
                event_type=MatchEvent.TypeChoices.POINTS,
                timestamp=10,
                action_description="takedown",
                points_awarded=2,
            )


# ─── finish_match ─────────────────────────────────────────────────────────────


class TestMatchServiceFinish:
    def test_finish_match_sets_winner_and_flag(self, db, live_match, user_a):
        result = MatchService.finish_match(live_match.pk, winner_id=user_a.pk)
        assert result.is_finished is True
        assert result.winner_id == user_a.pk

    def test_finish_match_with_athlete_b_as_winner(self, db, live_match, user_b):
        result = MatchService.finish_match(live_match.pk, winner_id=user_b.pk)
        assert result.winner_id == user_b.pk

    def test_finish_match_rejects_non_participant(self, db, live_match):
        stranger = UserFactory(username="stranger_finish")
        with pytest.raises(ValueError, match="participants"):
            MatchService.finish_match(live_match.pk, winner_id=stranger.pk)

    def test_finish_match_rejects_already_finished(self, db, match_academy, user_a, user_b):
        finished = Match.objects.create(
            academy=match_academy,
            athlete_a=user_a,
            athlete_b=user_b,
            is_finished=True,
            winner=user_a,
        )
        with pytest.raises(ValueError, match="already finished"):
            MatchService.finish_match(finished.pk, winner_id=user_b.pk)

    def test_finish_match_persists_in_db(self, db, live_match, user_a):
        MatchService.finish_match(live_match.pk, winner_id=user_a.pk)
        live_match.refresh_from_db()
        assert live_match.is_finished is True
        assert live_match.winner == user_a
