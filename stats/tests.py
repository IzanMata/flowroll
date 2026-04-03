"""
Tests for the stats app: models, services, and API endpoints.

Covers:
  - AthleteMatchStats model (win_rate, str)
  - StatsService.recompute_for_athlete (win/loss/draw/points/submissions)
  - StatsService.get_academy_leaderboard
  - AthleteStatsViewSet: by_athlete, recompute, leaderboard
"""

import pytest
from rest_framework import status

from matches.models import Match, MatchEvent
from stats.models import AthleteMatchStats
from stats.services import StatsService
from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteMatchStatsFactory,
    AthleteProfileFactory,
    UserFactory,
)

STATS_URL = "/api/v1/stats/"


# ─── Model tests ──────────────────────────────────────────────────────────────


class TestAthleteMatchStatsModel:
    def test_create_stats(self, db):
        stats = AthleteMatchStatsFactory(total_matches=10, wins=6, losses=4)
        assert stats.pk is not None
        assert "6W" in str(stats)
        assert "4L" in str(stats)

    def test_win_rate_with_matches(self, db):
        stats = AthleteMatchStatsFactory(total_matches=10, wins=7, losses=3)
        assert stats.win_rate == pytest.approx(0.7)

    def test_win_rate_with_no_matches(self, db):
        stats = AthleteMatchStatsFactory(total_matches=0, wins=0, losses=0)
        assert stats.win_rate == 0.0

    def test_one_to_one_with_athlete(self, db):
        from django.db import IntegrityError
        athlete = AthleteProfileFactory()
        AthleteMatchStatsFactory(athlete=athlete)
        with pytest.raises(IntegrityError):
            AthleteMatchStatsFactory(athlete=athlete)


# ─── Service tests ────────────────────────────────────────────────────────────


def _make_match(academy, athlete_a_user, athlete_b_user, winner_user=None, finished=True):
    return Match.objects.create(
        academy=academy,
        athlete_a=athlete_a_user,
        athlete_b=athlete_b_user,
        is_finished=finished,
        winner=winner_user,
    )


