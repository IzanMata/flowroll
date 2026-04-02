"""
Tests for academy member management:
  GET    /api/academies/{id}/members/            — list members
  POST   /api/academies/{id}/members/            — add member by email (OWNER only)
  PATCH  /api/academies/{id}/members/{user_id}/  — change role (OWNER only)
  DELETE /api/academies/{id}/members/{user_id}/  — remove member (OWNER only)
"""

import pytest
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from academies.services import AcademyMemberService
from core.models import AcademyMembership
from factories import AcademyFactory, AcademyMembershipFactory, UserFactory


def members_url(academy_id):
    return f"/api/academies/{academy_id}/members/"


def member_url(academy_id, user_id):
    return f"/api/academies/{academy_id}/members/{user_id}/"


@pytest.fixture
def owner_user(db):
    return User.objects.create_user(username="owner@test.com", email="owner@test.com", password="Pass123!")


@pytest.fixture
def academy(db):
    return AcademyFactory(is_active=True)


@pytest.fixture
def owner_membership(db, owner_user, academy):
    return AcademyMembershipFactory(user=owner_user, academy=academy, role=AcademyMembership.Role.OWNER)


@pytest.fixture
def owner_client(owner_user):
    client = APIClient()
    refresh = RefreshToken.for_user(owner_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="other@test.com", email="other@test.com", password="Pass123!")


# ─── Service layer ────────────────────────────────────────────────────────────

class TestAcademyMemberService:
    def test_add_member_by_email(self, db, academy, other_user):
        membership = AcademyMemberService.add_member(academy, other_user.email, AcademyMembership.Role.PROFESSOR)
        assert membership.role == AcademyMembership.Role.PROFESSOR
        assert membership.is_active is True

    def test_add_unknown_email_raises(self, db, academy):
        with pytest.raises(ValueError, match="No registered user"):
            AcademyMemberService.add_member(academy, "nobody@x.com", AcademyMembership.Role.STUDENT)

    def test_add_reactivates_inactive_member(self, db, academy, other_user):
        m = AcademyMembershipFactory(user=other_user, academy=academy, role=AcademyMembership.Role.STUDENT, is_active=False)
        AcademyMemberService.add_member(academy, other_user.email, AcademyMembership.Role.PROFESSOR)
        m.refresh_from_db()
        assert m.is_active is True
        assert m.role == AcademyMembership.Role.PROFESSOR

    def test_change_role_student_to_professor(self, db, academy, owner_user, other_user):
        AcademyMembershipFactory(user=owner_user, academy=academy, role=AcademyMembership.Role.OWNER)
        m = AcademyMembershipFactory(user=other_user, academy=academy, role=AcademyMembership.Role.STUDENT)
        AcademyMemberService.change_role(academy, other_user.pk, AcademyMembership.Role.PROFESSOR, owner_user)
        m.refresh_from_db()
        assert m.role == AcademyMembership.Role.PROFESSOR

    def test_cannot_change_own_role(self, db, academy, owner_user):
        AcademyMembershipFactory(user=owner_user, academy=academy, role=AcademyMembership.Role.OWNER)
        with pytest.raises(ValueError, match="own role"):
            AcademyMemberService.change_role(academy, owner_user.pk, AcademyMembership.Role.STUDENT, owner_user)

    def test_cannot_demote_last_owner(self, db, academy, owner_user):
        AcademyMembershipFactory(user=owner_user, academy=academy, role=AcademyMembership.Role.OWNER)
        other = UserFactory()
        AcademyMembershipFactory(user=other, academy=academy, role=AcademyMembership.Role.STUDENT)
        with pytest.raises(ValueError, match="last owner"):
            AcademyMemberService.change_role(academy, owner_user.pk, AcademyMembership.Role.STUDENT, other)

    def test_remove_member(self, db, academy, owner_user, other_user):
        AcademyMembershipFactory(user=owner_user, academy=academy, role=AcademyMembership.Role.OWNER)
        m = AcademyMembershipFactory(user=other_user, academy=academy, role=AcademyMembership.Role.STUDENT)
        AcademyMemberService.remove_member(academy, other_user.pk, owner_user)
        m.refresh_from_db()
        assert m.is_active is False

    def test_cannot_remove_last_owner(self, db, academy, owner_user, other_user):
        # owner_user is the sole OWNER; other_user is a PROFESSOR
        AcademyMembershipFactory(user=owner_user, academy=academy, role=AcademyMembership.Role.OWNER)
        AcademyMembershipFactory(user=other_user, academy=academy, role=AcademyMembership.Role.PROFESSOR)
        # A professor trying to remove the last owner must be blocked
        with pytest.raises(ValueError, match="last owner"):
            AcademyMemberService.remove_member(academy, owner_user.pk, other_user)

    def test_cannot_remove_self_via_this_service(self, db, academy, owner_user, other_user):
        AcademyMembershipFactory(user=owner_user, academy=academy, role=AcademyMembership.Role.OWNER)
        AcademyMembershipFactory(user=other_user, academy=academy, role=AcademyMembership.Role.STUDENT)
        with pytest.raises(ValueError, match="leave endpoint"):
            AcademyMemberService.remove_member(academy, other_user.pk, other_user)


# ─── API layer ────────────────────────────────────────────────────────────────

class TestMemberListView:
    def test_owner_can_list_members(self, owner_client, academy, owner_membership):
        response = owner_client.get(members_url(academy.pk))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_non_member_gets_404(self, db, academy):
        stranger = UserFactory()
        client = APIClient()
        refresh = RefreshToken.for_user(stranger)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        response = client.get(members_url(academy.pk))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_owner_can_add_professor(self, owner_client, academy, owner_membership, other_user):
        response = owner_client.post(
            members_url(academy.pk),
            {"email": other_user.email, "role": "PROFESSOR"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["role"] == "PROFESSOR"

    def test_student_cannot_add_members(self, db, academy, owner_membership, other_user):
        student = UserFactory()
        AcademyMembershipFactory(user=student, academy=academy, role=AcademyMembership.Role.STUDENT)
        client = APIClient()
        refresh = RefreshToken.for_user(student)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        response = client.post(
            members_url(academy.pk),
            {"email": other_user.email, "role": "PROFESSOR"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_add_unknown_email_returns_400(self, owner_client, academy, owner_membership):
        response = owner_client.post(
            members_url(academy.pk),
            {"email": "ghost@nowhere.com", "role": "STUDENT"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestMemberDetailView:
    def test_owner_can_change_role(self, owner_client, academy, owner_membership, other_user):
        m = AcademyMembershipFactory(user=other_user, academy=academy, role=AcademyMembership.Role.STUDENT)
        response = owner_client.patch(
            member_url(academy.pk, other_user.pk),
            {"role": "PROFESSOR"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["role"] == "PROFESSOR"

    def test_owner_can_remove_member(self, owner_client, academy, owner_membership, other_user):
        AcademyMembershipFactory(user=other_user, academy=academy, role=AcademyMembership.Role.STUDENT)
        response = owner_client.delete(member_url(academy.pk, other_user.pk))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not AcademyMembership.objects.filter(user=other_user, academy=academy, is_active=True).exists()

    def test_cannot_demote_last_owner_via_api(self, owner_client, academy, owner_membership):
        response = owner_client.patch(
            member_url(academy.pk, owner_membership.user.pk),
            {"role": "STUDENT"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_returns_401(self, db, academy):
        client = APIClient()
        response = client.get(members_url(academy.pk))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
