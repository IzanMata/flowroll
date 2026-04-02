"""
Tests for POST /api/auth/logout/

After logout the refresh token must be blacklisted — it can no longer be used
to obtain new access tokens.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

LOGOUT_URL = "/api/auth/logout/"
REFRESH_URL = "/api/auth/token/refresh/"


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="logoutuser@test.com",
        email="logoutuser@test.com",
        password="StrongPass123!",
    )


@pytest.fixture
def tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


@pytest.fixture
def auth_client(user, tokens):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


class TestLogout:
    def test_logout_returns_204(self, auth_client, tokens):
        response = auth_client.post(LOGOUT_URL, {"refresh": tokens["refresh"]}, format="json")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_blacklisted_refresh_cannot_obtain_new_access_token(self, auth_client, tokens):
        auth_client.post(LOGOUT_URL, {"refresh": tokens["refresh"]}, format="json")

        client = APIClient()
        response = client.post(REFRESH_URL, {"refresh": tokens["refresh"]}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_twice_with_same_token_returns_400(self, auth_client, tokens):
        auth_client.post(LOGOUT_URL, {"refresh": tokens["refresh"]}, format="json")
        response = auth_client.post(LOGOUT_URL, {"refresh": tokens["refresh"]}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_logout_without_refresh_field_returns_400(self, auth_client):
        response = auth_client.post(LOGOUT_URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_logout_with_invalid_token_returns_400(self, auth_client):
        response = auth_client.post(LOGOUT_URL, {"refresh": "not.a.real.token"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_logout_returns_401(self, db, tokens):
        client = APIClient()
        response = client.post(LOGOUT_URL, {"refresh": tokens["refresh"]}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
