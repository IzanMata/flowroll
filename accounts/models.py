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
