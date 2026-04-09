import time

from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from config.throttles import (ChangePasswordRateThrottle,
                              EmailVerificationRateThrottle, LoginRateThrottle,
                              MagicLinkRateThrottle, PasswordResetRateThrottle,
                              PhoneOTPRateThrottle)

from .serializers import (AppleAuthSerializer, ChangePasswordSerializer,
                           CompleteProfileSerializer, EmailChangeConfirmSerializer,
                           EmailChangeRequestSerializer, EmailVerifySerializer,
                           GoogleAuthSerializer, LinkAppleSerializer,
                           LinkGoogleSerializer, LinkPhoneVerifySerializer,
                           MagicLinkRequestSerializer, MagicLinkVerifySerializer,
                           PasswordResetConfirmSerializer,
                           PasswordResetRequestSerializer, PhoneOTPRequestSerializer,
                           PhoneOTPVerifySerializer, RegisterSerializer,
                           ResendVerificationSerializer, TwoFactorChallengeSerializer,
                           TwoFactorConfirmSerializer, TwoFactorDisableSerializer,
                           UnlinkProviderSerializer, UserSessionSerializer)
from .services import (AccountLinkingService, AppleAuthService,
                       EmailChangeService, EmailVerificationService,
                       LoginEventService, MagicLinkService,
                       PasswordResetService, PhoneOTPService,
                       ProfileCompletionService, RegistrationService,
                       SessionService, TwoFactorService)


def _tokens_for_user(user, request=None, login_method: str = "email") -> dict:
    """
    Issue JWT token pair, create a UserSession, and log the login event.
    When *request* is None (e.g. tests), session creation and logging are skipped.
    """
    refresh = RefreshToken.for_user(user)

    if request is not None:
        session = SessionService.create(
            user=user, jti=str(refresh["jti"]), request=request, login_method=login_method
        )
        # Embed session PK in both tokens so /sessions/ can detect the current one
        refresh["session_id"] = session.pk
        refresh.access_token["session_id"] = session.pk
        LoginEventService.log(user=user, method=login_method, request=request, success=True)

    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


class LogoutView(APIView):
    """
    Invalidate a refresh token so it can no longer be used to obtain new
    access tokens.  The client should discard both tokens after calling this.

    POST body: {"refresh": "<refresh_token>"}
    Returns 204 on success.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "refresh token is required."}, status=400)
        try:
            RefreshToken(refresh_token).blacklist()
        except TokenError:
            return Response({"detail": "Invalid or already blacklisted token."}, status=400)

        # Revoke the access token via Redis JTI blocklist
        if request.auth:
            jti = request.auth.get("jti")
            exp = request.auth.get("exp")
            if jti and exp:
                remaining = int(exp) - int(time.time())
                if remaining > 0:
                    cache.set(f"revoked_jti:{jti}", "1", timeout=remaining)

        # Deactivate the session record (identified by the refresh token JTI)
        try:
            import jwt as pyjwt
            claims = pyjwt.decode(refresh_token, options={"verify_signature": False})
            refresh_jti = claims.get("jti")
            if refresh_jti:
                SessionService.deactivate(refresh_jti)
        except Exception:
            pass

        return Response(status=204)


class VerifyEmailView(APIView):
    """
    Confirm email ownership using the uid+token received after registration.

    POST body: {"uid": "...", "token": "..."}
    """

    permission_classes = [AllowAny]
    throttle_classes = [EmailVerificationRateThrottle]

    def post(self, request):
        serializer = EmailVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            EmailVerificationService.verify(
                uid=serializer.validated_data["uid"],
                token=serializer.validated_data["token"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"detail": "Email verified successfully."}, status=200)


class ResendVerificationView(APIView):
    """
    Resend the verification email. Returns 200 regardless of whether the
    address is registered to avoid leaking account existence.

    POST body: {"email": "..."}
    """

    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = User.objects.get(email__iexact=serializer.validated_data["email"])
            if not EmailVerificationService.is_verified(user):
                EmailVerificationService.send_verification(user)
        except User.DoesNotExist:
            pass
        return Response(
            {"detail": "If that email is registered and unverified, a new verification email has been sent."},
            status=200,
        )


class ChangePasswordView(APIView):
    """
    Change the authenticated user's password.

    Requires the current password for confirmation.
    POST body: {"old_password": "...", "new_password": "...", "new_password_confirm": "..."}
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ChangePasswordRateThrottle]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return Response({"old_password": "Incorrect password."}, status=400)
        try:
            from django.contrib.auth import password_validation
            from django.core.exceptions import ValidationError
            password_validation.validate_password(serializer.validated_data["new_password"], user)
        except ValidationError as exc:
            return Response({"new_password": list(exc.messages)}, status=400)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Password updated successfully."}, status=200)


class PasswordResetRequestView(APIView):
    """
    Request a password-reset email.

    Always returns 200 to avoid leaking whether the email address is registered.
    POST body: {"email": "user@example.com"}
    """

    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PasswordResetService.request_reset(serializer.validated_data["email"])
        return Response(
            {"detail": "If that email is registered you will receive a reset link shortly."},
            status=200,
        )