class TestStatsServiceRecompute:
    def test_recompute_no_matches(self, db, academy):
        athlete = AthleteProfileFactory(academy=academy)
        stats = StatsService.recompute_for_athlete(athlete)
        assert stats.total_matches == 0
        assert stats.wins == 0
        assert stats.losses == 0

    def test_recompute_counts_wins_and_losses(self, db, academy):
        athlete = AthleteProfileFactory(academy=academy)
        opponent = AthleteProfileFactory(academy=academy)

        # Win
        _make_match(academy, athlete.user, opponent.user, winner_user=athlete.user)
        # Loss
        _make_match(academy, athlete.user, opponent.user, winner_user=opponent.user)

        stats = StatsService.recompute_for_athlete(athlete)
        assert stats.total_matches == 2
        assert stats.wins == 1
        assert stats.losses == 1

    def test_recompute_counts_draws(self, db, academy):
        athlete = AthleteProfileFactory(academy=academy)
        opponent = AthleteProfileFactory(academy=academy)
        # Draw: is_finished=True, winner=None
        _make_match(academy, athlete.user, opponent.user, winner_user=None)

        stats = StatsService.recompute_for_athlete(athlete)
        assert stats.draws == 1
        assert stats.wins == 0
        assert stats.losses == 0

    def test_recompute_counts_as_athlete_b(self, db, academy):
        athlete = AthleteProfileFactory(academy=academy)
        opponent = AthleteProfileFactory(academy=academy)
        # athlete is athlete_b here
        _make_match(academy, opponent.user, athlete.user, winner_user=athlete.user)

        stats = StatsService.recompute_for_athlete(athlete)
        assert stats.total_matches == 1
        assert stats.wins == 1

    def test_recompute_ignores_unfinished_matches(self, db, academy):
        athlete = AthleteProfileFactory(academy=academy)
        opponent = AthleteProfileFactory(academy=academy)
        _make_match(academy, athlete.user, opponent.user, finished=False)

        stats = StatsService.recompute_for_athlete(athlete)
        assert stats.total_matches == 0

    def test_recompute_counts_points_scored(self, db, academy):
        athlete = AthleteProfileFactory(academy=academy)
        opponent = AthleteProfileFactory(academy=academy)
        match = _make_match(academy, athlete.user, opponent.user, winner_user=athlete.user)
        MatchEvent.objects.create(
            match=match,
            athlete=athlete.user,
            timestamp=30,
            event_type=MatchEvent.TypeChoices.POINTS,
            points_awarded=3,
            action_description="guard pass",
        )

        stats = StatsService.recompute_for_athlete(athlete)
        assert stats.total_points_scored == 3

    def test_recompute_counts_points_conceded(self, db, academy):
        athlete = AthleteProfileFactory(academy=academy)
        opponent = AthleteProfileFactory(academy=academy)
        match = _make_match(academy, athlete.user, opponent.user, winner_user=opponent.user)
        MatchEvent.objects.create(
            match=match,
            athlete=opponent.user,
            timestamp=30,
            event_type=MatchEvent.TypeChoices.POINTS,
            points_awarded=4,
            action_description="mount",
        )

        stats = StatsService.recompute_for_athlete(athlete)
        assert stats.total_points_conceded == 4

    def test_recompute_counts_submissions_won(self, db, academy):
        athlete = AthleteProfileFactory(academy=academy)
        opponent = AthleteProfileFactory(academy=academy)
        match = _make_match(academy, athlete.user, opponent.user, winner_user=athlete.user)
        MatchEvent.objects.create(
            match=match,
            athlete=athlete.user,
            timestamp=90,
            event_type=MatchEvent.TypeChoices.SUBMISSION,
            points_awarded=0,
            action_description="armbar",
        )

        stats = StatsService.recompute_for_athlete(athlete)
        assert stats.submissions_won == 1

    def test_recompute_updates_existing_record(self, db, academy):
        athlete = AthleteProfileFactory(academy=academy)
        opponent = AthleteProfileFactory(academy=academy)
        # First compute
        StatsService.recompute_for_athlete(athlete)
        # Add a match
        _make_match(academy, athlete.user, opponent.user, winner_user=athlete.user)
        stats = StatsService.recompute_for_athlete(athlete)
        assert stats.wins == 1
        # Only one record should exist
        assert AthleteMatchStats.objects.filter(athlete=athlete).count() == 1

    def test_get_or_create_stats_creates_empty_record(self, db):
        athlete = AthleteProfileFactory()
        stats = StatsService.get_or_create_stats(athlete)
        assert stats.pk is not None
        assert stats.total_matches == 0


class TestStatsServiceLeaderboard:
    def test_leaderboard_returns_top_athletes(self, db, academy):
        a1 = AthleteProfileFactory(academy=academy)
        a2 = AthleteProfileFactory(academy=academy)
        opponent = AthleteProfileFactory(academy=academy)
        _make_match(academy, a1.user, opponent.user, winner_user=a1.user)
        _make_match(academy, a1.user, opponent.user, winner_user=a1.user)
        _make_match(academy, a2.user, opponent.user, winner_user=a2.user)
        StatsService.recompute_for_athlete(a1)
        StatsService.recompute_for_athlete(a2)

        leaderboard = StatsService.get_academy_leaderboard(academy.pk, limit=10)
        assert len(leaderboard) == 2
        assert leaderboard[0].athlete == a1  # 2 wins

    def test_leaderboard_excludes_athletes_with_no_matches(self, db, academy):
        idle = AthleteProfileFactory(academy=academy)
        StatsService.recompute_for_athlete(idle)

        leaderboard = StatsService.get_academy_leaderboard(academy.pk)
        assert all(s.athlete != idle for s in leaderboard)


# ─── API tests ────────────────────────────────────────────────────────────────


@pytest.fixture
def stats_academy(db):
    return AcademyFactory(name="Stats Academy")


@pytest.fixture
def member_user(db, stats_academy):
    user = UserFactory(username="stats_member")
    AcademyMembershipFactory(user=user, academy=stats_academy, role="STUDENT", is_active=True)
    return user


