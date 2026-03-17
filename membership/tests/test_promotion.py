"""
Unit tests for PromotionService.

Run with:  pytest membership/tests/test_promotion.py
"""

from datetime import date, timedelta

import pytest

from membership.models import PromotionRequirement
from membership.services import PromotionService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def white_belt_requirement(db, academy):
    return PromotionRequirement.objects.create(
        belt="white",
        min_mat_hours=100.0,
        min_months_at_belt=12,
        min_stripes_before_promotion=4,
        academy=None,  # global requirement
    )


@pytest.fixture
def blue_belt_requirement(db, academy):
    return PromotionRequirement.objects.create(
        belt="blue",
        min_mat_hours=200.0,
        min_months_at_belt=18,
        min_stripes_before_promotion=4,
        academy=None,
    )


@pytest.fixture
def academy_white_requirement(db, academy):
    """Academy-specific override: stricter mat hours."""
    return PromotionRequirement.objects.create(
        belt="white",
        min_mat_hours=150.0,
        min_months_at_belt=12,
        min_stripes_before_promotion=4,
        academy=academy,
    )


# ---------------------------------------------------------------------------
# check_readiness — happy path
# ---------------------------------------------------------------------------


class TestPromotionReadinessEligible:
    def test_athlete_meeting_all_requirements_is_ready(
        self, make_athlete, belt_white, white_belt_requirement
    ):
        belt_awarded = date.today() - timedelta(days=400)  # ~13 months
        athlete = make_athlete(belt=belt_white, stripes=4)
        athlete.mat_hours = 120.0
        athlete.save()

        result = PromotionService.check_readiness(
            athlete, belt_awarded_date=belt_awarded
        )

        assert result.is_ready is True
        assert result.mat_hours_ok is True
        assert result.months_at_belt_ok is True
        assert result.stripes_ok is True

    def test_ready_result_contains_accurate_current_values(
        self, make_athlete, belt_white, white_belt_requirement
    ):
        belt_awarded = date.today() - timedelta(days=400)
        athlete = make_athlete(belt=belt_white, stripes=4)
        athlete.mat_hours = 110.0
        athlete.save()

        result = PromotionService.check_readiness(
            athlete, belt_awarded_date=belt_awarded
        )

        assert result.current_mat_hours == 110.0
        assert result.required_mat_hours == 100.0
        assert result.current_stripes == 4


# ---------------------------------------------------------------------------
# check_readiness — individual gaps
# ---------------------------------------------------------------------------


class TestPromotionReadinessGaps:
    def test_insufficient_mat_hours(
        self, make_athlete, belt_white, white_belt_requirement
    ):
        belt_awarded = date.today() - timedelta(days=400)
        athlete = make_athlete(belt=belt_white, stripes=4)
        athlete.mat_hours = 50.0  # below 100 required
        athlete.save()

        result = PromotionService.check_readiness(
            athlete, belt_awarded_date=belt_awarded
        )

        assert result.is_ready is False
        assert result.mat_hours_ok is False
        assert "mat hours" in result.message

    def test_insufficient_time_at_belt(
        self, make_athlete, belt_white, white_belt_requirement
    ):
        belt_awarded = date.today() - timedelta(days=30)  # only 1 month
        athlete = make_athlete(belt=belt_white, stripes=4)
        athlete.mat_hours = 120.0
        athlete.save()

        result = PromotionService.check_readiness(
            athlete, belt_awarded_date=belt_awarded
        )

        assert result.is_ready is False
        assert result.months_at_belt_ok is False
        assert "months at belt" in result.message

    def test_insufficient_stripes(
        self, make_athlete, belt_white, white_belt_requirement
    ):
        belt_awarded = date.today() - timedelta(days=400)
        athlete = make_athlete(belt=belt_white, stripes=2)  # only 2 stripes
        athlete.mat_hours = 120.0
        athlete.save()

        result = PromotionService.check_readiness(
            athlete, belt_awarded_date=belt_awarded
        )

        assert result.is_ready is False
        assert result.stripes_ok is False
        assert "stripes" in result.message

    def test_all_gaps_present(self, make_athlete, belt_white, white_belt_requirement):
        belt_awarded = date.today() - timedelta(days=10)
        athlete = make_athlete(belt=belt_white, stripes=1)
        athlete.mat_hours = 5.0
        athlete.save()

        result = PromotionService.check_readiness(
            athlete, belt_awarded_date=belt_awarded
        )

        assert result.is_ready is False
        assert result.mat_hours_ok is False
        assert result.months_at_belt_ok is False
        assert result.stripes_ok is False