class PasswordResetConfirmView(APIView):
    """
    Set a new password using the uid+token received by email.

    POST body: {"uid": "...", "token": "...", "new_password": "...", "new_password_confirm": "..."}
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            PasswordResetService.confirm_reset(
                uid=data["uid"],
                token=data["token"],
                new_password=data["new_password"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"detail": "Password has been reset successfully."}, status=200)


class RegisterView(APIView):
    """
    Register a new account with email and password.

    Returns JWT access and refresh tokens on success.
    """

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = RegistrationService.register_with_email(
                email=data["email"],
                password=data["password"],
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_tokens_for_user(user, request, "email"), status=201)


class GoogleAuthView(APIView):
    """
    Sign in or register using a Google ID token.

    The client must obtain the ID token via Google Sign-In SDK and send it here.
    Returns JWT access and refresh tokens on success.
    """

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = RegistrationService.register_or_login_with_google(
                serializer.validated_data["token"]
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_tokens_for_user(user, request, "google"), status=200)


class AppleAuthView(APIView):
    """
    Sign in or register using a Sign in with Apple identity_token.

    The client must obtain the identity_token via the Apple Sign-In SDK and
    send it here.  Returns JWT access and refresh tokens on success.

    POST body: {"token": "<apple_identity_token>"}
    """

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = AppleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = AppleAuthService.register_or_login_with_apple(
                serializer.validated_data["token"]
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_tokens_for_user(user, request, "apple"), status=200)


class MagicLinkRequestView(APIView):
    """
    Request a magic-link login email.

    Always returns 200 regardless of whether the address is registered to
    avoid leaking account existence.

    POST body: {"email": "user@example.com"}
    """

    permission_classes = [AllowAny]
    throttle_classes = [MagicLinkRateThrottle]

    def post(self, request):
        serializer = MagicLinkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        MagicLinkService.request_link(serializer.validated_data["email"])
        return Response(
            {"detail": "If that email is registered you will receive a login link shortly."},
            status=200,
        )


class MagicLinkVerifyView(APIView):
    """
    Exchange a magic-link token for JWT access and refresh tokens.

    Tokens are single-use and expire after 15 minutes.

    POST body: {"token": "<magic_link_token>"}
    """

    permission_classes = [AllowAny]
    throttle_classes = [EmailVerificationRateThrottle]

    def post(self, request):
        serializer = MagicLinkVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = MagicLinkService.verify_link(serializer.validated_data["token"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_tokens_for_user(user, request, "magic_link"), status=200)


class PhoneOTPRequestView(APIView):
    """
    Request a 6-digit OTP via SMS to the given phone number.

    Always returns 200 to avoid leaking whether the number is registered.

    POST body: {"phone": "+34612345678"}
    """

    permission_classes = [AllowAny]
    throttle_classes = [PhoneOTPRateThrottle]

    def post(self, request):
        serializer = PhoneOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            PhoneOTPService.send_otp(serializer.validated_data["phone"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {"detail": "If that phone number is valid, an OTP has been sent."},
            status=200,
        )


class PhoneOTPVerifyView(APIView):
    """
    Verify the OTP received via SMS and obtain JWT tokens.

    POST body: {"phone": "+34612345678", "otp": "123456"}
    """

    permission_classes = [AllowAny]
    throttle_classes = [PhoneOTPRateThrottle]

    def post(self, request):
        serializer = PhoneOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = PhoneOTPService.verify_otp(data["phone"], data["otp"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_tokens_for_user(user, request, "phone"), status=200)


# ─── Two-Factor Authentication ────────────────────────────────────────────────


class TwoFactorSetupView(APIView):
    """
    Begin 2FA setup: generate a TOTP secret and provisioning URI for QR scanning.

    The device is not active until /2fa/confirm/ is called.
    GET (no body required).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = TwoFactorService.setup(request.user)
        return Response(data, status=200)


class TwoFactorConfirmView(APIView):
    """
    Activate 2FA by verifying the first TOTP code.
    Returns plaintext recovery codes (shown once — store them securely).

    POST body: {"code": "123456"}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TwoFactorConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            codes = TwoFactorService.confirm(request.user, serializer.validated_data["code"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"recovery_codes": codes}, status=200)


class TwoFactorChallengeView(APIView):
    """
    Complete login for a 2FA-enabled account.

    POST body: {"partial_token": "...", "code": "123456"}  (TOTP or recovery code)
    Returns JWT access + refresh tokens on success.
    """

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = TwoFactorChallengeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = TwoFactorService.challenge(data["partial_token"], data["code"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(_tokens_for_user(user, request, "totp"), status=200)


class TwoFactorDisableView(APIView):
    """
    Disable 2FA after verifying the current TOTP code or a recovery code.

    POST body: {"code": "123456"}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TwoFactorDisableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            TwoFactorService.disable(request.user, serializer.validated_data["code"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"detail": "Two-factor authentication has been disabled."}, status=200)


