"""
Tests for JWT authentication endpoints:
  POST /api/auth/token/         — obtain access + refresh tokens
  POST /api/auth/token/refresh/ — rotate refresh token
"""

import pytest
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from factories import UserFactory

TOKEN_URL = "/api/auth/token/"
REFRESH_URL = "/api/auth/token/refresh/"


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def active_user(db):
    return UserFactory(username="testuser", password=None)


@pytest.fixture
def active_user_with_password(db):
    user = User.objects.create_user(
        username="loginuser",
        password="StrongPass123!",
        email="loginuser@example.com",
        is_active=True,
    )
    return user


@pytest.fixture
def inactive_user(db):
    return User.objects.create_user(
        username="inactiveuser",
        password="StrongPass123!",
        is_active=False,
    )


# ─── Token Obtain (Login) ────────────────────────────────────────────────────


class TestTokenObtain:
    def test_valid_credentials_returns_tokens(self, client, active_user_with_password):
        response = client.post(
            TOKEN_URL,
            {"username": "loginuser", "password": "StrongPass123!"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data

    def test_access_token_is_non_empty_string(self, client, active_user_with_password):
        response = client.post(
            TOKEN_URL,
            {"username": "loginuser", "password": "StrongPass123!"},
            format="json",
        )
        assert isinstance(response.data["access"], str)
        assert len(response.data["access"]) > 20

    def test_wrong_password_returns_401(self, client, active_user_with_password):
        response = client.post(
            TOKEN_URL,
            {"username": "loginuser", "password": "WrongPassword!"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_nonexistent_user_returns_401(self, client, db):
        response = client.post(
            TOKEN_URL,
            {"username": "ghost", "password": "whatever"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_inactive_user_returns_401(self, client, inactive_user):
        response = client.post(
            TOKEN_URL,
            {"username": "inactiveuser", "password": "StrongPass123!"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_missing_password_returns_400(self, client, active_user_with_password):
        response = client.post(
            TOKEN_URL,
            {"username": "loginuser"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_username_returns_400(self, client, active_user_with_password):
        response = client.post(
            TOKEN_URL,
            {"password": "StrongPass123!"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_empty_body_returns_400(self, client, db):
        response = client.post(TOKEN_URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_wrong_credentials_do_not_expose_user_existence(
        self, client, active_user_with_password, db
    ):
        """Both known-user/wrong-pass and unknown-user should return the same status."""
        r1 = client.post(
            TOKEN_URL,
            {"username": "loginuser", "password": "WrongPass"},
            format="json",
        )
        r2 = client.post(
            TOKEN_URL,
            {"username": "doesnotexist", "password": "WrongPass"},
            format="json",
        )
        assert r1.status_code == r2.status_code == status.HTTP_401_UNAUTHORIZED


# ─── Token Refresh ────────────────────────────────────────────────────────────


class TestTokenRefresh:
    def test_valid_refresh_returns_new_access_token(self, client, active_user_with_password):
        # Obtain tokens first
        login = client.post(
            TOKEN_URL,
            {"username": "loginuser", "password": "StrongPass123!"},
            format="json",
        )
        refresh_token = login.data["refresh"]

        response = client.post(
            REFRESH_URL,
            {"refresh": refresh_token},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data

    def test_refresh_rotates_refresh_token(self, client, active_user_with_password):
        """ROTATE_REFRESH_TOKENS=True: a new refresh token is issued on each refresh."""
        login = client.post(
            TOKEN_URL,
            {"username": "loginuser", "password": "StrongPass123!"},
            format="json",
        )
        old_refresh = login.data["refresh"]

        response = client.post(
            REFRESH_URL,
            {"refresh": old_refresh},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        new_refresh = response.data.get("refresh")
        assert new_refresh is not None
        assert new_refresh != old_refresh

    def test_used_refresh_token_is_blacklisted(self, client, active_user_with_password):
        """BLACKLIST_AFTER_ROTATION=True: the old token cannot be reused."""
        login = client.post(
            TOKEN_URL,
            {"username": "loginuser", "password": "StrongPass123!"},
            format="json",
        )
        old_refresh = login.data["refresh"]

        # Use the refresh token once
        client.post(REFRESH_URL, {"refresh": old_refresh}, format="json")

        # Attempting to reuse it must fail
        response = client.post(
            REFRESH_URL,
            {"refresh": old_refresh},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_refresh_token_returns_401(self, client, db):
        response = client.post(
            REFRESH_URL,
            {"refresh": "this.is.not.a.valid.token"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_missing_refresh_field_returns_400(self, client, db):
        response = client.post(REFRESH_URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ─── Bearer Token usage in protected endpoints ────────────────────────────────


class TestBearerTokenAccess:
    def test_valid_bearer_token_grants_access(self, client, active_user_with_password):
        login = client.post(
            TOKEN_URL,
            {"username": "loginuser", "password": "StrongPass123!"},
            format="json",
        )
        access = login.data["access"]

        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        # /api/academies/ requires IsAuthenticated
        response = client.get("/api/academies/")
        assert response.status_code != status.HTTP_401_UNAUTHORIZED

    def test_no_token_returns_401_on_protected_endpoint(self, db):
        anon = APIClient()
        response = anon.get("/api/academies/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_malformed_bearer_token_returns_401(self, db):
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION="Bearer notarealtoken")
        response = bad.get("/api/academies/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_token_generated_with_simplejwt_helper_works(self, db):
        """Shortcut used in many other tests: RefreshToken.for_user()."""
        user = UserFactory()
        refresh = RefreshToken.for_user(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        response = client.get("/api/academies/")
        assert response.status_code != status.HTTP_401_UNAUTHORIZED


# ─── User model constraints ───────────────────────────────────────────────────


class TestUserModelConstraints:
    def test_username_must_be_unique(self, db):
        User.objects.create_user(username="duplicated", password="pass")
        with pytest.raises(Exception):
            User.objects.create_user(username="duplicated", password="other")

    def test_inactive_user_cannot_authenticate(self, db):
        user = User.objects.create_user(
            username="sleeper", password="pass123", is_active=False
        )
        from django.contrib.auth import authenticate

        result = authenticate(username="sleeper", password="pass123")
        assert result is None

    def test_active_user_can_authenticate(self, db):
        User.objects.create_user(username="awake", password="pass123", is_active=True)
        from django.contrib.auth import authenticate

        result = authenticate(username="awake", password="pass123")
        assert result is not None
        assert result.username == "awake"

    def test_password_is_hashed_not_stored_in_plain_text(self, db):
        user = User.objects.create_user(username="secure", password="MySecret!")
        assert user.password != "MySecret!"
        assert user.check_password("MySecret!") is True

    def test_user_factory_creates_active_user(self, db):
        user = UserFactory()
        assert user.is_active is True
        assert user.pk is not None

    def test_user_factory_password_is_testpass123(self, db):
        user = UserFactory()
        assert user.check_password("testpass123") is True
