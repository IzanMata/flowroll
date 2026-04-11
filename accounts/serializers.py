from django.contrib.auth.models import User
from rest_framework import serializers


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})
    password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})
    first_name = serializers.CharField(max_length=150, required=False, default="")
    last_name = serializers.CharField(max_length=150, required=False, default="")

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with that email already exists.")
        return value.lower().strip()

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs


class GoogleAuthSerializer(serializers.Serializer):
    token = serializers.CharField(
        help_text="Google Sign-In ID token obtained on the client side."
    )


class EmailVerifySerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(
        write_only=True, min_length=8, style={"input_type": "password"}
    )
    new_password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True, min_length=8, style={"input_type": "password"}
    )
    new_password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        return attrs


class AppleAuthSerializer(serializers.Serializer):
    token = serializers.CharField(
        help_text="Sign in with Apple identity_token obtained on the client side."
    )


class MagicLinkRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class MagicLinkVerifySerializer(serializers.Serializer):
    token = serializers.CharField()


class PhoneOTPRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(
        help_text="Phone number in E.164 format or local format with country code, e.g. +34612345678"
    )


class PhoneOTPVerifySerializer(serializers.Serializer):
    phone = serializers.CharField()
    otp = serializers.CharField(min_length=6, max_length=6)


# ─── 2FA / TOTP ───────────────────────────────────────────────────────────────

class TwoFactorConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=6, help_text="6-digit TOTP code from your authenticator app")


class TwoFactorChallengeSerializer(serializers.Serializer):
    partial_token = serializers.CharField()
    code = serializers.CharField(min_length=6, max_length=16, help_text="TOTP code or recovery code (XXXXXX-XXXXXX)")


class TwoFactorDisableSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=16)


# ─── Session management ───────────────────────────────────────────────────────

class UserSessionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    device_name = serializers.CharField()
    ip_address = serializers.IPAddressField(allow_null=True)
    login_method = serializers.CharField()
    created_at = serializers.DateTimeField()
    last_seen_at = serializers.DateTimeField()
    is_current = serializers.BooleanField()


# ─── Account linking ──────────────────────────────────────────────────────────

class LinkGoogleSerializer(serializers.Serializer):
    token = serializers.CharField(help_text="Google ID token")


class LinkAppleSerializer(serializers.Serializer):
    token = serializers.CharField(help_text="Apple identity_token")


class LinkPhoneVerifySerializer(serializers.Serializer):
    phone = serializers.CharField()
    otp = serializers.CharField(min_length=6, max_length=6)


class UnlinkProviderSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=["google", "apple", "phone"])


# ─── Email change ─────────────────────────────────────────────────────────────

class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField()


class EmailChangeConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()


# ─── Profile completion ───────────────────────────────────────────────────────

class CompleteProfileSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