class TwoFactorRegenerateCodesView(APIView):
    """
    Regenerate recovery codes (old codes are invalidated).
    Requires current TOTP code for confirmation.

    POST body: {"code": "123456"}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TwoFactorConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            codes = TwoFactorService.regenerate_codes(request.user, serializer.validated_data["code"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"recovery_codes": codes}, status=200)


# ─── Session management ───────────────────────────────────────────────────────


class SessionListView(APIView):
    """
    List all active sessions for the authenticated user.

    GET — returns sessions with is_current=True on the calling session.
    DELETE — revoke all sessions except the current one.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import UserSession

        current_session_id = request.auth.get("session_id") if request.auth else None
        sessions = UserSession.objects.filter(user=request.user, is_active=True)
        data = UserSessionSerializer(
            [
                {
                    "id": s.pk,
                    "device_name": s.device_name,
                    "ip_address": s.ip_address,
                    "login_method": s.login_method,
                    "created_at": s.created_at,
                    "last_seen_at": s.last_seen_at,
                    "is_current": s.pk == current_session_id,
                }
                for s in sessions
            ],
            many=True,
        )
        return Response(data.data)

    def delete(self, request):
        current_jti = str(request.auth["jti"]) if request.auth else None
        revoked = SessionService.revoke_all(request.user, except_jti=current_jti)
        return Response({"revoked": revoked}, status=200)


class SessionDetailView(APIView):
    """
    Revoke a specific session by ID.

    DELETE /api/auth/sessions/{id}/
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, session_id: int):
        current_jti = str(request.auth["jti"]) if request.auth else None
        try:
            SessionService.revoke(request.user, session_id, current_jti=current_jti)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(status=204)


# ─── Account connections ──────────────────────────────────────────────────────


class ConnectionsView(APIView):
    """
    GET  — list all linked auth providers.
    DELETE — unlink a provider: body {"provider": "google"|"apple"|"phone"}
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(AccountLinkingService.list_connections(request.user))

    def delete(self, request):
        serializer = UnlinkProviderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            AccountLinkingService.unlink(request.user, serializer.validated_data["provider"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"detail": "Provider unlinked successfully."}, status=200)


class LinkGoogleView(APIView):
    """Link a Google account to the authenticated user. POST body: {"token": "..."}"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LinkGoogleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            AccountLinkingService.link_google(request.user, serializer.validated_data["token"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"detail": "Google account linked successfully."}, status=200)


class LinkAppleView(APIView):
    """Link an Apple account to the authenticated user. POST body: {"token": "..."}"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LinkAppleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            AccountLinkingService.link_apple(request.user, serializer.validated_data["token"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"detail": "Apple account linked successfully."}, status=200)


class LinkPhoneVerifyView(APIView):
    """
    Verify the OTP and link the phone number.
    The OTP must have been requested first via POST /api/auth/phone/otp/.

    POST body: {"phone": "+34612345678", "otp": "123456"}
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [PhoneOTPRateThrottle]

    def post(self, request):
        serializer = LinkPhoneVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            AccountLinkingService.link_phone_verify(request.user, data["phone"], data["otp"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"detail": "Phone number linked successfully."}, status=200)


# ─── Email change ─────────────────────────────────────────────────────────────


class EmailChangeRequestView(APIView):
    """
    Request an email address change.
    Sends a confirmation token to the *new* address and a security notice to the old one.

    POST body: {"new_email": "new@example.com"}
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = EmailChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            EmailChangeService.request_change(request.user, serializer.validated_data["new_email"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {"detail": "A confirmation email has been sent to your new address."},
            status=200,
        )


class EmailChangeConfirmView(APIView):
    """
    Confirm the email change using the token from the confirmation email.

    POST body: {"token": "..."}
    """

    permission_classes = [AllowAny]
    throttle_classes = [EmailVerificationRateThrottle]

    def post(self, request):
        serializer = EmailChangeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            EmailChangeService.confirm_change(serializer.validated_data["token"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"detail": "Email address updated successfully."}, status=200)


# ─── Login history ────────────────────────────────────────────────────────────


class LoginHistoryView(APIView):
    """
    Return the last 50 authentication events for the authenticated user.

    GET /api/auth/login-history/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import LoginEvent

        events = LoginEvent.objects.filter(user=request.user).values(
            "id", "method", "ip_address", "user_agent", "success", "created_at"
        )[:50]
        return Response(list(events))


# ─── Profile completion ───────────────────────────────────────────────────────


class CompleteProfileView(APIView):
    """
    Allow users who signed up via a social provider with missing data to
    fill in their profile (email, first_name, last_name).

    PATCH /api/auth/complete-profile/
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request):
        serializer = CompleteProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = ProfileCompletionService.complete(
                request.user,
                email=data.get("email", ""),
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }, status=200)
