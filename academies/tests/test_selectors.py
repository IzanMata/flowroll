"""
Tests for academies/selectors.py.

Covers:
  - get_academies_for_user: returns only academies user is actively a member of
  - get_public_academies: returns active academies, applies search/city/country filters
  - get_members_for_academy: returns active members, filters by role
  - get_academy_stats: returns correct member_count and athlete metrics
"""

import pytest

from academies.selectors import (
    get_academies_for_user,
    get_academy_stats,
    get_members_for_academy,
    get_public_academies,
)
from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    UserFactory,
)


# ─── get_academies_for_user ───────────────────────────────────────────────────


class TestGetAcademiesForUser:
    def test_returns_user_academies(self, db):
        user = UserFactory()
        acad1 = AcademyFactory(name="Acad 1")
        acad2 = AcademyFactory(name="Acad 2")
        AcademyMembershipFactory(user=user, academy=acad1, is_active=True)
        AcademyMembershipFactory(user=user, academy=acad2, is_active=True)
        result = get_academies_for_user(user.pk)
        assert acad1 in result
        assert acad2 in result

    def test_excludes_inactive_memberships(self, db):
        user = UserFactory()
        acad = AcademyFactory()
        AcademyMembershipFactory(user=user, academy=acad, is_active=False)
        result = get_academies_for_user(user.pk)
        assert acad not in result

    def test_does_not_return_other_users_academies(self, db):
        user = UserFactory()
        other = UserFactory()
        acad = AcademyFactory()
        AcademyMembershipFactory(user=other, academy=acad, is_active=True)
        result = get_academies_for_user(user.pk)
        assert acad not in result

    def test_returns_empty_for_unknown_user(self, db):
        result = get_academies_for_user(99999)
        assert result.count() == 0


# ─── get_public_academies ─────────────────────────────────────────────────────


class TestGetPublicAcademies:
    def test_returns_active_academies(self, db):
        active = AcademyFactory(name="Active Academy", is_active=True)
        AcademyFactory(name="Inactive Academy", is_active=False)
        result = get_public_academies()
        names = list(result.values_list("name", flat=True))
        assert "Active Academy" in names
        assert "Inactive Academy" not in names

    def test_search_by_name(self, db):
        AcademyFactory(name="Gracie Barra")
        AcademyFactory(name="Alliance BJJ")
        result = get_public_academies(search="gracie")
        assert result.count() == 1
        assert result.first().name == "Gracie Barra"

    def test_filter_by_city(self, db):
        AcademyFactory(name="London BJJ", city="London")
        AcademyFactory(name="Paris BJJ", city="Paris")
        result = get_public_academies(city="london")
        assert result.count() == 1
        assert result.first().name == "London BJJ"

    def test_filter_by_country(self, db):
        AcademyFactory(name="US Academy", country="USA")
        AcademyFactory(name="UK Academy", country="UK")
        result = get_public_academies(country="usa")
        assert result.count() == 1
        assert result.first().name == "US Academy"

    def test_multiple_filters_are_additive(self, db):
        AcademyFactory(name="NYC Gracie", city="New York", country="USA")
        AcademyFactory(name="LA Gracie", city="Los Angeles", country="USA")
        result = get_public_academies(city="new york", country="usa")
        assert result.count() == 1


# ─── get_members_for_academy ──────────────────────────────────────────────────


class TestGetMembersForAcademy:
    def test_returns_active_members(self, db):
        acad = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=acad, is_active=True)
        result = get_members_for_academy(acad.pk)
        assert result.filter(user=user).exists()

    def test_excludes_inactive_members_by_default(self, db):
        acad = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=acad, is_active=False)
        result = get_members_for_academy(acad.pk)
        assert not result.filter(user=user).exists()

    def test_includes_inactive_when_active_only_false(self, db):
        acad = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=acad, is_active=False)
        result = get_members_for_academy(acad.pk, active_only=False)
        assert result.filter(user=user).exists()

    def test_filter_by_role(self, db):
        acad = AcademyFactory()
        prof = UserFactory()
        student = UserFactory()
        AcademyMembershipFactory(user=prof, academy=acad, role="PROFESSOR", is_active=True)
        AcademyMembershipFactory(user=student, academy=acad, role="STUDENT", is_active=True)
        result = get_members_for_academy(acad.pk, role="PROFESSOR")
        assert result.filter(user=prof).exists()
        assert not result.filter(user=student).exists()

    def test_does_not_leak_other_academies_members(self, db):
        acad1 = AcademyFactory()
        acad2 = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=acad2, is_active=True)
        result = get_members_for_academy(acad1.pk)
        assert not result.filter(user=user).exists()


# ─── get_academy_stats ────────────────────────────────────────────────────────


class TestGetAcademyStats:
    def test_stats_member_count(self, db):
        acad = AcademyFactory()
        AcademyMembershipFactory(academy=acad, is_active=True)
        AcademyMembershipFactory(academy=acad, is_active=True)
        AcademyMembershipFactory(academy=acad, is_active=False)  # excluded
        stats = get_academy_stats(acad.pk)
        assert stats["member_count"] == 2

    def test_stats_total_athletes(self, db):
        acad = AcademyFactory()
        AthleteProfileFactory(academy=acad)
        AthleteProfileFactory(academy=acad)
        stats = get_academy_stats(acad.pk)
        assert stats["total_athletes"] == 2

    def test_stats_total_mat_hours(self, db):
        acad = AcademyFactory()
        AthleteProfileFactory(academy=acad, mat_hours=100.0)
        AthleteProfileFactory(academy=acad, mat_hours=50.0)
        stats = get_academy_stats(acad.pk)
        assert stats["total_mat_hours"] == pytest.approx(150.0)

    def test_stats_empty_academy(self, db):
        acad = AcademyFactory()
        stats = get_academy_stats(acad.pk)
        assert stats["member_count"] == 0
        assert stats["total_athletes"] == 0
        assert stats["total_mat_hours"] == 0.0
