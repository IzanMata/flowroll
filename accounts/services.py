"""
Registration and social-auth services for the accounts app.

Services:
  - RegistrationService: email/password sign-up, Google OAuth sign-up/in
  - EmailVerificationService: send + verify email confirmation tokens
  - PasswordResetService: request + confirm password resets
  - AppleAuthService: Sign in with Apple (RS256 JWKS verification)
  - MagicLinkService: passwordless email login via short-lived Redis tokens
  - PhoneOTPService: SMS one-time password login/registration via Twilio

All services return a Django User instance; the caller issues JWT tokens
via SimpleJWT's RefreshToken.for_user().
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction


class EmailVerificationTokenGenerator:
    """
    Thin wrapper around Django's PasswordResetTokenGenerator with a different
    key_salt so email-verification tokens cannot be used as password-reset
    tokens and vice-versa.
    """

    def __init__(self):
        from django.contrib.auth.tokens import PasswordResetTokenGenerator
        self._gen = PasswordResetTokenGenerator()
        self._gen.key_salt = "flowroll.accounts.EmailVerificationTokenGenerator"

    def make_token(self, user):
        return self._gen.make_token(user)

    def check_token(self, user, token):
        return self._gen.check_token(user, token)


_email_token_generator = EmailVerificationTokenGenerator()


class EmailVerificationService:
    @staticmethod
    def send_verification(user: User) -> None:
        """
        Create (or update) an unverified EmailAddress record for *user* and
        send a verification email.  Safe to call multiple times — acts as a
        resend when the record already exists.
        """
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        from allauth.account.models import EmailAddress
        from django.core.mail import send_mail

        EmailAddress.objects.get_or_create(
            user=user,
            email=user.email,
            defaults={"primary": True, "verified": False},
        )

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = _email_token_generator.make_token(user)

        send_mail(
            subject="FlowRoll — Verify your email",
            message=(
                f"Hi {user.first_name or user.username},\n\n"
                "Please verify your email address using the following:\n\n"
                f"  uid:   {uid}\n"
                f"  token: {token}\n\n"
                "This token expires after 24 hours.\n\n"
                "If you did not create a FlowRoll account, ignore this email."
            ),
            from_email=None,
            recipient_list=[user.email],
            fail_silently=True,
        )

    @staticmethod
    def verify(uid: str, token: str) -> User:
        """
        Validate *uid* + *token* and mark the user's email as verified.
        Raises ValueError on invalid/expired tokens.
        """
        from django.utils.encoding import force_str
        from django.utils.http import urlsafe_base64_decode
        from allauth.account.models import EmailAddress

        try:
            pk = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=pk)
        except (User.DoesNotExist, ValueError, OverflowError):
            raise ValueError("Invalid verification link.")

        if not _email_token_generator.check_token(user, token):
            raise ValueError("Invalid or expired verification token.")

        EmailAddress.objects.filter(user=user, email=user.email).update(verified=True, primary=True)
        return user

    @staticmethod
    def is_verified(user: User) -> bool:
        from allauth.account.models import EmailAddress
        return EmailAddress.objects.filter(user=user, email=user.email, verified=True).exists()


class PasswordResetService:
    @staticmethod
    def request_reset(email: str) -> None:
        """
        Generate a password-reset token for the user with this email and send
        it by email.  Always returns without error to avoid leaking whether the
        address exists.
        """
        from django.contrib.auth.tokens import default_token_generator
        from django.core.mail import send_mail
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return  # Silently ignore — do not reveal account existence

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        send_mail(
            subject="FlowRoll — Password reset",
            message=(
                f"Hi {user.first_name or user.username},\n\n"
                f"Use the following uid and token to reset your password:\n\n"
                f"  uid:   {uid}\n"
                f"  token: {token}\n\n"
                "This link expires after 24 hours and can only be used once.\n\n"
                "If you did not request a password reset, ignore this email."
            ),
            from_email=None,  # uses DEFAULT_FROM_EMAIL
            recipient_list=[user.email],
            fail_silently=True,
        )

    @staticmethod
    def confirm_reset(uid: str, token: str, new_password: str) -> None:
        """
        Validate the uid/token pair and set new_password on the user.
        Raises ValueError if uid or token is invalid or expired.
        """
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_str
        from django.utils.http import urlsafe_base64_decode

        try:
            pk = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=pk)
        except (User.DoesNotExist, ValueError, OverflowError):
            raise ValueError("Invalid password reset link.")

        if not default_token_generator.check_token(user, token):
            raise ValueError("Invalid or expired password reset token.")

        try:
            password_validation.validate_password(new_password, user)
        except ValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc

        user.set_password(new_password)
        user.save(update_fields=["password"])


class RegistrationService:
    @staticmethod
    @transaction.atomic
    def register_with_email(
        email: str,
        password: str,
        first_name: str = "",
        last_name: str = "",
    ) -> User:
        """Create a new User with email/password.

        Raises ValueError if the email is already in use or if Django's
        password validators reject the password.
        """
        email = email.lower().strip()

        if User.objects.filter(email__iexact=email).exists():
            raise ValueError("A user with that email already exists.")

        # Run Django's built-in password validators
        try:
            password_validation.validate_password(password)
        except ValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        EmailVerificationService.send_verification(user)
        return user

    @staticmethod
    @transaction.atomic
    def register_or_login_with_google(google_id_token: str) -> User:
        """Verify a Google ID token and return (or create) the matching User.

        The token must be a valid Google Sign-In ID token issued to this app's
        GOOGLE_CLIENT_ID.  Raises ValueError on invalid / expired tokens.

        Uses allauth's SocialAccount model so social identities are stored in
        the standard allauth schema (provider + uid composite key).
        """
        from google.auth.exceptions import GoogleAuthError
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2.id_token import verify_oauth2_token

        from allauth.socialaccount.models import SocialAccount

        client_id = settings.GOOGLE_CLIENT_ID
        if not client_id:
            raise ValueError(
                "Google OAuth is not configured. Set the GOOGLE_CLIENT_ID environment variable."
            )

        try:
            idinfo = verify_oauth2_token(google_id_token, GoogleRequest(), client_id)
        except (GoogleAuthError, ValueError) as exc:
            raise ValueError(f"Invalid Google token: {exc}") from exc

        google_uid = idinfo["sub"]
        email = idinfo.get("email", "").lower().strip()

        try:
            social = SocialAccount.objects.select_related("user").get(
                provider="google", uid=google_uid
            )
            return social.user
        except SocialAccount.DoesNotExist:
            pass

        # No existing social account — get or create user by email
        user, created = User.objects.get_or_create(
            email__iexact=email,
            defaults={
                "username": email,
                "email": email,
                "first_name": idinfo.get("given_name", ""),
                "last_name": idinfo.get("family_name", ""),
            },
        )
        if created and not user.username:
            user.username = email
            user.save(update_fields=["username"])

        # get_or_create guards against a duplicate-uid IntegrityError on
        # concurrent sign-ins with the same Google token.
        SocialAccount.objects.get_or_create(
            provider="google",
            uid=google_uid,
            defaults={"user": user, "extra_data": idinfo},
        )
        return user


# ─── Apple Sign-In ────────────────────────────────────────────────────────────

class AppleAuthService:
    """
    Verify a Sign in with Apple identity_token (RS256 JWT) and return (or
    create) the matching Django User.

    Apple publishes its public keys at APPLE_JWKS_URL; they are cached in
    Django's cache for JWKS_CACHE_TTL seconds to avoid hammering Apple's CDN
    on every sign-in request.

    Important Apple behaviour:
    - The ``email`` claim is only present on the *first* sign-in.  Subsequent
      sign-ins include only ``sub`` (the stable user identifier).
    - Apple may relay emails (@privaterelay.appleid.com) — these are real
      addresses; treat them like any other email.
    - ``aud`` must equal the Service ID (web) or Bundle ID (native) configured
      as APPLE_CLIENT_ID in settings.
    """

    APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
    APPLE_ISS = "https://appleid.apple.com"
    JWKS_CACHE_KEY = "apple_jwks"
    JWKS_CACHE_TTL = 3600  # 1 hour

    @classmethod
    def _fetch_apple_keys(cls) -> list:
        """Return Apple's current JWKS key list, using cache when possible."""
        from django.core.cache import cache
        import requests as http_requests

        cached = cache.get(cls.JWKS_CACHE_KEY)
        if cached is not None:
            return cached

        resp = http_requests.get(cls.APPLE_JWKS_URL, timeout=10)
        resp.raise_for_status()
        keys = resp.json()["keys"]
        cache.set(cls.JWKS_CACHE_KEY, keys, timeout=cls.JWKS_CACHE_TTL)
        return keys

    @classmethod
    def _get_public_key(cls, kid: str):
        """Return the RSA public key matching *kid*, refreshing cache if needed."""
        import json
        import jwt as pyjwt
        from jwt.algorithms import RSAAlgorithm
        from django.core.cache import cache

        for attempt in range(2):
            keys = cls._fetch_apple_keys()
            for key_data in keys:
                if key_data.get("kid") == kid:
                    return RSAAlgorithm.from_jwk(json.dumps(key_data))
            # kid not found — Apple may have rotated keys; bust cache and retry once
            if attempt == 0:
                cache.delete(cls.JWKS_CACHE_KEY)

        raise ValueError("Apple public key not found for this token. Try again.")

    @staticmethod
    @transaction.atomic
    def register_or_login_with_apple(identity_token: str) -> User:
        """
        Verify *identity_token* and return (or create) the matching User.
        Raises ValueError on invalid / expired tokens or misconfiguration.
        """
        import jwt as pyjwt
        from allauth.socialaccount.models import SocialAccount

        client_id = settings.APPLE_CLIENT_ID
        if not client_id:
            raise ValueError(
                "Apple Sign-In is not configured. Set the APPLE_CLIENT_ID environment variable."
            )

        try:
            header = pyjwt.get_unverified_header(identity_token)
        except pyjwt.DecodeError as exc:
            raise ValueError(f"Invalid Apple token: {exc}") from exc

        kid = header.get("kid")
        if not kid:
            raise ValueError("Apple token is missing the 'kid' header.")

        public_key = AppleAuthService._get_public_key(kid)

        try:
            payload = pyjwt.decode(
                identity_token,
                key=public_key,
                algorithms=["RS256"],
                audience=client_id,
                issuer=AppleAuthService.APPLE_ISS,
            )
        except pyjwt.ExpiredSignatureError:
            raise ValueError("Apple token has expired.")
        except pyjwt.InvalidTokenError as exc:
            raise ValueError(f"Invalid Apple token: {exc}") from exc

        apple_uid = payload["sub"]
        email = payload.get("email", "").lower().strip()

        # Fast path: existing social account
        try:
            social = SocialAccount.objects.select_related("user").get(
                provider="apple", uid=apple_uid
            )
            return social.user
        except SocialAccount.DoesNotExist:
            pass

        # Get or create user by email when available
        if email:
            user, _ = User.objects.get_or_create(
                email__iexact=email,
                defaults={
                    "username": email,
                    "email": email,
                    # Name is only in the payload on first sign-in
                    "first_name": payload.get("given_name", ""),
                    "last_name": payload.get("family_name", ""),
                },
            )
        else:
            # Apple withheld the email (user opted for privacy) — create a
            # placeholder user identified only by their Apple sub.
            username = f"apple_{apple_uid}"
            user = User.objects.create_user(username=username, email="")

        SocialAccount.objects.get_or_create(
            provider="apple",
            uid=apple_uid,
            defaults={"user": user, "extra_data": payload},
        )
        return user


