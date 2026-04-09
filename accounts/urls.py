from django.urls import path

from .views import (AppleAuthView, ChangePasswordView, GoogleAuthView,
                    LogoutView, MagicLinkRequestView, MagicLinkVerifyView,
                    PasswordResetConfirmView, PasswordResetRequestView,
                    PhoneOTPRequestView, PhoneOTPVerifyView, RegisterView,
                    ResendVerificationView, VerifyEmailView)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth_register"),
    path("logout/", LogoutView.as_view(), name="auth_logout"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="auth_password_reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="auth_password_reset_confirm"),
    path("verify-email/", VerifyEmailView.as_view(), name="auth_verify_email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="auth_resend_verification"),
    path("change-password/", ChangePasswordView.as_view(), name="auth_change_password"),
    # Social auth
    path("social/google/", GoogleAuthView.as_view(), name="auth_google"),
    path("social/apple/", AppleAuthView.as_view(), name="auth_apple"),
    # Passwordless
    path("magic-link/", MagicLinkRequestView.as_view(), name="auth_magic_link_request"),
    path("magic-link/verify/", MagicLinkVerifyView.as_view(), name="auth_magic_link_verify"),
    # Phone OTP
    path("phone/otp/", PhoneOTPRequestView.as_view(), name="auth_phone_otp_request"),
    path("phone/otp/verify/", PhoneOTPVerifyView.as_view(), name="auth_phone_otp_verify"),
]
