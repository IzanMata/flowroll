"""
Tests for the AthleteMatchStats model.
"""

import pytest

from factories import AthleteProfileFactory
from stats.models import AthleteMatchStats


@pytest.mark.django_db
class TestAthleteMatchStats:
    def test_str_shows_wins_losses_draws(self):
        athlete = AthleteProfileFactory()
        stats = AthleteMatchStats.objects.create(
            athlete=athlete,
            total_matches=5,
            wins=3,
            losses=1,
            draws=1,
        )
        result = str(stats)
        assert "3W" in result
        assert "1L" in result
        assert "1D" in result

    def test_win_rate_zero_when_no_matches(self):
        athlete = AthleteProfileFactory()
        stats = AthleteMatchStats.objects.create(athlete=athlete)
        assert stats.win_rate == 0.0

    def test_win_rate_calculated_correctly(self):
        athlete = AthleteProfileFactory()
        stats = AthleteMatchStats.objects.create(
            athlete=athlete,
            total_matches=4,
            wins=3,
            losses=1,
            draws=0,
        )
        assert stats.win_rate == pytest.approx(0.75)

    def test_win_rate_perfect(self):
        athlete = AthleteProfileFactory()
        stats = AthleteMatchStats.objects.create(
            athlete=athlete,
            total_matches=10,
            wins=10,
            losses=0,
            draws=0,
        )
        assert stats.win_rate == 1.0

    def test_default_values_are_zero(self):
        athlete = AthleteProfileFactory()
        stats = AthleteMatchStats.objects.create(athlete=athlete)
        assert stats.total_matches == 0
        assert stats.wins == 0
        assert stats.losses == 0
        assert stats.draws == 0
        assert stats.total_points_scored == 0
        assert stats.total_points_conceded == 0
        assert stats.submissions_won == 0

    def test_one_to_one_with_athlete(self):
        from django.db import IntegrityError

        athlete = AthleteProfileFactory()
        AthleteMatchStats.objects.create(athlete=athlete)
        with pytest.raises(IntegrityError):
            AthleteMatchStats.objects.create(athlete=athlete)
