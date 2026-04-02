"""
Tests for the password-reset flow:
  POST /api/auth/password-reset/         — request a reset token by email
  POST /api/auth/password-reset/confirm/ — set a new password with uid + token
"""

import pytest
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient

REQUEST_URL = "/api/auth/password-reset/"
CONFIRM_URL = "/api/auth/password-reset/confirm/"
TOKEN_URL = "/api/auth/token/"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="resetuser@test.com",
        email="resetuser@test.com",
        password="OldPassword123!",
    )


@pytest.fixture
def reset_payload(user):
    """Valid uid + token for the test user."""
    return {
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": default_token_generator.make_token(user),
    }


# ─── Request endpoint ─────────────────────────────────────────────────────────

class TestPasswordResetRequest:
    def test_known_email_returns_200(self, client, user):
        response = client.post(REQUEST_URL, {"email": user.email}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_unknown_email_also_returns_200(self, client, db):
        """Must not reveal whether an account exists."""
        response = client.post(REQUEST_URL, {"email": "nobody@example.com"}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_response_body_is_generic(self, client, user):
        response = client.post(REQUEST_URL, {"email": user.email}, format="json")
        assert "detail" in response.data

    def test_missing_email_returns_400(self, client, db):
        response = client.post(REQUEST_URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_email_format_returns_400(self, client, db):
        response = client.post(REQUEST_URL, {"email": "notanemail"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_sends_email(self, client, user, mailoutbox):
        client.post(REQUEST_URL, {"email": user.email}, format="json")
        assert len(mailoutbox) == 1
        assert user.email in mailoutbox[0].to

    def test_email_contains_uid_and_token(self, client, user, mailoutbox):
        client.post(REQUEST_URL, {"email": user.email}, format="json")
        body = mailoutbox[0].body
        assert "uid" in body
        assert "token" in body


# ─── Confirm endpoint ─────────────────────────────────────────────────────────

class TestPasswordResetConfirm:
    def test_valid_uid_and_token_resets_password(self, client, user, reset_payload):
        payload = {**reset_payload, "new_password": "NewPass456!", "new_password_confirm": "NewPass456!"}
        response = client.post(CONFIRM_URL, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.check_password("NewPass456!")

    def test_can_login_with_new_password(self, client, user, reset_payload):
        client.post(
            CONFIRM_URL,
            {**reset_payload, "new_password": "NewPass456!", "new_password_confirm": "NewPass456!"},
            format="json",
        )
        response = client.post(
            TOKEN_URL,
            {"username": user.username, "password": "NewPass456!"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

    def test_old_password_no_longer_works(self, client, user, reset_payload):
        client.post(
            CONFIRM_URL,
            {**reset_payload, "new_password": "NewPass456!", "new_password_confirm": "NewPass456!"},
            format="json",
        )
        response = client.post(
            TOKEN_URL,
            {"username": user.username, "password": "OldPassword123!"},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_token_cannot_be_reused(self, client, user, reset_payload):
        payload = {**reset_payload, "new_password": "NewPass456!", "new_password_confirm": "NewPass456!"}
        client.post(CONFIRM_URL, payload, format="json")
        # Second use of the same token must fail (password change invalidates it)
        payload2 = {**reset_payload, "new_password": "AnotherPass789!", "new_password_confirm": "AnotherPass789!"}
        response = client.post(CONFIRM_URL, payload2, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_token_returns_400(self, client, user, reset_payload):
        payload = {**reset_payload, "token": "invalidtoken", "new_password": "NewPass456!", "new_password_confirm": "NewPass456!"}
        response = client.post(CONFIRM_URL, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_uid_returns_400(self, client, reset_payload):
        payload = {**reset_payload, "uid": "notavaliduid", "new_password": "NewPass456!", "new_password_confirm": "NewPass456!"}
        response = client.post(CONFIRM_URL, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_password_mismatch_returns_400(self, client, reset_payload):
        payload = {**reset_payload, "new_password": "NewPass456!", "new_password_confirm": "DifferentPass!"}
        response = client.post(CONFIRM_URL, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_weak_password_returns_400(self, client, reset_payload):
        payload = {**reset_payload, "new_password": "123", "new_password_confirm": "123"}
        response = client.post(CONFIRM_URL, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_fields_returns_400(self, client, db):
        response = client.post(CONFIRM_URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
