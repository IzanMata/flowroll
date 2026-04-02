"""
Tests for POST /api/membership/subscriptions/{id}/cancel/
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from factories import AcademyFactory, AthleteProfileFactory, MembershipPlanFactory, SubscriptionFactory
from membership.models import Subscription
from membership.services import SubscriptionService


def cancel_url(subscription_id):
    return f"/api/membership/subscriptions/{subscription_id}/cancel/"


@pytest.fixture
def user(db):
    return User.objects.create_user(username="canceluser@test.com", email="canceluser@test.com", password="Pass123!")


@pytest.fixture
def athlete(db, user):
    academy = AcademyFactory()
    return AthleteProfileFactory(user=user, academy=academy)


@pytest.fixture
def plan(db, athlete):
    return MembershipPlanFactory(academy=athlete.academy, duration_days=30, price=Decimal("50.00"), is_active=True)


@pytest.fixture
def active_subscription(db, athlete, plan):
    return SubscriptionFactory(athlete=athlete, plan=plan, status=Subscription.Status.ACTIVE)


@pytest.fixture
def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


class TestCancelSubscriptionService:
    def test_cancel_sets_status_to_cancelled(self, db, user, active_subscription):
        SubscriptionService.cancel(active_subscription, user=user)
        active_subscription.refresh_from_db()
        assert active_subscription.status == Subscription.Status.CANCELLED

    def test_cancel_already_cancelled_raises(self, db, user, active_subscription):
        SubscriptionService.cancel(active_subscription, user=user)
        with pytest.raises(ValueError, match="Cannot cancel"):
            SubscriptionService.cancel(active_subscription, user=user)

    def test_cancel_expired_raises(self, db, user, athlete, plan):
        sub = SubscriptionFactory(athlete=athlete, plan=plan, status=Subscription.Status.EXPIRED)
        with pytest.raises(ValueError, match="Cannot cancel"):
            SubscriptionService.cancel(sub, user=user)

    def test_other_user_cannot_cancel(self, db, active_subscription):
        other = User.objects.create_user(username="other@test.com", password="Pass123!")
        with pytest.raises(ValueError, match="own subscription"):
            SubscriptionService.cancel(active_subscription, user=other)


class TestCancelSubscriptionView:
    def test_cancel_returns_200_with_updated_status(self, auth_client, active_subscription):
        response = auth_client.post(cancel_url(active_subscription.pk))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == Subscription.Status.CANCELLED

    def test_cancel_already_cancelled_returns_400(self, auth_client, active_subscription):
        auth_client.post(cancel_url(active_subscription.pk))
        response = auth_client.post(cancel_url(active_subscription.pk))
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_other_user_cannot_cancel_returns_400(self, db, active_subscription):
        other = User.objects.create_user(username="intruder@test.com", password="Pass123!")
        client = APIClient()
        refresh = RefreshToken.for_user(other)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        response = client.post(cancel_url(active_subscription.pk))
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unknown_subscription_returns_404(self, auth_client):
        response = auth_client.post(cancel_url(99999))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_returns_401(self, db, active_subscription):
        client = APIClient()
        response = client.post(cancel_url(active_subscription.pk))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
