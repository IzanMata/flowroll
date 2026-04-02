"""
Tests for POST /api/v1/membership/{academy_id}/leave/

Rules:
- STUDENT and PROFESSOR can leave.
- OWNER cannot leave (must transfer ownership first).
- Leaving cancels active subscriptions at that academy.
- Leaving does not affect memberships at other academies.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import AcademyMembership
from factories import AcademyFactory, AcademyMembershipFactory, MembershipPlanFactory
from membership.models import Subscription
from membership.services import EnrollmentService, LeaveAcademyService


def leave_url(academy_id):
    return f"/api/v1/membership/{academy_id}/leave/"


@pytest.fixture
def user(db):
    return User.objects.create_user(username="leaveuser@test.com", email="leaveuser@test.com", password="Pass123!")


@pytest.fixture
def academy(db):
    return AcademyFactory(is_active=True)


@pytest.fixture
def plan(db, academy):
    return MembershipPlanFactory(academy=academy, duration_days=30, is_active=True, price=Decimal("50.00"))


@pytest.fixture
def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


# ─── Service layer ────────────────────────────────────────────────────────────

class TestLeaveAcademyService:
    def test_student_can_leave(self, db, user, academy):
        AcademyMembershipFactory(user=user, academy=academy, role=AcademyMembership.Role.STUDENT)
        LeaveAcademyService.leave(user=user, academy=academy)
        membership = AcademyMembership.objects.get(user=user, academy=academy)
        assert membership.is_active is False

    def test_professor_can_leave(self, db, user, academy):
        AcademyMembershipFactory(user=user, academy=academy, role=AcademyMembership.Role.PROFESSOR)
        LeaveAcademyService.leave(user=user, academy=academy)
        assert not AcademyMembership.objects.filter(user=user, academy=academy, is_active=True).exists()

    def test_owner_cannot_leave(self, db, user, academy):
        AcademyMembershipFactory(user=user, academy=academy, role=AcademyMembership.Role.OWNER)
        with pytest.raises(ValueError, match="owners cannot leave"):
            LeaveAcademyService.leave(user=user, academy=academy)

    def test_leaving_cancels_active_subscription(self, db, user, academy, plan):
        result = EnrollmentService.enroll(user=user, academy=academy, plan=plan)
        assert result["subscription"].status == Subscription.Status.ACTIVE

        LeaveAcademyService.leave(user=user, academy=academy)

        result["subscription"].refresh_from_db()
        assert result["subscription"].status == Subscription.Status.CANCELLED

    def test_leaving_does_not_affect_other_academy(self, db, user, academy, plan):
        other_academy = AcademyFactory(is_active=True)
        other_plan = MembershipPlanFactory(academy=other_academy, duration_days=30, is_active=True, price=Decimal("50.00"))

        EnrollmentService.enroll(user=user, academy=academy, plan=plan)
        r2 = EnrollmentService.enroll(user=user, academy=other_academy, plan=other_plan)

        LeaveAcademyService.leave(user=user, academy=academy)

        # Membership at other academy still active
        assert AcademyMembership.objects.filter(user=user, academy=other_academy, is_active=True).exists()
        r2["subscription"].refresh_from_db()
        assert r2["subscription"].status == Subscription.Status.ACTIVE

    def test_non_member_raises(self, db, user, academy):
        with pytest.raises(ValueError, match="not an active member"):
            LeaveAcademyService.leave(user=user, academy=academy)


# ─── API layer ────────────────────────────────────────────────────────────────

class TestLeaveAcademyView:
    def test_student_leave_returns_200(self, auth_client, user, academy):
        AcademyMembershipFactory(user=user, academy=academy, role=AcademyMembership.Role.STUDENT)
        response = auth_client.post(leave_url(academy.pk))
        assert response.status_code == status.HTTP_200_OK

    def test_owner_leave_returns_400(self, auth_client, user, academy):
        AcademyMembershipFactory(user=user, academy=academy, role=AcademyMembership.Role.OWNER)
        response = auth_client.post(leave_url(academy.pk))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "owners cannot leave" in response.data["detail"]

    def test_non_member_returns_400(self, auth_client, academy):
        response = auth_client.post(leave_url(academy.pk))
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unknown_academy_returns_404(self, auth_client):
        response = auth_client.post(leave_url(99999))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_returns_401(self, db, academy):
        client = APIClient()
        response = client.post(leave_url(academy.pk))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
