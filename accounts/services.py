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
        Generate a 6-digit OTP, store its SHA-256 hash in Redis, and send the
        plaintext via Twilio SMS.  Storing a hash means a Redis breach does not
        expose usable codes.
        Raises ValueError for invalid phone numbers or Twilio errors.
        """
        import hashlib
        import secrets
        from django.core.cache import cache
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException

        e164 = PhoneOTPService._normalise(phone)

        # Cryptographically random 6-digit code (100000–999999)
        otp = str(100000 + secrets.randbelow(900000))
        otp_hash = hashlib.sha256(otp.encode()).hexdigest()

        cache.set(f"{PhoneOTPService.OTP_PREFIX}{e164}", otp_hash, timeout=PhoneOTPService.OTP_TTL)
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
        - Comparison is done against the stored SHA-256 hash (never plaintext).
        - New users are created with the phone number as their identifier.
        """
        import hashlib
        from django.core.cache import cache
        from .models import UserPhoneNumber

        e164 = PhoneOTPService._normalise(phone)
        otp_key = f"{PhoneOTPService.OTP_PREFIX}{e164}"
        attempts_key = f"{PhoneOTPService.ATTEMPTS_PREFIX}{e164}"

        stored_hash = cache.get(otp_key)
        if stored_hash is None:
            raise ValueError("OTP has expired or was never requested. Please request a new code.")

        attempts = cache.get(attempts_key, 0)
        if attempts >= PhoneOTPService.MAX_ATTEMPTS:
            cache.delete(otp_key)
            cache.delete(attempts_key)
            raise ValueError("Too many incorrect attempts. Please request a new code.")

        if hashlib.sha256(otp.encode()).hexdigest() != stored_hash:
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


# ─── Session management ───────────────────────────────────────────────────────

def _parse_device_name(user_agent: str) -> str:
    """Return a human-readable device string from a User-Agent header."""
    ua = user_agent.lower()
    if "iphone" in ua:
        device = "iPhone"
    elif "ipad" in ua:
        device = "iPad"
    elif "android" in ua:
        device = "Android"
    elif "macintosh" in ua or "mac os" in ua:
        device = "Mac"
    elif "windows" in ua:
        device = "Windows"
    elif "linux" in ua:
        device = "Linux"
    else:
        device = "Unknown device"

    if "chrome" in ua and "edg" not in ua and "opr" not in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "edg" in ua:
        browser = "Edge"
    else:
        browser = ""

    return f"{browser} on {device}".strip(" on") if browser else device


class SessionService:
    """Create and manage user sessions tied to refresh token JTIs."""

    @staticmethod
    def create(user: User, jti: str, request, login_method: str = "email"):
        """Create a new UserSession and return it."""
        from .models import UserSession

        ua = request.META.get("HTTP_USER_AGENT", "") if request else ""
        ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR")
        ) if request else None

        session = UserSession.objects.create(
            user=user,
            jti=jti,
            device_name=_parse_device_name(ua),
            ip_address=ip or None,
            login_method=login_method,
        )
        # Store own PK so we can emit it in JWT claims
        session.session_id = session.pk
        session.save(update_fields=["session_id"])
        return session

    @staticmethod
    def rotate_jti(old_jti: str, new_jti: str) -> None:
        """Update a session's JTI after token rotation and refresh last_seen_at."""
        from django.utils import timezone
        from .models import UserSession

        UserSession.objects.filter(jti=old_jti, is_active=True).update(
            jti=new_jti,
            last_seen_at=timezone.now(),
        )

    @staticmethod
    def deactivate(jti: str) -> None:
        """Deactivate the session associated with *jti* (called on logout)."""
        from .models import UserSession

        UserSession.objects.filter(jti=jti).update(is_active=False)

    @staticmethod
    def revoke(user: User, session_pk: int, current_jti: str | None = None) -> None:
        """
        Revoke a specific session: blacklist its refresh token and deactivate it.
        Raises ValueError if the session does not belong to the user.
        """
        from .models import UserSession

        try:
            session = UserSession.objects.get(pk=session_pk, user=user, is_active=True)
        except UserSession.DoesNotExist:
            raise ValueError("Session not found.")

        if current_jti and session.jti == current_jti:
            raise ValueError("Cannot revoke the current session via this endpoint. Use /logout/ instead.")

        SessionService._blacklist_jti(session.jti)
        session.is_active = False
        session.save(update_fields=["is_active"])

    @staticmethod
    def revoke_all(user: User, except_jti: str | None = None) -> int:
        """
        Blacklist and deactivate all sessions for *user* except the one with
        *except_jti* (typically the current session).  Returns the count revoked.
        """
        from .models import UserSession

        qs = UserSession.objects.filter(user=user, is_active=True)
        if except_jti:
            qs = qs.exclude(jti=except_jti)

        revoked = 0
        for session in qs:
            SessionService._blacklist_jti(session.jti)
            revoked += 1

        qs.update(is_active=False)
        return revoked

    @staticmethod
    def _blacklist_jti(jti: str) -> None:
        """Blacklist the OutstandingToken with this JTI if it exists."""
        try:
            from rest_framework_simplejwt.token_blacklist.models import (
                BlacklistedToken, OutstandingToken,
            )
            outstanding = OutstandingToken.objects.filter(jti=jti).first()
            if outstanding:
                BlacklistedToken.objects.get_or_create(token=outstanding)
        except Exception:
            pass  # token_blacklist app may not have the token yet