# ─── Magic Link (passwordless email login) ────────────────────────────────────

class MagicLinkService:
    """
    Passwordless login via a single-use token sent by email.

    Tokens are stored in Redis (Django cache) with a 15-minute TTL and
    deleted immediately on first use, making them truly single-use.
    """

    TTL_SECONDS = 15 * 60  # 15 minutes
    CACHE_PREFIX = "magic_link:"

    @staticmethod
    def request_link(email: str) -> None:
        """
        Generate a magic-link token and email it to the user.
        Always returns silently when the address is not registered to avoid
        leaking account existence.
        """
        import secrets
        from django.core.cache import cache
        from django.core.mail import send_mail

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return  # Silently ignore

        token = secrets.token_urlsafe(32)
        cache.set(
            f"{MagicLinkService.CACHE_PREFIX}{token}",
            user.pk,
            timeout=MagicLinkService.TTL_SECONDS,
        )

        send_mail(
            subject="FlowRoll — Your login link",
            message=(
                f"Hi {user.first_name or user.username},\n\n"
                "Use the following token to log in (valid for 15 minutes, single use):\n\n"
                f"  token: {token}\n\n"
                "If you did not request this, you can safely ignore this email."
            ),
            from_email=None,
            recipient_list=[user.email],
            fail_silently=True,
        )

    @staticmethod
    def verify_link(token: str) -> User:
        """
        Validate *token* and return the matching User.
        The token is deleted on first use (single-use guarantee).
        Raises ValueError if the token is invalid or expired.
        """
        from django.core.cache import cache

        cache_key = f"{MagicLinkService.CACHE_PREFIX}{token}"
        user_pk = cache.get(cache_key)

        if user_pk is None:
            raise ValueError("Invalid or expired magic link.")

        cache.delete(cache_key)  # Single-use: consume immediately

        try:
            return User.objects.get(pk=user_pk)
        except User.DoesNotExist:
            raise ValueError("User account no longer exists.")


