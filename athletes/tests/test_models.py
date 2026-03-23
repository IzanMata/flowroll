"""Tests for AthleteProfile model."""

import pytest

from athletes.models import AthleteProfile
from factories import AcademyFactory, AthleteProfileFactory, UserFactory


class TestAthleteProfile:
    def test_create_athlete(self, db):
        # Use ORM directly to exercise model defaults, not the factory's FuzzyChoice values
        user = UserFactory()
        academy = AcademyFactory()
        athlete = AthleteProfile.objects.create(user=user, academy=academy)
        assert athlete.pk is not None
        assert athlete.belt == "white"
        assert athlete.stripes == 0
        assert athlete.mat_hours == 0.0

    def test_str_representation(self, db):
        user = UserFactory(username="tester")
        academy = AcademyFactory(name="Gracie HQ")
        athlete = AthleteProfileFactory(user=user, academy=academy, belt="blue")
        assert "tester" in str(athlete)
        assert "Gracie HQ" in str(athlete)

    def test_str_without_academy(self, db):
        user = UserFactory(username="nomad")
        athlete = AthleteProfileFactory(user=user, academy=None)
        assert "No Academy" in str(athlete)

    def test_one_to_one_with_user(self, db):
        athlete = AthleteProfileFactory()
        assert athlete.user.profile == athlete

    def test_valid_belt_choices(self, db):
        for belt in ["white", "blue", "purple", "brown", "black"]:
            a = AthleteProfileFactory(belt=belt)
            assert a.belt == belt

    def test_stripes_default_zero(self, db):
        user = UserFactory()
        athlete = AthleteProfile.objects.create(user=user, academy=AcademyFactory())
        assert athlete.stripes == 0

    def test_weight_can_be_null(self, db):
        athlete = AthleteProfileFactory(weight=None)
        assert athlete.weight is None

    def test_mat_hours_default_zero(self, db):
        user = UserFactory()
        athlete = AthleteProfile.objects.create(user=user, academy=AcademyFactory())
        assert athlete.mat_hours == 0.0

    def test_get_lineage_no_coach(self, db):
        athlete = AthleteProfileFactory()
        assert athlete.get_lineage() == []

    def test_get_lineage_single_coach(self, db):
        coach = AthleteProfileFactory()
        athlete = AthleteProfileFactory(coach=coach)
        lineage = athlete.get_lineage()
        assert lineage == [coach]

    def test_get_lineage_chain(self, db):
        grandmaster = AthleteProfileFactory()
        master = AthleteProfileFactory(coach=grandmaster)
        blackbelt = AthleteProfileFactory(coach=master)
        student = AthleteProfileFactory(coach=blackbelt)

        lineage = student.get_lineage()
        assert lineage == [blackbelt, master, grandmaster]

    def test_coach_is_self_referential(self, db):
        a = AthleteProfileFactory()
        b = AthleteProfileFactory(coach=a)
        assert b.coach == a
        # a is the coach, so b appears in a.students (not b.students)
        assert b in a.students.all()

    def test_cascade_delete_user_removes_profile(self, db):
        athlete = AthleteProfileFactory()
        pk = athlete.pk
        athlete.user.delete()
        assert not AthleteProfile.objects.filter(pk=pk).exists()

    def test_academy_set_null_on_delete(self, db):
        athlete = AthleteProfileFactory()
        athlete.academy.delete()
        athlete.refresh_from_db()
        assert athlete.academy is None

    def test_default_role_is_student(self, db):
        user = UserFactory()
        academy = AcademyFactory()
        athlete = AthleteProfile.objects.create(user=user, academy=academy)
        assert athlete.role == AthleteProfile.RoleChoices.STUDENT

    def test_role_choices(self):
        roles = {r for r, _ in AthleteProfile.RoleChoices.choices}
        assert roles == {"STUDENT", "PROFESSOR"}

    def test_one_user_one_profile(self, db):
        from django.db import IntegrityError

        user = UserFactory()
        academy = AcademyFactory()
        AthleteProfile.objects.create(user=user, academy=academy)
        with pytest.raises(IntegrityError):
            AthleteProfile.objects.create(user=user, academy=AcademyFactory())

    def test_get_lineage_circular_reference_does_not_loop(self, db):
        """M-9 fix: circular coach references must terminate without RecursionError."""
        a = AthleteProfileFactory(coach=None)
        b = AthleteProfileFactory(coach=a)
        a.coach = b
        a.save()

        lineage = b.get_lineage()
        assert len(lineage) <= 2
