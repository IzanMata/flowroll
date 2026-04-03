"""
Tests for athletes/services.py: AthleteProfileService.

Covers:
  - award_stripe: increments stripes, rejects at max (4), enforces professor role
  - promote_belt: validates progression order, resets stripes, enforces professor role
  - update_weight: persists positive weight, rejects zero/negative
  - assign_coach: sets coach, rejects self, detects cycles
"""

import pytest

from athletes.models import AthleteProfile
from athletes.services import AthleteProfileService
from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    UserFactory,
)


@pytest.fixture
def academy(db):
    return AcademyFactory()


@pytest.fixture
def professor(db, academy):
    user = UserFactory()
    athlete = AthleteProfileFactory(user=user, academy=academy, role="PROFESSOR", belt="blue", stripes=0)
    AcademyMembershipFactory(user=user, academy=academy, role="PROFESSOR", is_active=True)
    return athlete


@pytest.fixture
def student(db, academy):
    return AthleteProfileFactory(academy=academy, role="STUDENT", belt="white", stripes=0)


# ─── award_stripe ─────────────────────────────────────────────────────────────


class TestAwardStripe:
    def test_award_stripe_increments(self, db, professor, student):
        result = AthleteProfileService.award_stripe(student, awarded_by=professor)
        assert result.stripes == 1

    def test_award_stripe_increments_multiple_times(self, db, professor, student):
        for expected in range(1, 5):
            student = AthleteProfileService.award_stripe(student, awarded_by=professor)
            assert student.stripes == expected

    def test_award_stripe_at_max_raises(self, db, professor, academy):
        athlete = AthleteProfileFactory(academy=academy, stripes=4, belt="white")
        with pytest.raises(ValueError, match="4 stripes"):
            AthleteProfileService.award_stripe(athlete, awarded_by=professor)

    def test_non_professor_cannot_award_stripe(self, db, academy, student):
        student2 = AthleteProfileFactory(academy=academy, role="STUDENT", belt="blue")
        AcademyMembershipFactory(user=student2.user, academy=academy, role="STUDENT", is_active=True)
        with pytest.raises(ValueError, match="professors"):
            AthleteProfileService.award_stripe(student, awarded_by=student2)


# ─── promote_belt ─────────────────────────────────────────────────────────────


class TestPromoteBelt:
    def test_promote_from_white_to_blue(self, db, professor, academy):
        athlete = AthleteProfileFactory(academy=academy, belt="white", stripes=4)
        result = AthleteProfileService.promote_belt(athlete, new_belt="blue", awarded_by=professor)
        assert result.belt == "blue"
        assert result.stripes == 0

    def test_promote_resets_stripes(self, db, professor, academy):
        athlete = AthleteProfileFactory(academy=academy, belt="white", stripes=4)
        result = AthleteProfileService.promote_belt(athlete, new_belt="blue", awarded_by=professor)
        assert result.stripes == 0

    def test_promote_rejects_same_belt(self, db, professor, academy):
        athlete = AthleteProfileFactory(academy=academy, belt="blue")
        with pytest.raises(ValueError, match="higher"):
            AthleteProfileService.promote_belt(athlete, new_belt="blue", awarded_by=professor)

    def test_promote_rejects_downgrade(self, db, professor, academy):
        athlete = AthleteProfileFactory(academy=academy, belt="blue")
        with pytest.raises(ValueError, match="higher"):
            AthleteProfileService.promote_belt(athlete, new_belt="white", awarded_by=professor)

    def test_non_professor_cannot_promote(self, db, academy, student):
        athlete = AthleteProfileFactory(academy=academy, belt="white")
        student2 = AthleteProfileFactory(academy=academy, role="STUDENT")
        AcademyMembershipFactory(user=student2.user, academy=academy, role="STUDENT", is_active=True)
        with pytest.raises(ValueError, match="professors"):
            AthleteProfileService.promote_belt(athlete, new_belt="blue", awarded_by=student2)

    def test_full_belt_progression(self, db, professor, academy):
        athlete = AthleteProfileFactory(academy=academy, belt="white")
        for belt in ["blue", "purple", "brown", "black"]:
            athlete = AthleteProfileService.promote_belt(athlete, new_belt=belt, awarded_by=professor)
        assert athlete.belt == "black"


# ─── update_weight ────────────────────────────────────────────────────────────


class TestUpdateWeight:
    def test_update_weight_persists(self, db, student):
        result = AthleteProfileService.update_weight(student, weight_kg=74.5)
        assert result.weight == pytest.approx(74.5)

    def test_update_weight_zero_raises(self, db, student):
        with pytest.raises(ValueError, match="positive"):
            AthleteProfileService.update_weight(student, weight_kg=0)

    def test_update_weight_negative_raises(self, db, student):
        with pytest.raises(ValueError, match="positive"):
            AthleteProfileService.update_weight(student, weight_kg=-5)

    def test_update_weight_persists_in_db(self, db, student):
        AthleteProfileService.update_weight(student, weight_kg=82.0)
        student.refresh_from_db()
        assert student.weight == pytest.approx(82.0)


# ─── assign_coach ─────────────────────────────────────────────────────────────


class TestAssignCoach:
    def test_assign_coach(self, db, professor, student):
        result = AthleteProfileService.assign_coach(student, coach=professor)
        assert result.coach == professor

    def test_assign_self_as_coach_raises(self, db, student):
        with pytest.raises(ValueError, match="cannot be their own coach"):
            AthleteProfileService.assign_coach(student, coach=student)

    def test_assign_coach_detects_direct_cycle(self, db):
        a = AthleteProfileFactory(coach=None)
        b = AthleteProfileFactory(coach=a)
        with pytest.raises(ValueError, match="circular"):
            AthleteProfileService.assign_coach(a, coach=b)

    def test_assign_coach_detects_indirect_cycle(self, db):
        a = AthleteProfileFactory(coach=None)
        b = AthleteProfileFactory(coach=a)
        c = AthleteProfileFactory(coach=b)
        # Assigning c as a's coach would make a ← b ← c ← a
        with pytest.raises(ValueError, match="circular"):
            AthleteProfileService.assign_coach(a, coach=c)

    def test_assign_coach_persists_in_db(self, db, professor, student):
        AthleteProfileService.assign_coach(student, coach=professor)
        student.refresh_from_db()
        assert student.coach == professor
