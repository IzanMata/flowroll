"""
Tests for modern auth systems:
  - AppleAuthService / POST /api/auth/social/apple/
  - MagicLinkService  / POST /api/auth/magic-link/ + /magic-link/verify/
  - PhoneOTPService   / POST /api/auth/phone/otp/ + /phone/otp/verify/
  - LogoutView access-token revocation via JTI blocklist
  - Rate-limiting regression: ChangePasswordView and VerifyEmailView
"""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

APPLE_URL = "/api/auth/social/apple/"
MAGIC_LINK_REQUEST_URL = "/api/auth/magic-link/"
MAGIC_LINK_VERIFY_URL = "/api/auth/magic-link/verify/"
PHONE_OTP_REQUEST_URL = "/api/auth/phone/otp/"
PHONE_OTP_VERIFY_URL = "/api/auth/phone/otp/verify/"
LOGOUT_URL = "/api/auth/logout/"
CHANGE_PASSWORD_URL = "/api/auth/change-password/"
VERIFY_EMAIL_URL = "/api/auth/verify-email/"


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="modern@test.com",
        email="modern@test.com",
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


# ─── Apple Sign-In ────────────────────────────────────────────────────────────


class TestAppleAuth:
    def test_missing_token_returns_400(self, db):
        client = APIClient()
        response = client.post(APPLE_URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_token_returns_400(self, db):
        with patch(
            "accounts.services.AppleAuthService.register_or_login_with_apple",
            side_effect=ValueError("Invalid Apple token"),
        ):
            client = APIClient()
            response = client.post(APPLE_URL, {"token": "bad.token"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid Apple token" in response.data["detail"]

    def test_valid_token_returns_jwt_pair(self, db, user):
        with patch(
            "accounts.services.AppleAuthService.register_or_login_with_apple",
            return_value=user,
        ):
            client = APIClient()
            response = client.post(APPLE_URL, {"token": "valid.apple.token"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data

    def test_unconfigured_apple_client_id_returns_400(self, db):
        with patch(
            "accounts.services.AppleAuthService.register_or_login_with_apple",
            side_effect=ValueError("Apple Sign-In is not configured."),
        ):
            client = APIClient()
            response = client.post(APPLE_URL, {"token": "any.token"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestAppleAuthService:
    def test_missing_kid_header_raises(self, db):
        import jwt as pyjwt
        from accounts.services import AppleAuthService

        with patch("django.conf.settings.APPLE_CLIENT_ID", "com.example.app"):
            with patch.object(pyjwt, "get_unverified_header", return_value={}):
                with pytest.raises(ValueError, match="missing the 'kid'"):
                    AppleAuthService.register_or_login_with_apple("dummy.token.here")

    def test_expired_token_raises(self, db):
        import jwt as pyjwt
        from accounts.services import AppleAuthService

        with patch("django.conf.settings.APPLE_CLIENT_ID", "com.example.app"):
            with patch.object(
                pyjwt, "get_unverified_header", return_value={"kid": "key1"}
            ):
                with patch.object(
                    AppleAuthService, "_get_public_key", return_value=MagicMock()
                ):
                    with patch.object(
                        pyjwt,
                        "decode",
                        side_effect=pyjwt.ExpiredSignatureError,
                    ):
                        with pytest.raises(ValueError, match="expired"):
                            AppleAuthService.register_or_login_with_apple("token")

    def test_creates_new_user_on_first_sign_in(self, db):
        from accounts.services import AppleAuthService
        import jwt as pyjwt
        from allauth.socialaccount.models import SocialAccount

        payload = {
            "sub": "apple_uid_123",
            "email": "newapple@example.com",
            "given_name": "Jane",
            "family_name": "Doe",
            "iss": AppleAuthService.APPLE_ISS,
            "aud": "com.example.app",
            "exp": 9999999999,
        }

        with patch("django.conf.settings.APPLE_CLIENT_ID", "com.example.app"):
            with patch.object(
                pyjwt, "get_unverified_header", return_value={"kid": "key1"}
            ):
                with patch.object(
                    AppleAuthService, "_get_public_key", return_value=MagicMock()
                ):
                    with patch.object(pyjwt, "decode", return_value=payload):
                        user = AppleAuthService.register_or_login_with_apple("token")

        assert User.objects.filter(email="newapple@example.com").exists()
        assert SocialAccount.objects.filter(provider="apple", uid="apple_uid_123").exists()
        assert user.first_name == "Jane"

    def test_returns_existing_user_on_subsequent_sign_in(self, db, user):
        from accounts.services import AppleAuthService
        import jwt as pyjwt
        from allauth.socialaccount.models import SocialAccount

        SocialAccount.objects.create(provider="apple", uid="existing_uid", user=user, extra_data={})

        payload = {"sub": "existing_uid", "iss": AppleAuthService.APPLE_ISS, "aud": "com.example.app", "exp": 9999999999}

        with patch("django.conf.settings.APPLE_CLIENT_ID", "com.example.app"):
            with patch.object(
                pyjwt, "get_unverified_header", return_value={"kid": "key1"}
            ):
                with patch.object(
                    AppleAuthService, "_get_public_key", return_value=MagicMock()
                ):
                    with patch.object(pyjwt, "decode", return_value=payload):
                        returned_user = AppleAuthService.register_or_login_with_apple("token")

        assert returned_user.pk == user.pk

    def test_creates_placeholder_user_when_email_withheld(self, db):
        from accounts.services import AppleAuthService
        import jwt as pyjwt

        payload = {
            "sub": "no_email_uid",
            "iss": AppleAuthService.APPLE_ISS,
            "aud": "com.example.app",
            "exp": 9999999999,
            # email intentionally absent
        }

        with patch("django.conf.settings.APPLE_CLIENT_ID", "com.example.app"):
            with patch.object(
                pyjwt, "get_unverified_header", return_value={"kid": "key1"}
            ):
                with patch.object(
                    AppleAuthService, "_get_public_key", return_value=MagicMock()
                ):
                    with patch.object(pyjwt, "decode", return_value=payload):
                        user = AppleAuthService.register_or_login_with_apple("token")

        assert user.username == "apple_no_email_uid"
        assert user.email == ""


# ─── Magic Link ───────────────────────────────────────────────────────────────


class TestMagicLinkRequest:
    def test_valid_email_returns_200(self, db, user):
        client = APIClient()
        with patch("accounts.services.MagicLinkService.request_link"):
            response = client.post(MAGIC_LINK_REQUEST_URL, {"email": user.email}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_unknown_email_still_returns_200(self, db):
        client = APIClient()
        response = client.post(
            MAGIC_LINK_REQUEST_URL, {"email": "nobody@example.com"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_missing_email_returns_400(self, db):
        client = APIClient()
        response = client.post(MAGIC_LINK_REQUEST_URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestMagicLinkVerify:
    def test_valid_token_returns_jwt_pair(self, db, user):
        from accounts.services import MagicLinkService
        from django.core.cache import cache

        token = "securetokenvalue123"
        cache.set(f"{MagicLinkService.CACHE_PREFIX}{token}", user.pk, timeout=900)

        client = APIClient()
        response = client.post(MAGIC_LINK_VERIFY_URL, {"token": token}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data

    def test_token_is_single_use(self, db, user):
        from accounts.services import MagicLinkService
        from django.core.cache import cache

        token = "singleusetoken456"
        cache.set(f"{MagicLinkService.CACHE_PREFIX}{token}", user.pk, timeout=900)

        client = APIClient()
        client.post(MAGIC_LINK_VERIFY_URL, {"token": token}, format="json")
        response = client.post(MAGIC_LINK_VERIFY_URL, {"token": token}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_expired_token_returns_400(self, db):
        client = APIClient()
        response = client.post(MAGIC_LINK_VERIFY_URL, {"token": "nonexistent_token"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_token_returns_400(self, db):
        client = APIClient()
        response = client.post(MAGIC_LINK_VERIFY_URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestMagicLinkService:
    def test_request_link_sends_email_to_known_user(self, db, user, mailoutbox):
        from accounts.services import MagicLinkService

        MagicLinkService.request_link(user.email)
        assert len(mailoutbox) == 1
        assert user.email in mailoutbox[0].to

    def test_request_link_silently_ignores_unknown_email(self, db, mailoutbox):
        from accounts.services import MagicLinkService

        MagicLinkService.request_link("nobody@example.com")
        assert len(mailoutbox) == 0

    def test_verify_link_returns_correct_user(self, db, user):
        from accounts.services import MagicLinkService
        from django.core.cache import cache

        token = "testtoken789"
        cache.set(f"{MagicLinkService.CACHE_PREFIX}{token}", user.pk, timeout=900)
        returned = MagicLinkService.verify_link(token)
        assert returned.pk == user.pk

    def test_verify_link_deletes_token_after_use(self, db, user):
        from accounts.services import MagicLinkService
        from django.core.cache import cache

        token = "consumetoken"
        cache.set(f"{MagicLinkService.CACHE_PREFIX}{token}", user.pk, timeout=900)
        MagicLinkService.verify_link(token)
        assert cache.get(f"{MagicLinkService.CACHE_PREFIX}{token}") is None

    def test_verify_link_raises_for_invalid_token(self, db):
        from accounts.services import MagicLinkService

        with pytest.raises(ValueError, match="Invalid or expired"):
            MagicLinkService.verify_link("nonexistent_token")


# ─── Phone OTP ────────────────────────────────────────────────────────────────


class TestPhoneOTPRequest:
    def test_valid_phone_triggers_send_and_returns_200(self, db):
        with patch("accounts.services.PhoneOTPService.send_otp"):
            client = APIClient()
            response = client.post(
                PHONE_OTP_REQUEST_URL, {"phone": "+34612345678"}, format="json"
            )
        assert response.status_code == status.HTTP_200_OK

    def test_invalid_phone_returns_400(self, db):
        client = APIClient()
        response = client.post(PHONE_OTP_REQUEST_URL, {"phone": "notaphone"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_phone_returns_400(self, db):
        client = APIClient()
        response = client.post(PHONE_OTP_REQUEST_URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestPhoneOTPVerify:
    def test_valid_otp_returns_jwt_pair(self, db):
        with patch("accounts.services.PhoneOTPService.verify_otp") as mock_verify:
            mock_verify.return_value = User.objects.create_user(
                username="phone_34612345678", email=""
            )
            client = APIClient()
            response = client.post(
                PHONE_OTP_VERIFY_URL,
                {"phone": "+34612345678", "otp": "123456"},
                format="json",
            )
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data

    def test_wrong_otp_returns_400(self, db):
        with patch(
            "accounts.services.PhoneOTPService.verify_otp",
            side_effect=ValueError("Incorrect OTP."),
        ):
            client = APIClient()
            response = client.post(
                PHONE_OTP_VERIFY_URL,
                {"phone": "+34612345678", "otp": "000000"},
                format="json",
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_fields_returns_400(self, db):
        client = APIClient()
        response = client.post(PHONE_OTP_VERIFY_URL, {"phone": "+34612345678"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestPhoneOTPService:
    VALID_PHONE = "+34612345678"

    def test_send_otp_stores_code_in_cache(self, db):
        from accounts.services import PhoneOTPService
        from django.core.cache import cache

        with patch("twilio.rest.Client") as MockClient:
            MockClient.return_value.messages.create.return_value = MagicMock()
            with patch("django.conf.settings.TWILIO_ACCOUNT_SID", "ACtest"):
                with patch("django.conf.settings.TWILIO_AUTH_TOKEN", "token"):
                    with patch("django.conf.settings.TWILIO_PHONE_NUMBER", "+15005550006"):
                        PhoneOTPService.send_otp(self.VALID_PHONE)

        otp = cache.get(f"{PhoneOTPService.OTP_PREFIX}{self.VALID_PHONE}")
        assert otp is not None
        assert len(otp) == 6
        assert otp.isdigit()

    def test_verify_otp_correct_creates_user(self, db):
        from accounts.services import PhoneOTPService
        from django.core.cache import cache

        cache.set(f"{PhoneOTPService.OTP_PREFIX}{self.VALID_PHONE}", "123456", timeout=300)
        cache.set(f"{PhoneOTPService.ATTEMPTS_PREFIX}{self.VALID_PHONE}", 0, timeout=300)

        user = PhoneOTPService.verify_otp(self.VALID_PHONE, "123456")
        assert user is not None
        assert User.objects.filter(username="phone_34612345678").exists()

    def test_verify_otp_correct_returns_existing_user(self, db, user):
        from accounts.services import PhoneOTPService
        from accounts.models import UserPhoneNumber
        from django.core.cache import cache

        UserPhoneNumber.objects.create(user=user, phone=self.VALID_PHONE, is_verified=True)
        cache.set(f"{PhoneOTPService.OTP_PREFIX}{self.VALID_PHONE}", "654321", timeout=300)
        cache.set(f"{PhoneOTPService.ATTEMPTS_PREFIX}{self.VALID_PHONE}", 0, timeout=300)

        returned = PhoneOTPService.verify_otp(self.VALID_PHONE, "654321")
        assert returned.pk == user.pk

    def test_verify_otp_wrong_increments_attempts(self, db):
        from accounts.services import PhoneOTPService
        from django.core.cache import cache

        cache.set(f"{PhoneOTPService.OTP_PREFIX}{self.VALID_PHONE}", "111111", timeout=300)
        cache.set(f"{PhoneOTPService.ATTEMPTS_PREFIX}{self.VALID_PHONE}", 0, timeout=300)

        with pytest.raises(ValueError, match="Incorrect OTP"):
            PhoneOTPService.verify_otp(self.VALID_PHONE, "999999")

        attempts = cache.get(f"{PhoneOTPService.ATTEMPTS_PREFIX}{self.VALID_PHONE}")
        assert attempts == 1

    def test_verify_otp_max_attempts_invalidates_code(self, db):
        from accounts.services import PhoneOTPService
        from django.core.cache import cache

        cache.set(f"{PhoneOTPService.OTP_PREFIX}{self.VALID_PHONE}", "111111", timeout=300)
        cache.set(
            f"{PhoneOTPService.ATTEMPTS_PREFIX}{self.VALID_PHONE}",
            PhoneOTPService.MAX_ATTEMPTS,
            timeout=300,
        )

        with pytest.raises(ValueError, match="Too many incorrect attempts"):
            PhoneOTPService.verify_otp(self.VALID_PHONE, "111111")

        assert cache.get(f"{PhoneOTPService.OTP_PREFIX}{self.VALID_PHONE}") is None

    def test_verify_otp_expired_raises(self, db):
        from accounts.services import PhoneOTPService

        with pytest.raises(ValueError, match="expired or was never requested"):
            PhoneOTPService.verify_otp(self.VALID_PHONE, "123456")

    def test_normalise_invalid_phone_raises(self, db):
        from accounts.services import PhoneOTPService

        with pytest.raises(ValueError, match="Invalid phone number"):
            PhoneOTPService._normalise("notaphone")


# ─── Logout access token revocation ─────────────────────────────────────────


class TestLogoutAccessTokenRevocation:
    def test_revoked_access_token_rejected_on_next_request(self, db, user, tokens):
        """After logout the access token JTI must be in the Redis blocklist."""
        from django.core.cache import cache
        from rest_framework_simplejwt.tokens import AccessToken

        decoded = AccessToken(tokens["access"])
        jti = decoded["jti"]

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        client.post(LOGOUT_URL, {"refresh": tokens["refresh"]}, format="json")

        assert cache.get(f"revoked_jti:{jti}") == "1"

    def test_me_endpoint_rejects_revoked_access_token(self, db, user, tokens):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        client.post(LOGOUT_URL, {"refresh": tokens["refresh"]}, format="json")

        response = client.get("/api/auth/me/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── Rate-limiting regression ─────────────────────────────────────────────────


class TestChangePasswordThrottle:
    def test_change_password_view_has_throttle_class(self):
        from accounts.views import ChangePasswordView
        from config.throttles import ChangePasswordRateThrottle

        throttle_classes = [cls for cls in ChangePasswordView.throttle_classes]
        assert ChangePasswordRateThrottle in throttle_classes


class TestEmailVerificationThrottle:
    def test_verify_email_view_has_throttle_class(self):
        from accounts.views import VerifyEmailView
        from config.throttles import EmailVerificationRateThrottle

        throttle_classes = [cls for cls in VerifyEmailView.throttle_classes]
        assert EmailVerificationRateThrottle in throttle_classes
