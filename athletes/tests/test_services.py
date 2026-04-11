"""
Tests for PromotionService — evaluation logic, requirement resolution, and
academy-wide readiness listing.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from athletes.services import PromotionReadiness, PromotionService
from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    PromotionRequirementFactory,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def academy(db):
    return AcademyFactory()


@pytest.fixture
def athlete(db, academy):
    return AthleteProfileFactory(
        academy=academy,
        belt="white",
        stripes=4,
        mat_hours=200.0,
        belt_awarded_at=timezone.now() - timedelta(days=400),
    )


@pytest.fixture
def global_req(db):
    """Global requirement for white→blue: 100h, 6 months, 4 stripes."""
    return PromotionRequirementFactory(
        academy=None,
        belt="blue",
        min_mat_hours=100.0,
        min_months_at_belt=6,
        min_stripes_before_promotion=4,
    )


@pytest.fixture
def academy_req(db, academy):
    """Academy-specific requirement for white→blue: 50h, 3 months, 3 stripes."""
    return PromotionRequirementFactory(
        academy=academy,
        belt="blue",
        min_mat_hours=50.0,
        min_months_at_belt=3,
        min_stripes_before_promotion=3,
    )


# ─── PromotionService.evaluate ─────────────────────────────────────────────────


class TestPromotionServiceEvaluate:
    def test_returns_dataclass(self, db, athlete, global_req):
        result = PromotionService.evaluate(athlete)
        assert isinstance(result, PromotionReadiness)

    def test_ready_when_all_criteria_met(self, db, athlete, global_req):
        result = PromotionService.evaluate(athlete)
        assert result.is_ready is True
        assert result.mat_hours_ok is True
        assert result.months_ok is True
        assert result.stripes_ok is True

    def test_not_ready_insufficient_mat_hours(self, db, academy, global_req):
        athlete = AthleteProfileFactory(
            academy=academy,
            belt="white",
            stripes=4,
            mat_hours=50.0,  # below 100h requirement
            belt_awarded_at=timezone.now() - timedelta(days=400),
        )
        result = PromotionService.evaluate(athlete)
        assert result.is_ready is False
        assert result.mat_hours_ok is False
        assert result.mat_hours_current == 50.0
        assert result.mat_hours_required == 100.0

    def test_not_ready_insufficient_months(self, db, academy, global_req):
        athlete = AthleteProfileFactory(
            academy=academy,
            belt="white",
            stripes=4,
            mat_hours=200.0,
            belt_awarded_at=timezone.now() - timedelta(days=30),  # ~1 month
        )
        result = PromotionService.evaluate(athlete)
        assert result.is_ready is False
        assert result.months_ok is False
        assert result.months_required == 6

    def test_not_ready_insufficient_stripes(self, db, academy, global_req):
        athlete = AthleteProfileFactory(
            academy=academy,
            belt="white",
            stripes=2,
            mat_hours=200.0,
            belt_awarded_at=timezone.now() - timedelta(days=400),
        )
        result = PromotionService.evaluate(athlete)
        assert result.is_ready is False
        assert result.stripes_ok is False
        assert result.stripes_current == 2
        assert result.stripes_required == 4

    def test_no_belt_awarded_at_means_zero_months(self, db, academy, global_req):
        athlete = AthleteProfileFactory(
            academy=academy,
            belt="white",
            stripes=4,
            mat_hours=200.0,
            belt_awarded_at=None,
        )
        result = PromotionService.evaluate(athlete)
        assert result.months_current == 0.0
        assert result.months_ok is False

    def test_black_belt_no_next_belt(self, db):
        athlete = AthleteProfileFactory(belt="black")
        result = PromotionService.evaluate(athlete)
        assert result.next_belt is None
        assert result.is_ready is False
        assert result.requirement_found is False

    def test_no_requirement_means_not_ready(self, db, academy):
        athlete = AthleteProfileFactory(
            academy=academy, belt="white", stripes=4, mat_hours=200.0
        )
        # No PromotionRequirement exists
        result = PromotionService.evaluate(athlete)
        assert result.requirement_found is False
        assert result.is_ready is False

    def test_next_belt_fields_are_populated(self, db, athlete, global_req):
        result = PromotionService.evaluate(athlete)
        assert result.current_belt == "white"
        assert result.next_belt == "blue"
        assert result.athlete_id == athlete.pk


# ─── Requirement resolution (academy-specific vs global) ───────────────────────


class TestRequirementResolution:
    def test_academy_specific_takes_precedence(self, db, athlete, global_req, academy_req):
        req = PromotionService.get_requirement(athlete, "blue")
        assert req.pk == academy_req.pk

    def test_falls_back_to_global_when_no_academy_req(self, db, athlete, global_req):
        req = PromotionService.get_requirement(athlete, "blue")
        assert req.pk == global_req.pk

    def test_returns_none_when_no_requirement_exists(self, db, athlete):
        req = PromotionService.get_requirement(athlete, "blue")
        assert req is None

    def test_academy_req_used_for_evaluation(self, db, athlete, global_req, academy_req):
        # Academy req is easier (50h / 3mo / 3 stripes), athlete has 200h / 400d / 4 stripes
        result = PromotionService.evaluate(athlete)
        assert result.is_ready is True
        assert result.mat_hours_required == 50.0
        assert result.months_required == 3


# ─── Belt progression map ──────────────────────────────────────────────────────


class TestBeltProgression:
    @pytest.mark.parametrize("current,expected_next", [
        ("white", "blue"),
        ("blue", "purple"),
        ("purple", "brown"),
        ("brown", "black"),
        ("black", None),
    ])
    def test_progression_map(self, db, current, expected_next):
        athlete = AthleteProfileFactory(belt=current)
        result = PromotionService.evaluate(athlete)
        assert result.next_belt == expected_next


# ─── PromotionService.get_academy_readiness ────────────────────────────────────


class TestGetAcademyReadiness:
    def test_returns_list_for_all_athletes(self, db, academy, global_req):
        a1 = AthleteProfileFactory(
            academy=academy, belt="white", stripes=4, mat_hours=200.0,
            belt_awarded_at=timezone.now() - timedelta(days=400),
        )
        a2 = AthleteProfileFactory(
            academy=academy, belt="white", stripes=2, mat_hours=50.0,
            belt_awarded_at=timezone.now() - timedelta(days=30),
        )
        results = PromotionService.get_academy_readiness(academy.pk)
        ids = {r.athlete_id for r in results}
        assert a1.pk in ids
        assert a2.pk in ids

    def test_empty_academy_returns_empty_list(self, db):
        empty = AcademyFactory()
        assert PromotionService.get_academy_readiness(empty.pk) == []

    def test_excludes_athletes_from_other_academies(self, db, academy, global_req):
        AthleteProfileFactory(academy=academy, belt="white", stripes=4, mat_hours=200.0)
        other_academy = AcademyFactory()
        other_athlete = AthleteProfileFactory(
            academy=other_academy, belt="white", stripes=4, mat_hours=200.0
        )
        results = PromotionService.get_academy_readiness(academy.pk)
        ids = {r.athlete_id for r in results}
        assert other_athlete.pk not in ids

    def test_ready_and_not_ready_mixed(self, db, academy, global_req):
        AthleteProfileFactory(
            academy=academy, belt="white", stripes=4, mat_hours=200.0,
            belt_awarded_at=timezone.now() - timedelta(days=400),
        )
        AthleteProfileFactory(
            academy=academy, belt="white", stripes=0, mat_hours=5.0,
            belt_awarded_at=None,
        )
        results = PromotionService.get_academy_readiness(academy.pk)
        ready = [r for r in results if r.is_ready]
        not_ready = [r for r in results if not r.is_ready]
        assert len(ready) == 1
        assert len(not_ready) == 1


# ─── award_stripe → promotion-ready notification ───────────────────────────────


class TestAwardStripePromotionNotification:
    def test_notification_fired_on_4th_stripe_if_ready(self, db, academy, global_req):
        from athletes.services import AthleteProfileService
        from notifications.models import Notification

        prof = AthleteProfileFactory(academy=academy, role="PROFESSOR")
        AcademyMembershipFactory(
            user=prof.user, academy=academy, role="PROFESSOR", is_active=True
        )
        athlete = AthleteProfileFactory(
            academy=academy, belt="white", stripes=3,
            mat_hours=200.0,
            belt_awarded_at=timezone.now() - timedelta(days=400),
        )
        AthleteProfileService.award_stripe(athlete, prof)
        assert Notification.objects.filter(
            recipient=athlete.user,
            notification_type=Notification.NotificationType.PROMOTION_READY,
        ).exists()

    def test_no_promotion_notification_when_not_ready(self, db, academy, global_req):
        from athletes.services import AthleteProfileService
        from notifications.models import Notification

        prof = AthleteProfileFactory(academy=academy, role="PROFESSOR")
        AcademyMembershipFactory(
            user=prof.user, academy=academy, role="PROFESSOR", is_active=True
        )
        athlete = AthleteProfileFactory(
            academy=academy, belt="white", stripes=3,
            mat_hours=10.0,  # below 100h requirement
            belt_awarded_at=None,
        )
        AthleteProfileService.award_stripe(athlete, prof)
        assert not Notification.objects.filter(
            recipient=athlete.user,
            notification_type=Notification.NotificationType.PROMOTION_READY,
        ).exists()

    def test_no_promotion_notification_on_non_4th_stripe(self, db, academy, global_req):
        from athletes.services import AthleteProfileService
        from notifications.models import Notification

        prof = AthleteProfileFactory(academy=academy, role="PROFESSOR")
        AcademyMembershipFactory(
            user=prof.user, academy=academy, role="PROFESSOR", is_active=True
        )
        athlete = AthleteProfileFactory(
            academy=academy, belt="white", stripes=1,
            mat_hours=200.0,
            belt_awarded_at=timezone.now() - timedelta(days=400),
        )
        AthleteProfileService.award_stripe(athlete, prof)
        assert not Notification.objects.filter(
            recipient=athlete.user,
            notification_type=Notification.NotificationType.PROMOTION_READY,
        ).exists()


# ─── promote_belt → belt_awarded_at stamped ────────────────────────────────────


class TestPromoteBeltAwardedAt:
    def test_promote_belt_sets_belt_awarded_at(self, db, academy):
        prof = AthleteProfileFactory(academy=academy, role="PROFESSOR")
        AcademyMembershipFactory(
            user=prof.user, academy=academy, role="PROFESSOR", is_active=True
        )
        athlete = AthleteProfileFactory(
            academy=academy, belt="white", belt_awarded_at=None
        )
        from athletes.services import AthleteProfileService

        before = timezone.now()
        updated = AthleteProfileService.promote_belt(athlete, "blue", prof)
        after = timezone.now()

        assert updated.belt == "blue"
        assert updated.belt_awarded_at is not None
        assert before <= updated.belt_awarded_at <= after

    def test_promote_belt_overwrites_previous_belt_awarded_at(self, db, academy):
        prof = AthleteProfileFactory(academy=academy, role="PROFESSOR")
        AcademyMembershipFactory(
            user=prof.user, academy=academy, role="PROFESSOR", is_active=True
        )
        old_ts = timezone.now() - timedelta(days=500)
        athlete = AthleteProfileFactory(
            academy=academy, belt="white", belt_awarded_at=old_ts
        )
        from athletes.services import AthleteProfileService

        updated = AthleteProfileService.promote_belt(athlete, "blue", prof)
        assert updated.belt_awarded_at > old_ts