# ─── Login event logging ──────────────────────────────────────────────────────

class LoginEventService:
    """Log authentication events for the login history audit trail."""

    @staticmethod
    def log(user: User | None, method: str, request, success: bool = True) -> None:
        from .models import LoginEvent

        ua = request.META.get("HTTP_USER_AGENT", "") if request else ""
        ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR")
        ) if request else None

        LoginEvent.objects.create(
            user=user,
            method=method,
            ip_address=ip or None,
            user_agent=ua,
            success=success,
        )


# ─── Two-Factor Authentication (TOTP) ────────────────────────────────────────

RECOVERY_CODE_COUNT = 8  # codes generated per 2FA setup or regeneration


class TwoFactorService:
    """
    TOTP-based two-factor authentication using RFC 6238 (30-second window).

    Setup flow:
      1. setup(user)    → returns {secret, provisioning_uri, qr_url} — device inactive
      2. confirm(user, code) → activates device + returns plaintext recovery codes

    Login flow (when 2FA is active):
      1. Credentials validated → issue partial_token (Redis, 5 min TTL)
      2. challenge(partial_token, code) → validates TOTP or recovery code → returns user

    Management:
      - disable(user, code)
      - regenerate_codes(user, code) → new recovery codes (old ones invalidated)
    """

    PARTIAL_TOKEN_PREFIX = "2fa_partial:"
    PARTIAL_TOKEN_TTL = 5 * 60  # 5 minutes
    PARTIAL_ATTEMPTS_PREFIX = "2fa_attempts:"
    MAX_CHALLENGE_ATTEMPTS = 5  # max wrong codes before the partial_token is voided

    @staticmethod
    def setup(user: User) -> dict:
        """
        Initialise (or reset) 2FA for *user*.
        Returns secret + QR provisioning URI.  Device is NOT yet active.
        """
        import pyotp
        from .models import TOTPDevice

        secret = pyotp.random_base32()

        TOTPDevice.objects.filter(user=user).delete()  # reset any existing setup
        TOTPDevice.objects.create(user=user, secret=secret, is_active=False)

        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=user.email or user.username,
            issuer_name="FlowRoll",
        )

        return {
            "secret": secret,
            "provisioning_uri": provisioning_uri,
        }

    @staticmethod
    @transaction.atomic
    def confirm(user: User, code: str) -> list[str]:
        """
        Verify the first TOTP code, activate the device, and generate recovery codes.
        Returns plaintext recovery codes (shown once — never stored in plaintext).
        Raises ValueError if the code is invalid or no setup is in progress.
        """
        import pyotp
        from django.utils import timezone
        from .models import TOTPDevice, RecoveryCode

        try:
            device = TOTPDevice.objects.get(user=user, is_active=False)
        except TOTPDevice.DoesNotExist:
            raise ValueError("No pending 2FA setup found. Call /2fa/setup/ first.")

        try:
            valid = TwoFactorService._verify_totp_code(device, code)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if not valid:
            raise ValueError("Invalid TOTP code.")

        device.is_active = True
        device.confirmed_at = timezone.now()
        device.save(update_fields=["is_active", "confirmed_at"])

        return TwoFactorService._generate_recovery_codes(device)

    @staticmethod
    def issue_partial_token(user: User) -> str:
        """
        Issue a short-lived Redis token representing a partially-authenticated
        user (credentials validated, 2FA not yet verified).
        """
        import secrets
        from django.core.cache import cache

        token = secrets.token_urlsafe(32)
        cache.set(
            f"{TwoFactorService.PARTIAL_TOKEN_PREFIX}{token}",
            user.pk,
            timeout=TwoFactorService.PARTIAL_TOKEN_TTL,
        )
        return token

    @staticmethod
    def challenge(partial_token: str, code: str) -> User:
        """
        Validate a TOTP code (or recovery code) against *partial_token*.
        Returns the User on success; raises ValueError otherwise.
        """
        from django.core.cache import cache

        cache_key = f"{TwoFactorService.PARTIAL_TOKEN_PREFIX}{partial_token}"
        attempts_key = f"{TwoFactorService.PARTIAL_ATTEMPTS_PREFIX}{partial_token}"

        user_pk = cache.get(cache_key)
        if user_pk is None:
            raise ValueError("Partial token expired or invalid. Please log in again.")

        # Brute-force guard: distributed attackers can each hit the IP throttle
        # limit, so we also keep a per-token attempt counter in Redis.
        attempts = cache.get(attempts_key, 0)
        if attempts >= TwoFactorService.MAX_CHALLENGE_ATTEMPTS:
            cache.delete(cache_key)
            cache.delete(attempts_key)
            raise ValueError("Too many failed attempts. Please log in again.")

        try:
            user = User.objects.get(pk=user_pk)
        except User.DoesNotExist:
            raise ValueError("User not found.")

        device = getattr(user, "totp_device", None)
        if device is None or not device.is_active:
            raise ValueError("2FA is not active for this account.")

        # Try TOTP first, then recovery codes
        try:
            totp_valid = TwoFactorService._verify_totp_code(device, code)
        except ValueError as exc:
            # Code already used — clear the partial token to force re-login
            cache.delete(cache_key)
            cache.delete(attempts_key)
            raise ValueError(str(exc)) from exc

        if totp_valid:
            cache.delete(cache_key)
            cache.delete(attempts_key)
            return user

        if TwoFactorService._use_recovery_code(device, code):
            cache.delete(cache_key)
            cache.delete(attempts_key)
            return user

        # Wrong code — increment attempt counter (TTL matches partial token)
        cache.set(attempts_key, attempts + 1, timeout=TwoFactorService.PARTIAL_TOKEN_TTL)
        raise ValueError("Invalid code.")

    @staticmethod
    @transaction.atomic
    def disable(user: User, code: str) -> None:
        """Verify TOTP code and deactivate 2FA, deleting all codes."""
        import pyotp
        from .models import TOTPDevice

        device = getattr(user, "totp_device", None)
        if device is None or not device.is_active:
            raise ValueError("2FA is not active for this account.")

        try:
            totp_valid = TwoFactorService._verify_totp_code(device, code)
        except ValueError:
            totp_valid = False
        if not totp_valid:
            if not TwoFactorService._use_recovery_code(device, code):
                raise ValueError("Invalid code.")

        device.delete()

    @staticmethod
    @transaction.atomic
    def regenerate_codes(user: User, code: str) -> list[str]:
        """Verify TOTP code and generate a fresh set of recovery codes."""
        import pyotp
        from .models import RecoveryCode

        device = getattr(user, "totp_device", None)
        if device is None or not device.is_active:
            raise ValueError("2FA is not active for this account.")

        try:
            totp_valid = TwoFactorService._verify_totp_code(device, code)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if not totp_valid:
            raise ValueError("Invalid TOTP code.")

        RecoveryCode.objects.filter(device=device).delete()
        return TwoFactorService._generate_recovery_codes(device)

    @staticmethod
    def _verify_totp_code(device, code: str) -> bool:
        """
        Verify *code* against the device's TOTP secret with reuse prevention.

        Stores the counter value (floor(epoch/30)) of the last accepted code.
        Rejects any code whose counter is ≤ the stored value so the same OTP
        cannot be replayed within its 90-second validity window.

        Returns True on success, False on invalid code, raises ValueError on reuse.
        """
        import time
        import pyotp

        totp = pyotp.TOTP(device.secret)
        if not totp.verify(code, valid_window=1):
            return False

        # Determine which counter slot the accepted code belongs to
        now_counter = int(time.time()) // 30
        used_counter = now_counter  # default to current slot
        for offset in (-1, 0, 1):
            if totp.at(for_time=(now_counter + offset) * 30) == code:
                used_counter = now_counter + offset
                break

        # Reject if this counter was already consumed (reuse within validity window)
        if device.last_otp_counter is not None and device.last_otp_counter >= used_counter:
            raise ValueError("This code has already been used. Please wait for the next code.")

        device.last_otp_counter = used_counter
        device.save(update_fields=["last_otp_counter"])
        return True

    @staticmethod
    def _generate_recovery_codes(device) -> list[str]:
        import hashlib
        import secrets
        from .models import RecoveryCode

        plaintext_codes = [
            f"{secrets.token_hex(3).upper()}-{secrets.token_hex(3).upper()}"
            for _ in range(RECOVERY_CODE_COUNT)
        ]
        RecoveryCode.objects.bulk_create([
            RecoveryCode(
                device=device,
                code_hash=hashlib.sha256(code.encode()).hexdigest(),
            )
            for code in plaintext_codes
        ])
        return plaintext_codes

    @staticmethod
    def _use_recovery_code(device, code: str) -> bool:
        """Try to consume a recovery code. Returns True if valid and unused."""
        import hashlib
        from django.utils import timezone
        from .models import RecoveryCode

        code_hash = hashlib.sha256(code.upper().encode()).hexdigest()
        try:
            record = RecoveryCode.objects.select_for_update().get(
                device=device, code_hash=code_hash, is_used=False
            )
        except RecoveryCode.DoesNotExist:
            return False

        record.is_used = True
        record.used_at = timezone.now()
        record.save(update_fields=["is_used", "used_at"])
        return True


