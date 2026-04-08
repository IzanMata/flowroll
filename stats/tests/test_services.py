"""
Tests for StatsService — recompute_for_athlete, get_or_create_stats,
get_academy_leaderboard.
"""

import pytest

from factories import AcademyFactory, AthleteProfileFactory, MatchFactory
from matches.models import Match, MatchEvent
from stats.models import AthleteMatchStats
from stats.services import StatsService


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def stats_academy(db):
    return AcademyFactory()


@pytest.fixture
def athlete_a(stats_academy):
    return AthleteProfileFactory(academy=stats_academy)


@pytest.fixture
def athlete_b(stats_academy):
    return AthleteProfileFactory(academy=stats_academy)


def _finished_match(academy, user_a, user_b, winner=None):
    """Helper: create a finished Match between two users."""
    return Match.objects.create(
        academy=academy,
        athlete_a=user_a,
        athlete_b=user_b,
        is_finished=True,
        winner=winner,
    )


def _add_points_event(match, athlete_user, points):
    MatchEvent.objects.create(
        match=match,
        athlete=athlete_user,
        event_type=MatchEvent.TypeChoices.POINTS,
        points_awarded=points,
        timestamp=10,
    )


def _add_submission_event(match, athlete_user):
    MatchEvent.objects.create(
        match=match,
        athlete=athlete_user,
        event_type=MatchEvent.TypeChoices.SUBMISSION,
        points_awarded=0,
        timestamp=60,
    )


# ─── recompute_for_athlete ────────────────────────────────────────────────────


@pytest.mark.django_db
class TestRecomputeForAthlete:
    def test_no_matches_produces_zeros(self, athlete_a):
        stats = StatsService.recompute_for_athlete(athlete_a)
        assert stats.total_matches == 0
        assert stats.wins == 0
        assert stats.losses == 0
        assert stats.draws == 0
        assert stats.total_points_scored == 0
        assert stats.total_points_conceded == 0
        assert stats.submissions_won == 0

    def test_counts_wins(self, stats_academy, athlete_a, athlete_b):
        _finished_match(stats_academy, athlete_a.user, athlete_b.user, winner=athlete_a.user)
        _finished_match(stats_academy, athlete_a.user, athlete_b.user, winner=athlete_a.user)
        stats = StatsService.recompute_for_athlete(athlete_a)
        assert stats.wins == 2
        assert stats.total_matches == 2

    def test_counts_losses(self, stats_academy, athlete_a, athlete_b):
        _finished_match(stats_academy, athlete_a.user, athlete_b.user, winner=athlete_b.user)
        stats = StatsService.recompute_for_athlete(athlete_a)
        assert stats.losses == 1
        assert stats.wins == 0

    def test_counts_draws(self, stats_academy, athlete_a, athlete_b):
        _finished_match(stats_academy, athlete_a.user, athlete_b.user, winner=None)
        stats = StatsService.recompute_for_athlete(athlete_a)
        assert stats.draws == 1
        assert stats.wins == 0
        assert stats.losses == 0

    def test_counts_mix_win_loss_draw(self, stats_academy, athlete_a, athlete_b):
        _finished_match(stats_academy, athlete_a.user, athlete_b.user, winner=athlete_a.user)
        _finished_match(stats_academy, athlete_a.user, athlete_b.user, winner=athlete_b.user)
        _finished_match(stats_academy, athlete_a.user, athlete_b.user, winner=None)
        stats = StatsService.recompute_for_athlete(athlete_a)
        assert stats.total_matches == 3
        assert stats.wins == 1
        assert stats.losses == 1
        assert stats.draws == 1

    def test_unfinished_matches_not_counted(self, stats_academy, athlete_a, athlete_b):
        Match.objects.create(
            academy=stats_academy,
            athlete_a=athlete_a.user,
            athlete_b=athlete_b.user,
            is_finished=False,
        )
        stats = StatsService.recompute_for_athlete(athlete_a)
        assert stats.total_matches == 0

    def test_counts_points_scored(self, stats_academy, athlete_a, athlete_b):
        match = _finished_match(stats_academy, athlete_a.user, athlete_b.user)
        _add_points_event(match, athlete_a.user, 2)
        _add_points_event(match, athlete_a.user, 3)
        stats = StatsService.recompute_for_athlete(athlete_a)
        assert stats.total_points_scored == 5

    def test_counts_points_conceded(self, stats_academy, athlete_a, athlete_b):
        match = _finished_match(stats_academy, athlete_a.user, athlete_b.user)
        _add_points_event(match, athlete_b.user, 4)
        stats = StatsService.recompute_for_athlete(athlete_a)
        assert stats.total_points_conceded == 4

    def test_points_scored_and_conceded_independent(self, stats_academy, athlete_a, athlete_b):
        match = _finished_match(stats_academy, athlete_a.user, athlete_b.user)
        _add_points_event(match, athlete_a.user, 2)
        _add_points_event(match, athlete_b.user, 4)
        stats = StatsService.recompute_for_athlete(athlete_a)
        assert stats.total_points_scored == 2
        assert stats.total_points_conceded == 4

    def test_counts_submissions_won(self, stats_academy, athlete_a, athlete_b):
        match = _finished_match(
            stats_academy, athlete_a.user, athlete_b.user, winner=athlete_a.user
        )
        _add_submission_event(match, athlete_a.user)
        stats = StatsService.recompute_for_athlete(athlete_a)
        assert stats.submissions_won == 1

    def test_submission_only_counted_when_athlete_won(self, stats_academy, athlete_a, athlete_b):
        """Submission event where opponent wins should not count for athlete_a."""
        match = _finished_match(
            stats_academy, athlete_a.user, athlete_b.user, winner=athlete_b.user
        )
        _add_submission_event(match, athlete_a.user)
        stats = StatsService.recompute_for_athlete(athlete_a)
        assert stats.submissions_won == 0

    def test_recompute_is_idempotent(self, stats_academy, athlete_a, athlete_b):
        _finished_match(stats_academy, athlete_a.user, athlete_b.user, winner=athlete_a.user)
        StatsService.recompute_for_athlete(athlete_a)
        StatsService.recompute_for_athlete(athlete_a)
        count = AthleteMatchStats.objects.filter(athlete=athlete_a).count()
        assert count == 1

    def test_recompute_updates_existing_stats(self, stats_academy, athlete_a, athlete_b):
        _finished_match(stats_academy, athlete_a.user, athlete_b.user, winner=athlete_a.user)
        StatsService.recompute_for_athlete(athlete_a)
        _finished_match(stats_academy, athlete_a.user, athlete_b.user, winner=athlete_a.user)
        stats = StatsService.recompute_for_athlete(athlete_a)
        assert stats.total_matches == 2
        assert stats.wins == 2

    def test_only_counts_matches_for_this_athlete(self, stats_academy, athlete_a, athlete_b):
        """Matches not involving athlete_a should be ignored."""
        third = AthleteProfileFactory(academy=stats_academy)
        _finished_match(stats_academy, athlete_b.user, third.user, winner=athlete_b.user)
        stats = StatsService.recompute_for_athlete(athlete_a)
        assert stats.total_matches == 0


