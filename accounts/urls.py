from django.urls import path

from .views import (ChangePasswordView, GoogleAuthView, LogoutView,
                    PasswordResetConfirmView, PasswordResetRequestView,
                    RegisterView, ResendVerificationView, VerifyEmailView)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth_register"),
    path("logout/", LogoutView.as_view(), name="auth_logout"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="auth_password_reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="auth_password_reset_confirm"),
    path("verify-email/", VerifyEmailView.as_view(), name="auth_verify_email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="auth_resend_verification"),
    path("change-password/", ChangePasswordView.as_view(), name="auth_change_password"),
    path("social/google/", GoogleAuthView.as_view(), name="auth_google"),
]
