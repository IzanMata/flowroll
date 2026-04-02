"""
Registration and social-auth services for the accounts app.

RegistrationService handles:
  - Email/password sign-up
  - Google ID token sign-up / sign-in

Both paths return a Django User instance; the caller is responsible for
issuing JWT tokens via SimpleJWT's RefreshToken.for_user().
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

        SocialAccount.objects.create(
            user=user,
            provider="google",
            uid=google_uid,
            extra_data=idinfo,
        )
        return user
