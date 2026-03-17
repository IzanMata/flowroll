"""Tests for all four DRF permission classes."""

from unittest.mock import MagicMock

from core.permissions import (IsAcademyMember, IsAcademyOwner,
                              IsAcademyProfessor, IsSuperAdmin)
from factories import AcademyFactory, AcademyMembershipFactory, UserFactory


def _make_request(user, academy_id=None):
    """Build a mock DRF request with optional academy query param."""
    request = MagicMock()
    request.user = user
    request.query_params = {"academy": str(academy_id)} if academy_id else {}
    return request


def _make_view(academy_pk=None):
    view = MagicMock()
    view.kwargs = {"academy_pk": academy_pk} if academy_pk else {}
    return view


class TestIsAcademyMember:
    def test_active_student_has_access(self, db):
        membership = AcademyMembershipFactory(role="STUDENT", is_active=True)
        perm = IsAcademyMember()
        request = _make_request(membership.user, academy_id=membership.academy_id)
        assert perm.has_permission(request, _make_view()) is True

    def test_inactive_member_denied(self, db):
        membership = AcademyMembershipFactory(role="STUDENT", is_active=False)
        perm = IsAcademyMember()
        request = _make_request(membership.user, academy_id=membership.academy_id)
        assert perm.has_permission(request, _make_view()) is False

    def test_no_academy_param_denied(self, db):
        user = UserFactory()
        perm = IsAcademyMember()
        request = _make_request(user)  # no academy_id
        assert perm.has_permission(request, _make_view()) is False

    def test_professor_is_also_a_member(self, db):
        membership = AcademyMembershipFactory(role="PROFESSOR", is_active=True)
        perm = IsAcademyMember()
        request = _make_request(membership.user, academy_id=membership.academy_id)
        assert perm.has_permission(request, _make_view()) is True

    def test_member_of_different_academy_denied(self, db):
        a1 = AcademyFactory()
        a2 = AcademyFactory()
        membership = AcademyMembershipFactory(academy=a1, is_active=True)
        perm = IsAcademyMember()
        request = _make_request(membership.user, academy_id=a2.pk)
        assert perm.has_permission(request, _make_view()) is False


class TestIsAcademyProfessor:
    def test_professor_has_access(self, db):
        membership = AcademyMembershipFactory(role="PROFESSOR", is_active=True)
        perm = IsAcademyProfessor()
        request = _make_request(membership.user, academy_id=membership.academy_id)
        assert perm.has_permission(request, _make_view()) is True

    def test_owner_has_access(self, db):
        membership = AcademyMembershipFactory(role="OWNER", is_active=True)
        perm = IsAcademyProfessor()
        request = _make_request(membership.user, academy_id=membership.academy_id)
        assert perm.has_permission(request, _make_view()) is True

    def test_student_denied(self, db):
        membership = AcademyMembershipFactory(role="STUDENT", is_active=True)
        perm = IsAcademyProfessor()
        request = _make_request(membership.user, academy_id=membership.academy_id)
        assert perm.has_permission(request, _make_view()) is False

    def test_academy_pk_from_url_kwargs(self, db):
        """Permissions should also resolve academy from URL kwargs."""
        membership = AcademyMembershipFactory(role="PROFESSOR", is_active=True)
        perm = IsAcademyProfessor()
        request = _make_request(membership.user)  # no query param
        view = _make_view(academy_pk=membership.academy_id)
        assert perm.has_permission(request, view) is True


class TestIsAcademyOwner:
    def test_owner_has_access(self, db):
        membership = AcademyMembershipFactory(role="OWNER", is_active=True)
        perm = IsAcademyOwner()
        request = _make_request(membership.user, academy_id=membership.academy_id)
        assert perm.has_permission(request, _make_view()) is True

    def test_professor_denied(self, db):
        membership = AcademyMembershipFactory(role="PROFESSOR", is_active=True)
        perm = IsAcademyOwner()
        request = _make_request(membership.user, academy_id=membership.academy_id)
        assert perm.has_permission(request, _make_view()) is False

    def test_student_denied(self, db):
        membership = AcademyMembershipFactory(role="STUDENT", is_active=True)
        perm = IsAcademyOwner()
        request = _make_request(membership.user, academy_id=membership.academy_id)
        assert perm.has_permission(request, _make_view()) is False


class TestIsSuperAdmin:
    def test_superuser_has_access(self, db):
        user = UserFactory(is_staff=True, is_superuser=True)
        perm = IsSuperAdmin()
        request = _make_request(user)
        assert perm.has_permission(request, _make_view()) is True

    def test_regular_user_denied(self, db):
        user = UserFactory()
        perm = IsSuperAdmin()
        request = _make_request(user)
        assert perm.has_permission(request, _make_view()) is False

    def test_staff_non_superuser_denied(self, db):
        user = UserFactory(is_staff=True, is_superuser=False)
        perm = IsSuperAdmin()
        request = _make_request(user)
        assert perm.has_permission(request, _make_view()) is False
