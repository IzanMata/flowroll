"""Tests for core models: Belt and AcademyMembership."""
import pytest

from core.models import AcademyMembership, Belt
from factories import AcademyFactory, AcademyMembershipFactory, UserFactory


class TestBelt:
    def test_create_belt(self, db):
        belt = Belt.objects.create(color="white", order=1)
        assert belt.color == "white"
        assert belt.order == 1

    def test_str_returns_color_display(self, db):
        belt = Belt.objects.create(color="blue", order=2)
        assert str(belt) == "Blue"

    def test_belt_ordering_by_order_field(self, db):
        Belt.objects.create(color="black", order=5)
        Belt.objects.create(color="white", order=1)
        Belt.objects.create(color="blue", order=2)
        colors = list(Belt.objects.values_list("color", flat=True))
        assert colors == ["white", "blue", "black"]

    def test_color_is_unique(self, db):
        from django.db import IntegrityError
        Belt.objects.create(color="white", order=1)
        with pytest.raises(IntegrityError):
            Belt.objects.create(color="white", order=2)

    def test_all_belt_colors_are_valid(self, db):
        valid = {"white", "blue", "purple", "brown", "black"}
        choices = {c for c, _ in Belt.BeltColor.choices}
        assert choices == valid


class TestAcademyMembership:
    def test_create_membership(self, db):
        membership = AcademyMembershipFactory()
        assert membership.pk is not None
        assert membership.is_active is True

    def test_str_representation(self, db):
        user = UserFactory(username="john")
        academy = AcademyFactory(name="Alpha BJJ")
        m = AcademyMembershipFactory(user=user, academy=academy, role="PROFESSOR")
        assert "john" in str(m)
        assert "Alpha BJJ" in str(m)
        assert "PROFESSOR" in str(m)

    def test_default_role_is_student(self, db):
        m = AcademyMembershipFactory()
        assert m.role == AcademyMembership.Role.STUDENT

    def test_unique_user_per_academy(self, db):
        from django.db import IntegrityError
        user = UserFactory()
        academy = AcademyFactory()
        AcademyMembershipFactory(user=user, academy=academy)
        with pytest.raises(IntegrityError):
            AcademyMembershipFactory(user=user, academy=academy)

    def test_same_user_can_belong_to_multiple_academies(self, db):
        user = UserFactory()
        a1 = AcademyFactory()
        a2 = AcademyFactory()
        AcademyMembershipFactory(user=user, academy=a1)
        AcademyMembershipFactory(user=user, academy=a2)
        assert AcademyMembership.objects.filter(user=user).count() == 2

    def test_cascade_delete_on_user(self, db):
        m = AcademyMembershipFactory()
        user_pk = m.user.pk
        m.user.delete()
        assert not AcademyMembership.objects.filter(pk=m.pk).exists()

    def test_cascade_delete_on_academy(self, db):
        m = AcademyMembershipFactory()
        m.academy.delete()
        assert not AcademyMembership.objects.filter(pk=m.pk).exists()

    def test_role_choices(self):
        roles = {r for r, _ in AcademyMembership.Role.choices}
        assert roles == {"STUDENT", "PROFESSOR", "OWNER"}
