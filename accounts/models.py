from django.contrib.auth.models import User
from django.db import models


class UserPhoneNumber(models.Model):
    """
    Stores a verified phone number for a user, used by Phone OTP authentication.
    Each user can have at most one phone number; each phone number belongs to
    exactly one user.
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="phone_number"
    )
    phone = models.CharField(max_length=20, unique=True, help_text="E.164 format, e.g. +34612345678")
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_user_phone_number"

    def __str__(self):
        return f"{self.user.email or self.user.username} — {self.phone}"


class UserSession(models.Model):
    """
    Tracks active refresh-token sessions to support session management.

    A session is created on every successful login and is associated with
    the refresh token's JTI.  The JTI is updated on each token rotation so
    the record stays in sync with the live token.  On logout the record is
    deactivated rather than deleted so login history is preserved.
    """

    LOGIN_METHODS = [
        ("email", "Email / Password"),
        ("google", "Google"),
        ("apple", "Apple"),
        ("phone", "Phone OTP"),
        ("magic_link", "Magic Link"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    jti = models.CharField(max_length=36, unique=True, db_index=True, help_text="Refresh token JTI")
    session_id = models.IntegerField(null=True, blank=True, help_text="Echoed into JWT claims for is_current detection")
    device_name = models.CharField(max_length=200, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    login_method = models.CharField(max_length=20, choices=LOGIN_METHODS, default="email")
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "accounts_user_session"
        ordering = ["-last_seen_at"]

    def __str__(self):
        return f"{self.user.email} — {self.device_name or self.ip_address} ({self.login_method})"


class TOTPDevice(models.Model):
    """
    Stores the TOTP secret for a 2FA-enabled user.

    The device is created in an inactive state when setup begins.  It is
    activated only after the user verifies their first TOTP code (confirming
    they have correctly configured their authenticator app).
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="totp_device"
    )
    secret = models.CharField(max_length=64, help_text="Base32 TOTP secret")
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "accounts_totp_device"

    def __str__(self):
        status = "active" if self.is_active else "pending"
        return f"{self.user.email} — TOTP ({status})"


class RecoveryCode(models.Model):
    """
    Single-use backup codes for 2FA account recovery.

    Codes are stored as SHA-256 hex digests so the plaintext is never
    persisted — it is shown to the user once on generation.
    """

    device = models.ForeignKey(
        TOTPDevice, on_delete=models.CASCADE, related_name="recovery_codes"
    )
    code_hash = models.CharField(max_length=64, help_text="SHA-256 hex digest of the plaintext code")
    is_used = models.BooleanField(default=False, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_recovery_code"

    def __str__(self):
        state = "used" if self.is_used else "active"
        return f"RecoveryCode({state}) for {self.device.user.email}"


class LoginEvent(models.Model):
    """
    Audit log of authentication attempts (both successful and failed).

    ``user`` is nullable so failed attempts where no user can be identified
    (wrong email / unknown phone) are still recorded.
    """

    METHODS = [
        ("email", "Email / Password"),
        ("google", "Google"),
        ("apple", "Apple"),
        ("phone", "Phone OTP"),
        ("magic_link", "Magic Link"),
        ("totp", "2FA TOTP"),
        ("recovery_code", "Recovery Code"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_events",
    )
    method = models.CharField(max_length=20, choices=METHODS)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    success = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "accounts_login_event"
        ordering = ["-created_at"]

    def __str__(self):
        who = self.user.email if self.user else "unknown"
        result = "ok" if self.success else "fail"
        return f"{who} via {self.method} — {result}"
