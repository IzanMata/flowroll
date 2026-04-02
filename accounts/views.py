from django.contrib.auth.models import User
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from config.throttles import LoginRateThrottle, PasswordResetRateThrottle

from .serializers import (ChangePasswordSerializer, EmailVerifySerializer,
                           GoogleAuthSerializer, PasswordResetConfirmSerializer,
                           PasswordResetRequestSerializer, RegisterSerializer,
                           ResendVerificationSerializer)
from .services import (EmailVerificationService, PasswordResetService,
                       RegistrationService)


def _tokens_for_user(user) -> dict:
    """Return a dict with access and refresh JWT tokens for the given user."""
    refresh = RefreshToken.for_user(user)
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
        return Response(status=204)


class VerifyEmailView(APIView):
    """
    Confirm email ownership using the uid+token received after registration.

    POST body: {"uid": "...", "token": "..."}
    """

    permission_classes = [AllowAny]

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
        return Response(_tokens_for_user(user), status=201)


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
        return Response(_tokens_for_user(user), status=200)