# ---------------------------------------------------------------------------
# No requirement configured
# ---------------------------------------------------------------------------


class TestNoRequirementConfigured:
    def test_returns_not_ready_when_no_requirement_exists(
        self, make_athlete, belt_blue
    ):
        """No PromotionRequirement for blue belt — should return not ready gracefully."""
        athlete = make_athlete(belt=belt_blue, stripes=4)
        athlete.mat_hours = 300.0
        athlete.save()

        result = PromotionService.check_readiness(athlete)

        assert result.is_ready is False
        assert "No promotion requirements configured" in result.message


# ---------------------------------------------------------------------------
# Academy-specific vs global requirements
# ---------------------------------------------------------------------------


class TestAcademySpecificRequirement:
    def test_academy_specific_requirement_takes_precedence(
        self,
        make_athlete,
        belt_white,
        white_belt_requirement,
        academy_white_requirement,
        academy,
    ):
        """Academy override requires 150 mat hours; athlete only has 110 — not ready."""
        belt_awarded = date.today() - timedelta(days=400)
        athlete = make_athlete(belt=belt_white, stripes=4)
        athlete.mat_hours = 110.0
        athlete.save()

        # Without academy_id, uses global (100 hours) → ready
        result_global = PromotionService.check_readiness(
            athlete, belt_awarded_date=belt_awarded
        )
        assert result_global.is_ready is True

        # With academy_id, uses academy-specific (150 hours) → not ready
        result_academy = PromotionService.check_readiness(
            athlete, belt_awarded_date=belt_awarded, academy_id=academy.pk
        )
        assert result_academy.is_ready is False
        assert result_academy.mat_hours_ok is False

    def test_falls_back_to_global_when_no_academy_override(
        self, make_athlete, belt_white, white_belt_requirement, academy
    ):
        """No academy-specific override exists → falls back to global requirement."""
        belt_awarded = date.today() - timedelta(days=400)
        athlete = make_athlete(belt=belt_white, stripes=4)
        athlete.mat_hours = 120.0
        athlete.save()

        # Academy has no specific override, but global exists
        result = PromotionService.check_readiness(
            athlete, belt_awarded_date=belt_awarded, academy_id=academy.pk
        )
        assert result.is_ready is True


# ---------------------------------------------------------------------------
# Months calculation
# ---------------------------------------------------------------------------


class TestMonthsAtBelt:
    def test_no_belt_awarded_date_gives_zero_months(
        self, make_athlete, belt_white, white_belt_requirement
    ):
        athlete = make_athlete(belt=belt_white, stripes=4)
        athlete.mat_hours = 120.0
        athlete.save()

        result = PromotionService.check_readiness(athlete, belt_awarded_date=None)

        assert result.current_months == 0
        assert result.months_at_belt_ok is False  # requirement is 12 months

    def test_exactly_at_minimum_months_is_eligible(
        self, make_athlete, belt_white, white_belt_requirement
    ):
        # Exactly 12 months ago
        belt_awarded = date.today().replace(year=date.today().year - 1)
        athlete = make_athlete(belt=belt_white, stripes=4)
        athlete.mat_hours = 120.0
        athlete.save()

        result = PromotionService.check_readiness(
            athlete, belt_awarded_date=belt_awarded
        )

        assert result.months_at_belt_ok is True