# ─── Phone OTP ────────────────────────────────────────────────────────────────

class PhoneOTPService:
    """
    SMS one-time password authentication via Twilio.

    Flow:
    1. Client calls send_otp(phone) → 6-digit OTP stored in Redis + sent by SMS.
    2. Client calls verify_otp(phone, otp) → OTP validated, User returned.

    Security:
    - OTP is 6 cryptographically random digits.
    - Max 3 wrong attempts before the OTP is invalidated (force re-request).
    - 5-minute TTL on both OTP and attempt counter.
    - Phone numbers are normalised to E.164 before use.
    """

    OTP_TTL = 5 * 60       # 5 minutes
    OTP_PREFIX = "phone_otp:"
    ATTEMPTS_PREFIX = "phone_otp_attempts:"
    MAX_ATTEMPTS = 3

    @staticmethod
    def _normalise(phone: str) -> str:
        """Return *phone* in E.164 format or raise ValueError."""
        import phonenumbers

        try:
            parsed = phonenumbers.parse(phone, None)
        except phonenumbers.NumberParseException as exc:
            raise ValueError(f"Invalid phone number: {exc}") from exc

        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Phone number is not valid.")

        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    @staticmethod
    def send_otp(phone: str) -> None:
        """
        Generate a 6-digit OTP, store it in Redis, and send it via Twilio SMS.
        Raises ValueError for invalid phone numbers or Twilio errors.
        """
        import secrets
        from django.core.cache import cache
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException

        e164 = PhoneOTPService._normalise(phone)

        # Cryptographically random 6-digit code (100000–999999)
        otp = str(100000 + secrets.randbelow(900000))

        cache.set(f"{PhoneOTPService.OTP_PREFIX}{e164}", otp, timeout=PhoneOTPService.OTP_TTL)
        cache.set(f"{PhoneOTPService.ATTEMPTS_PREFIX}{e164}", 0, timeout=PhoneOTPService.OTP_TTL)

        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            client.messages.create(
                body=f"Your FlowRoll code is: {otp}. Valid for 5 minutes.",
                from_=settings.TWILIO_PHONE_NUMBER,
                to=e164,
            )
        except TwilioRestException as exc:
            raise ValueError(f"Failed to send SMS: {exc}") from exc

    @staticmethod
    @transaction.atomic
    def verify_otp(phone: str, otp: str) -> User:
        """
        Validate *otp* for *phone* and return (or create) the matching User.

        - Max-attempts guard: after 3 wrong attempts the code is invalidated.
        - Single-use: code deleted from Redis on successful verification.
        - New users are created with the phone number as their identifier.
        """
        from django.core.cache import cache
        from .models import UserPhoneNumber

        e164 = PhoneOTPService._normalise(phone)
        otp_key = f"{PhoneOTPService.OTP_PREFIX}{e164}"
        attempts_key = f"{PhoneOTPService.ATTEMPTS_PREFIX}{e164}"

        stored_otp = cache.get(otp_key)
        if stored_otp is None:
            raise ValueError("OTP has expired or was never requested. Please request a new code.")

        attempts = cache.get(attempts_key, 0)
        if attempts >= PhoneOTPService.MAX_ATTEMPTS:
            cache.delete(otp_key)
            cache.delete(attempts_key)
            raise ValueError("Too many incorrect attempts. Please request a new code.")

        if otp != stored_otp:
            cache.incr(attempts_key)
            raise ValueError("Incorrect OTP.")

        # Valid — consume the code
        cache.delete(otp_key)
        cache.delete(attempts_key)

        # Return existing user or create a new one for this phone number
        try:
            record = UserPhoneNumber.objects.select_related("user").get(phone=e164)
            if not record.is_verified:
                record.is_verified = True
                record.save(update_fields=["is_verified"])
            return record.user
        except UserPhoneNumber.DoesNotExist:
            username = f"phone_{e164.replace('+', '')}"
            user = User.objects.create_user(username=username, email="")
            UserPhoneNumber.objects.create(user=user, phone=e164, is_verified=True)
            return user
