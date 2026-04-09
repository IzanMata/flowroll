from django.urls import path

from .views import (
    # Existing
    AppleAuthView, ChangePasswordView, CompleteProfileView,
    ConnectionsView, EmailChangeConfirmView, EmailChangeRequestView,
    GoogleAuthView, LinkAppleView, LinkGoogleView, LinkPhoneVerifyView,
    LoginHistoryView, LogoutView, MagicLinkRequestView, MagicLinkVerifyView,
    PasswordResetConfirmView, PasswordResetRequestView, PhoneOTPRequestView,
    PhoneOTPVerifyView, RegisterView, ResendVerificationView,
    SessionDetailView, SessionListView, TwoFactorChallengeView,
    TwoFactorConfirmView, TwoFactorDisableView, TwoFactorRegenerateCodesView,
    TwoFactorSetupView, VerifyEmailView,
)

urlpatterns = [
    # ── Registration & password ───────────────────────────────────────────────
    path("register/", RegisterView.as_view(), name="auth_register"),
    path("logout/", LogoutView.as_view(), name="auth_logout"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="auth_password_reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="auth_password_reset_confirm"),
    path("change-password/", ChangePasswordView.as_view(), name="auth_change_password"),

    # ── Email verification ────────────────────────────────────────────────────
    path("verify-email/", VerifyEmailView.as_view(), name="auth_verify_email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="auth_resend_verification"),

    # ── Social auth ───────────────────────────────────────────────────────────
    path("social/google/", GoogleAuthView.as_view(), name="auth_google"),
    path("social/apple/", AppleAuthView.as_view(), name="auth_apple"),

    # ── Passwordless ──────────────────────────────────────────────────────────
    path("magic-link/", MagicLinkRequestView.as_view(), name="auth_magic_link_request"),
    path("magic-link/verify/", MagicLinkVerifyView.as_view(), name="auth_magic_link_verify"),

    # ── Phone OTP ─────────────────────────────────────────────────────────────
    path("phone/otp/", PhoneOTPRequestView.as_view(), name="auth_phone_otp_request"),
    path("phone/otp/verify/", PhoneOTPVerifyView.as_view(), name="auth_phone_otp_verify"),

    # ── Two-Factor Authentication ─────────────────────────────────────────────
    path("2fa/setup/", TwoFactorSetupView.as_view(), name="auth_2fa_setup"),
    path("2fa/confirm/", TwoFactorConfirmView.as_view(), name="auth_2fa_confirm"),
    path("2fa/challenge/", TwoFactorChallengeView.as_view(), name="auth_2fa_challenge"),
    path("2fa/disable/", TwoFactorDisableView.as_view(), name="auth_2fa_disable"),
    path("2fa/backup-codes/regenerate/", TwoFactorRegenerateCodesView.as_view(), name="auth_2fa_regen_codes"),

    # ── Sessions ──────────────────────────────────────────────────────────────
    path("sessions/", SessionListView.as_view(), name="auth_sessions"),
    path("sessions/<int:session_id>/", SessionDetailView.as_view(), name="auth_session_detail"),

    # ── Account connections ───────────────────────────────────────────────────
    path("connections/", ConnectionsView.as_view(), name="auth_connections"),
    path("connections/google/", LinkGoogleView.as_view(), name="auth_link_google"),
    path("connections/apple/", LinkAppleView.as_view(), name="auth_link_apple"),
    path("connections/phone/verify/", LinkPhoneVerifyView.as_view(), name="auth_link_phone_verify"),

    # ── Email change ──────────────────────────────────────────────────────────
    path("change-email/", EmailChangeRequestView.as_view(), name="auth_change_email"),
    path("change-email/confirm/", EmailChangeConfirmView.as_view(), name="auth_change_email_confirm"),

    # ── Profile & history ─────────────────────────────────────────────────────
    path("complete-profile/", CompleteProfileView.as_view(), name="auth_complete_profile"),
    path("login-history/", LoginHistoryView.as_view(), name="auth_login_history"),
]