@pytest.fixture
def prof_user(db, stats_academy):
    user = UserFactory(username="stats_prof")
    AcademyMembershipFactory(user=user, academy=stats_academy, role="PROFESSOR", is_active=True)
    return user


class TestStatsAPIAuth:
    def test_unauthenticated_returns_401(self, api_client, stats_academy):
        r = api_client.get(f"{STATS_URL}?academy={stats_academy.pk}")
        assert r.status_code == status.HTTP_401_UNAUTHORIZED


class TestStatsAPIList:
    def test_member_can_list_stats(self, api_client, member_user, stats_academy):
        athlete = AthleteProfileFactory(academy=stats_academy)
        AthleteMatchStatsFactory(athlete=athlete)
        api_client.force_authenticate(user=member_user)
        r = api_client.get(f"{STATS_URL}?academy={stats_academy.pk}")
        assert r.status_code == status.HTTP_200_OK

    def test_no_academy_returns_empty(self, api_client, member_user):
        api_client.force_authenticate(user=member_user)
        r = api_client.get(STATS_URL)
        assert r.status_code == status.HTTP_200_OK
        assert r.data["count"] == 0

    def test_non_member_cannot_list(self, api_client, stats_academy):
        outsider = UserFactory()
        api_client.force_authenticate(user=outsider)
        r = api_client.get(f"{STATS_URL}?academy={stats_academy.pk}")
        assert r.status_code == status.HTTP_403_FORBIDDEN


class TestStatsAPIByAthlete:
    def test_by_athlete_returns_stats(self, api_client, member_user, stats_academy):
        athlete = AthleteProfileFactory(academy=stats_academy)
        AthleteMatchStatsFactory(athlete=athlete, wins=5, losses=2, total_matches=7)
        api_client.force_authenticate(user=member_user)
        r = api_client.get(f"{STATS_URL}athlete/{athlete.pk}/?academy={stats_academy.pk}")
        assert r.status_code == status.HTTP_200_OK
        assert r.data["wins"] == 5

    def test_by_athlete_404_when_no_stats(self, api_client, member_user, stats_academy):
        athlete = AthleteProfileFactory(academy=stats_academy)
        api_client.force_authenticate(user=member_user)
        r = api_client.get(f"{STATS_URL}athlete/{athlete.pk}/?academy={stats_academy.pk}")
        assert r.status_code == status.HTTP_404_NOT_FOUND


class TestStatsAPIRecompute:
    def test_professor_can_recompute(self, api_client, prof_user, stats_academy):
        athlete = AthleteProfileFactory(academy=stats_academy)
        api_client.force_authenticate(user=prof_user)
        r = api_client.post(
            f"{STATS_URL}athlete/{athlete.pk}/recompute/?academy={stats_academy.pk}"
        )
        assert r.status_code == status.HTTP_200_OK
        assert AthleteMatchStats.objects.filter(athlete=athlete).exists()

    def test_student_cannot_recompute(self, api_client, member_user, stats_academy):
        athlete = AthleteProfileFactory(academy=stats_academy)
        api_client.force_authenticate(user=member_user)
        r = api_client.post(
            f"{STATS_URL}athlete/{athlete.pk}/recompute/?academy={stats_academy.pk}"
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN


class TestStatsAPILeaderboard:
    def test_leaderboard_returns_ranked_list(self, api_client, member_user, stats_academy):
        a1 = AthleteProfileFactory(academy=stats_academy)
        a2 = AthleteProfileFactory(academy=stats_academy)
        AthleteMatchStatsFactory(athlete=a1, wins=10, total_matches=12)
        AthleteMatchStatsFactory(athlete=a2, wins=5, total_matches=8)
        api_client.force_authenticate(user=member_user)
        r = api_client.get(f"{STATS_URL}leaderboard/?academy={stats_academy.pk}")
        assert r.status_code == status.HTTP_200_OK
        assert r.data[0]["wins"] >= r.data[1]["wins"]

    def test_leaderboard_requires_academy(self, api_client, member_user):
        api_client.force_authenticate(user=member_user)
        r = api_client.get(f"{STATS_URL}leaderboard/")
        assert r.status_code == status.HTTP_400_BAD_REQUEST
