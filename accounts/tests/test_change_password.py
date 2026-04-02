"""
Tests for POST /api/auth/change-password/
"""

import pytest
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

CHANGE_URL = "/api/auth/change-password/"
TOKEN_URL = "/api/auth/token/"


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="changepass@test.com",
        email="changepass@test.com",
        password="OldPass123!",
    )


@pytest.fixture
def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


class TestChangePassword:
    def test_valid_change_returns_200(self, auth_client):
        response = auth_client.post(
            CHANGE_URL,
            {"old_password": "OldPass123!", "new_password": "NewPass456!", "new_password_confirm": "NewPass456!"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

    def test_can_login_with_new_password(self, auth_client, user):
        auth_client.post(
            CHANGE_URL,
            {"old_password": "OldPass123!", "new_password": "NewPass456!", "new_password_confirm": "NewPass456!"},
            format="json",
        )
        client = APIClient()
        response = client.post(TOKEN_URL, {"username": user.username, "password": "NewPass456!"}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_old_password_no_longer_works(self, auth_client, user):
        auth_client.post(
            CHANGE_URL,
            {"old_password": "OldPass123!", "new_password": "NewPass456!", "new_password_confirm": "NewPass456!"},
            format="json",
        )
        client = APIClient()
        response = client.post(TOKEN_URL, {"username": user.username, "password": "OldPass123!"}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_wrong_old_password_returns_400(self, auth_client):
        response = auth_client.post(
            CHANGE_URL,
            {"old_password": "WrongOld!", "new_password": "NewPass456!", "new_password_confirm": "NewPass456!"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_password_mismatch_returns_400(self, auth_client):
        response = auth_client.post(
            CHANGE_URL,
            {"old_password": "OldPass123!", "new_password": "NewPass456!", "new_password_confirm": "Different!"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_weak_new_password_returns_400(self, auth_client):
        response = auth_client.post(
            CHANGE_URL,
            {"old_password": "OldPass123!", "new_password": "123", "new_password_confirm": "123"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_returns_401(self, db):
        client = APIClient()
        response = client.post(
            CHANGE_URL,
            {"old_password": "OldPass123!", "new_password": "NewPass456!", "new_password_confirm": "NewPass456!"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_missing_fields_returns_400(self, auth_client):
        response = auth_client.post(CHANGE_URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
