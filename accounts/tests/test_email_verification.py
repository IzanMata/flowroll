"""
Tests for email verification flow:
  POST /api/auth/register/             — sends verification email on signup
  POST /api/auth/verify-email/         — confirm email with uid+token
  POST /api/auth/resend-verification/  — resend if not yet verified
  GET  /api/auth/me/                   — exposes email_verified field
"""

import pytest
from django.contrib.auth.models import User
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.services import EmailVerificationService, _email_token_generator

REGISTER_URL = "/api/auth/register/"
VERIFY_URL = "/api/auth/verify-email/"
RESEND_URL = "/api/auth/resend-verification/"
ME_URL = "/api/auth/me/"


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="verify@test.com",
        email="verify@test.com",
        password="Pass123!",
    )


@pytest.fixture
def verification_payload(user):
    return {
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": _email_token_generator.make_token(user),
    }


@pytest.fixture
def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


class TestRegistrationSendsVerificationEmail:
    def test_register_sends_email(self, db, mailoutbox):
        client = APIClient()
        client.post(
            REGISTER_URL,
            {"email": "new@test.com", "password": "Pass123!", "password_confirm": "Pass123!"},
            format="json",
        )
        assert len(mailoutbox) == 1
        assert "new@test.com" in mailoutbox[0].to

    def test_register_email_contains_uid_and_token(self, db, mailoutbox):
        client = APIClient()
        client.post(
            REGISTER_URL,
            {"email": "new2@test.com", "password": "Pass123!", "password_confirm": "Pass123!"},
            format="json",
        )
        body = mailoutbox[0].body
        assert "uid" in body
        assert "token" in body


class TestVerifyEmail:
    def test_valid_token_verifies_email(self, db, user, verification_payload):
        EmailVerificationService.send_verification(user)
        client = APIClient()
        response = client.post(VERIFY_URL, verification_payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert EmailVerificationService.is_verified(user)

    def test_invalid_token_returns_400(self, db, user, verification_payload):
        client = APIClient()
        response = client.post(
            VERIFY_URL, {**verification_payload, "token": "badtoken"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_uid_returns_400(self, db):
        client = APIClient()
        response = client.post(VERIFY_URL, {"uid": "notvalid", "token": "abc"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_token_invalidated_after_password_change(self, db, user, verification_payload):
        # Change the password — this invalidates all existing tokens
        user.set_password("DifferentPass!")
        user.save()
        client = APIClient()
        response = client.post(VERIFY_URL, verification_payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestResendVerification:
    def test_resend_sends_email(self, db, user, mailoutbox):
        EmailVerificationService.send_verification(user)
        mailoutbox.clear()
        client = APIClient()
        response = client.post(RESEND_URL, {"email": user.email}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert len(mailoutbox) == 1

    def test_resend_for_already_verified_does_not_send(self, db, user, verification_payload, mailoutbox):
        EmailVerificationService.send_verification(user)
        EmailVerificationService.verify(verification_payload["uid"], verification_payload["token"])
        mailoutbox.clear()
        client = APIClient()
        client.post(RESEND_URL, {"email": user.email}, format="json")
        assert len(mailoutbox) == 0

    def test_resend_unknown_email_returns_200(self, db, mailoutbox):
        client = APIClient()
        response = client.post(RESEND_URL, {"email": "nobody@nowhere.com"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert len(mailoutbox) == 0


class TestMeEmailVerifiedField:
    def test_me_shows_email_not_verified_before_confirmation(self, auth_client):
        response = auth_client.get(ME_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email_verified"] is False

    def test_me_shows_email_verified_after_confirmation(self, auth_client, user, verification_payload):
        EmailVerificationService.send_verification(user)
        EmailVerificationService.verify(verification_payload["uid"], verification_payload["token"])
        response = auth_client.get(ME_URL)
        assert response.data["email_verified"] is True