# ─── Account linking / unlinking ─────────────────────────────────────────────

class AccountLinkingService:
    """
    Link and unlink external auth providers (Google, Apple, Phone) to an
    existing user account.

    Rules:
    - A provider can only be linked once per account.
    - Unlinking is blocked if it would leave the user with no way to log in
      (no password, no other social account, no verified phone).
    """

    @staticmethod
    @transaction.atomic
    def link_google(user: User, google_id_token: str) -> None:
        """Link a Google account to *user*. Raises ValueError on failure."""
        from google.auth.exceptions import GoogleAuthError
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2.id_token import verify_oauth2_token
        from allauth.socialaccount.models import SocialAccount

        client_id = settings.GOOGLE_CLIENT_ID
        if not client_id:
            raise ValueError("Google OAuth is not configured.")

        try:
            idinfo = verify_oauth2_token(google_id_token, GoogleRequest(), client_id)
        except (GoogleAuthError, ValueError) as exc:
            raise ValueError(f"Invalid Google token: {exc}") from exc

        google_uid = idinfo["sub"]

        if SocialAccount.objects.filter(provider="google", uid=google_uid).exclude(user=user).exists():
            raise ValueError("This Google account is already linked to a different user.")

        SocialAccount.objects.get_or_create(
            provider="google",
            uid=google_uid,
            defaults={"user": user, "extra_data": idinfo},
        )

    @staticmethod
    @transaction.atomic
    def link_apple(user: User, identity_token: str) -> None:
        """Link an Apple account to *user*. Raises ValueError on failure."""
        from allauth.socialaccount.models import SocialAccount

        # Reuse AppleAuthService for token verification
        client_id = settings.APPLE_CLIENT_ID
        if not client_id:
            raise ValueError("Apple Sign-In is not configured.")

        import jwt as pyjwt

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

        if SocialAccount.objects.filter(provider="apple", uid=apple_uid).exclude(user=user).exists():
            raise ValueError("This Apple account is already linked to a different user.")

        SocialAccount.objects.get_or_create(
            provider="apple",
            uid=apple_uid,
            defaults={"user": user, "extra_data": payload},
        )

    @staticmethod
    @transaction.atomic
    def link_phone_verify(user: User, phone: str, otp: str) -> None:
        """
        Verify an OTP and link the phone number to *user*.
        The OTP must have been previously sent via PhoneOTPService.send_otp().
        Comparison is done against the stored SHA-256 hash (never plaintext).
        """
        import hashlib
        from django.core.cache import cache
        from .models import UserPhoneNumber

        e164 = PhoneOTPService._normalise(phone)
        otp_key = f"{PhoneOTPService.OTP_PREFIX}{e164}"
        attempts_key = f"{PhoneOTPService.ATTEMPTS_PREFIX}{e164}"

        stored_hash = cache.get(otp_key)
        if stored_hash is None:
            raise ValueError("OTP has expired. Please request a new one.")

        attempts = cache.get(attempts_key, 0)
        if attempts >= PhoneOTPService.MAX_ATTEMPTS:
            cache.delete(otp_key)
            cache.delete(attempts_key)
            raise ValueError("Too many incorrect attempts. Please request a new code.")

        if hashlib.sha256(otp.encode()).hexdigest() != stored_hash:
            cache.incr(attempts_key)
            raise ValueError("Incorrect OTP.")

        cache.delete(otp_key)
        cache.delete(attempts_key)

        if UserPhoneNumber.objects.filter(phone=e164).exclude(user=user).exists():
            raise ValueError("This phone number is already linked to a different account.")

        UserPhoneNumber.objects.update_or_create(
            user=user,
            defaults={"phone": e164, "is_verified": True},
        )

    @staticmethod
    @transaction.atomic
    def unlink(user: User, provider: str) -> None:
        """
        Unlink *provider* from *user*.  Raises ValueError if unlinking would
        leave the user with no authentication method.
        """
        from allauth.socialaccount.models import SocialAccount
        from .models import UserPhoneNumber

        valid_providers = {"google", "apple", "phone"}
        if provider not in valid_providers:
            raise ValueError(f"Unknown provider '{provider}'. Choose from: {', '.join(valid_providers)}.")

        # Check remaining methods after unlinking
        has_password = user.has_usable_password()
        social_count = SocialAccount.objects.filter(user=user).count()
        has_phone = UserPhoneNumber.objects.filter(user=user, is_verified=True).exists()

        if provider in {"google", "apple"}:
            remaining_socials = social_count - 1
        else:
            remaining_socials = social_count

        remaining_phone = not has_phone if provider == "phone" else has_phone

        if not has_password and remaining_socials == 0 and not remaining_phone:
            raise ValueError(
                "Cannot unlink: this is your only login method. "
                "Set a password or link another provider first."
            )

        if provider == "phone":
            UserPhoneNumber.objects.filter(user=user).delete()
        else:
            SocialAccount.objects.filter(user=user, provider=provider).delete()

    @staticmethod
    def list_connections(user: User) -> dict:
        """Return all connected auth methods for *user*."""
        from allauth.socialaccount.models import SocialAccount
        from .models import UserPhoneNumber

        socials = {
            s.provider: True
            for s in SocialAccount.objects.filter(user=user)
        }
        phone_record = UserPhoneNumber.objects.filter(user=user, is_verified=True).first()

        return {
            "has_password": user.has_usable_password(),
            "google": socials.get("google", False),
            "apple": socials.get("apple", False),
            "phone": phone_record.phone if phone_record else None,
            "two_factor_enabled": (
                hasattr(user, "totp_device") and user.totp_device.is_active
            ),
        }


