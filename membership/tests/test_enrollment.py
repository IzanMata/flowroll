"""
Tests for EnrollmentService and POST /api/membership/enroll/

Critical: a user must not be able to create duplicate active subscriptions
at the same academy.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import AcademyMembership
from factories import AcademyFactory, MembershipPlanFactory, SubscriptionFactory
from membership.models import MembershipPlan, Subscription
from membership.services import EnrollmentService

ENROLL_URL = "/api/membership/enroll/"


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="enrolluser@test.com",
        email="enrolluser@test.com",
        password="Pass123!",
    )


@pytest.fixture
def academy(db):
    return AcademyFactory(is_active=True)


@pytest.fixture
def plan(db, academy):
    return MembershipPlanFactory(
        academy=academy,
        plan_type=MembershipPlan.PlanType.MONTHLY,
        price=Decimal("80.00"),
        duration_days=30,
        is_active=True,
    )


@pytest.fixture
def plan_b(db, academy):
    """A second plan at the same academy."""
    return MembershipPlanFactory(
        academy=academy,
        plan_type=MembershipPlan.PlanType.ANNUAL,
        price=Decimal("700.00"),
        duration_days=365,
        is_active=True,
    )


@pytest.fixture
def other_academy(db):
    return AcademyFactory(is_active=True)


@pytest.fixture
def other_plan(db, other_academy):
    return MembershipPlanFactory(
        academy=other_academy,
        plan_type=MembershipPlan.PlanType.MONTHLY,
        price=Decimal("60.00"),
        duration_days=30,
        is_active=True,
    )


@pytest.fixture
def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


# ─── Service layer ────────────────────────────────────────────────────────────

class TestEnrollmentService:
    def test_enroll_creates_membership_and_subscription(self, db, user, academy, plan):
        result = EnrollmentService.enroll(user=user, academy=academy, plan=plan)

        assert AcademyMembership.objects.filter(user=user, academy=academy).exists()
        assert result["membership"].role == AcademyMembership.Role.STUDENT
        assert result["subscription"].status == Subscription.Status.ACTIVE

    def test_enroll_twice_same_academy_raises(self, db, user, academy, plan, plan_b):
        EnrollmentService.enroll(user=user, academy=academy, plan=plan)
        with pytest.raises(ValueError, match="active subscription"):
            EnrollmentService.enroll(user=user, academy=academy, plan=plan_b)

    def test_enroll_same_plan_twice_raises(self, db, user, academy, plan):
        EnrollmentService.enroll(user=user, academy=academy, plan=plan)
        with pytest.raises(ValueError, match="active subscription"):
            EnrollmentService.enroll(user=user, academy=academy, plan=plan)

    def test_enroll_in_two_different_academies_is_allowed(self, db, user, academy, plan, other_academy, other_plan):
        r1 = EnrollmentService.enroll(user=user, academy=academy, plan=plan)
        r2 = EnrollmentService.enroll(user=user, academy=other_academy, plan=other_plan)

        assert r1["membership"].academy == academy
        assert r2["membership"].academy == other_academy
        assert Subscription.objects.filter(athlete=r1["membership"].user.profile).count() == 2

    def test_enroll_after_expired_subscription_is_allowed(self, db, user, academy, plan):
        result = EnrollmentService.enroll(user=user, academy=academy, plan=plan)
        # Simulate expiry
        result["subscription"].status = Subscription.Status.EXPIRED
        result["subscription"].save(update_fields=["status"])

        # Should be able to enroll again now
        result2 = EnrollmentService.enroll(user=user, academy=academy, plan=plan)
        assert result2["subscription"].status == Subscription.Status.ACTIVE

    def test_plan_from_wrong_academy_raises(self, db, user, academy, other_plan):
        with pytest.raises(ValueError, match="does not belong"):
            EnrollmentService.enroll(user=user, academy=academy, plan=other_plan)


# ─── API layer ────────────────────────────────────────────────────────────────

class TestEnrollView:
    def test_enroll_returns_201(self, auth_client, academy, plan):
        response = auth_client.post(
            ENROLL_URL, {"academy": academy.pk, "plan": plan.pk}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert "subscription" in response.data

    def test_duplicate_enroll_returns_400(self, auth_client, academy, plan):
        auth_client.post(ENROLL_URL, {"academy": academy.pk, "plan": plan.pk}, format="json")
        response = auth_client.post(
            ENROLL_URL, {"academy": academy.pk, "plan": plan.pk}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "active subscription" in response.data["detail"]

    def test_unauthenticated_returns_401(self, db, academy, plan):
        client = APIClient()
        response = client.post(
            ENROLL_URL, {"academy": academy.pk, "plan": plan.pk}, format="json"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_inactive_academy_not_available(self, auth_client, db):
        inactive = AcademyFactory(is_active=False)
        plan = MembershipPlanFactory(academy=inactive, is_active=True)
        response = auth_client.post(
            ENROLL_URL, {"academy": inactive.pk, "plan": plan.pk}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_inactive_plan_not_available(self, auth_client, academy, db):
        inactive_plan = MembershipPlanFactory(academy=academy, is_active=False)
        response = auth_client.post(
            ENROLL_URL, {"academy": academy.pk, "plan": inactive_plan.pk}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