# ─── get_or_create_stats ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestGetOrCreateStats:
    def test_creates_empty_stats_if_none_exist(self, athlete_a):
        assert not AthleteMatchStats.objects.filter(athlete=athlete_a).exists()
        stats = StatsService.get_or_create_stats(athlete_a)
        assert stats.total_matches == 0
        assert AthleteMatchStats.objects.filter(athlete=athlete_a).exists()

    def test_returns_existing_stats(self, athlete_a):
        existing = AthleteMatchStats.objects.create(athlete=athlete_a, total_matches=5, wins=3)
        stats = StatsService.get_or_create_stats(athlete_a)
        assert stats.pk == existing.pk
        assert stats.total_matches == 5

    def test_idempotent_no_duplicate(self, athlete_a):
        StatsService.get_or_create_stats(athlete_a)
        StatsService.get_or_create_stats(athlete_a)
        assert AthleteMatchStats.objects.filter(athlete=athlete_a).count() == 1


# ─── get_academy_leaderboard ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestGetAcademyLeaderboard:
    def test_returns_athletes_ranked_by_wins(self, stats_academy):
        a1 = AthleteProfileFactory(academy=stats_academy)
        a2 = AthleteProfileFactory(academy=stats_academy)
        AthleteMatchStats.objects.create(athlete=a1, total_matches=3, wins=1)
        AthleteMatchStats.objects.create(athlete=a2, total_matches=3, wins=3)
        board = StatsService.get_academy_leaderboard(stats_academy.pk)
        assert board[0].athlete == a2
        assert board[1].athlete == a1

    def test_excludes_athletes_with_no_matches(self, stats_academy):
        a1 = AthleteProfileFactory(academy=stats_academy)
        a2 = AthleteProfileFactory(academy=stats_academy)
        AthleteMatchStats.objects.create(athlete=a1, total_matches=0, wins=0)
        AthleteMatchStats.objects.create(athlete=a2, total_matches=2, wins=2)
        board = StatsService.get_academy_leaderboard(stats_academy.pk)
        assert len(board) == 1
        assert board[0].athlete == a2

    def test_respects_limit(self, stats_academy):
        for _ in range(5):
            a = AthleteProfileFactory(academy=stats_academy)
            AthleteMatchStats.objects.create(athlete=a, total_matches=1, wins=1)
        board = StatsService.get_academy_leaderboard(stats_academy.pk, limit=3)
        assert len(board) == 3

    def test_excludes_other_academy_athletes(self, stats_academy):
        other = AcademyFactory()
        a1 = AthleteProfileFactory(academy=stats_academy)
        a2 = AthleteProfileFactory(academy=other)
        AthleteMatchStats.objects.create(athlete=a1, total_matches=2, wins=2)
        AthleteMatchStats.objects.create(athlete=a2, total_matches=2, wins=2)
        board = StatsService.get_academy_leaderboard(stats_academy.pk)
        assert len(board) == 1
        assert board[0].athlete == a1

    def test_empty_academy_returns_empty_list(self, stats_academy):
        board = StatsService.get_academy_leaderboard(stats_academy.pk)
        assert board == []
