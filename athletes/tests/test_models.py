"""Tests for AthleteProfile model."""
import pytest

from athletes.models import AthleteProfile
from factories import AcademyFactory, AthleteProfileFactory, UserFactory


class TestAthleteProfile:
    def test_create_athlete(self, db):
        athlete = AthleteProfileFactory()
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
        athlete = AthleteProfileFactory()
        assert athlete.stripes == 0

    def test_weight_can_be_null(self, db):
        athlete = AthleteProfileFactory(weight=None)
        assert athlete.weight is None

    def test_mat_hours_default_zero(self, db):
        athlete = AthleteProfileFactory()
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
        assert a in b.students.all()

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