# ─── Email change ─────────────────────────────────────────────────────────────

class EmailChangeService:
    """
    Allows users to change their email address with re-verification.

    The pending change is stored in Redis (not persisted to DB) until the
    user confirms it via the token sent to the new address.  On confirmation
    the old address receives a security notification.
    """

    PENDING_PREFIX = "email_change:"
    TTL_SECONDS = 24 * 60 * 60  # 24 hours

    @staticmethod
    def request_change(user: User, new_email: str) -> None:
        """
        Validate *new_email* and send a confirmation link.
        Raises ValueError if the email is already in use.
        """
        import secrets
        from django.core.cache import cache
        from django.core.mail import send_mail

        new_email = new_email.lower().strip()

        if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
            raise ValueError("That email address is already in use.")

        token = secrets.token_urlsafe(32)
        cache.set(
            f"{EmailChangeService.PENDING_PREFIX}{token}",
            {"user_pk": user.pk, "new_email": new_email},
            timeout=EmailChangeService.TTL_SECONDS,
        )

        send_mail(
            subject="FlowRoll — Confirm your new email address",
            message=(
                f"Hi {user.first_name or user.username},\n\n"
                f"You requested to change your email to: {new_email}\n\n"
                f"Confirm this change with the following token (valid 24 hours):\n\n"
                f"  token: {token}\n\n"
                "If you did not request this change, contact support immediately."
            ),
            from_email=None,
            recipient_list=[new_email],
            fail_silently=True,
        )

        # Security notification to old address
        if user.email:
            send_mail(
                subject="FlowRoll — Email change requested",
                message=(
                    f"Hi {user.first_name or user.username},\n\n"
                    f"A request to change your email to {new_email} was made.\n\n"
                    "If this was not you, contact support immediately."
                ),
                from_email=None,
                recipient_list=[user.email],
                fail_silently=True,
            )

    @staticmethod
    @transaction.atomic
    def confirm_change(token: str) -> User:
        """
        Validate *token* and apply the email change.
        Returns the updated User.  Raises ValueError on invalid/expired tokens.
        """
        from django.core.cache import cache
        from allauth.account.models import EmailAddress

        cache_key = f"{EmailChangeService.PENDING_PREFIX}{token}"
        data = cache.get(cache_key)
        if data is None:
            raise ValueError("Invalid or expired confirmation token.")

        cache.delete(cache_key)

        try:
            user = User.objects.get(pk=data["user_pk"])
        except User.DoesNotExist:
            raise ValueError("User account no longer exists.")

        new_email = data["new_email"]

        if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
            raise ValueError("That email address was taken while your confirmation was pending.")

        user.email = new_email
        user.username = new_email
        user.save(update_fields=["email", "username"])

        # Update allauth email record
        EmailAddress.objects.filter(user=user).update(primary=False)
        EmailAddress.objects.update_or_create(
            user=user,
            email=new_email,
            defaults={"primary": True, "verified": True},
        )

        return user


# ─── Profile completion (for social-login users) ──────────────────────────────

class ProfileCompletionService:
    """
    Allow users who registered via a social provider with missing data
    (e.g. Apple hid their email) to fill in their profile.
    """

    @staticmethod
    @transaction.atomic
    def complete(user: User, email: str = "", first_name: str = "", last_name: str = "") -> User:
        """
        Update *user*'s profile with the provided fields.
        - *email*: only accepted if the user has no email yet (avoids silent hijack).
        - *first_name* / *last_name*: always updatable.
        """
        from allauth.account.models import EmailAddress

        updates = []

        if first_name:
            user.first_name = first_name
            updates.append("first_name")

        if last_name:
            user.last_name = last_name
            updates.append("last_name")

        if email and not user.email:
            email = email.lower().strip()
            if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                raise ValueError("That email address is already in use.")
            user.email = email
            updates.append("email")
            EmailAddress.objects.get_or_create(
                user=user,
                email=email,
                defaults={"primary": True, "verified": False},
            )
            EmailVerificationService.send_verification(user)

        if updates:
            user.save(update_fields=updates)

        return user
