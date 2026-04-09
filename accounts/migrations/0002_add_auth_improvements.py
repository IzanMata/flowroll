from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sessions", to=settings.AUTH_USER_MODEL)),
                ("jti", models.CharField(db_index=True, help_text="Refresh token JTI", max_length=36, unique=True)),
                ("session_id", models.IntegerField(blank=True, help_text="Echoed into JWT claims for is_current detection", null=True)),
                ("device_name", models.CharField(blank=True, max_length=200)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("login_method", models.CharField(choices=[("email", "Email / Password"), ("google", "Google"), ("apple", "Apple"), ("phone", "Phone OTP"), ("magic_link", "Magic Link")], default="email", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now_add=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
            ],
            options={"db_table": "accounts_user_session", "ordering": ["-last_seen_at"]},
        ),
        migrations.CreateModel(
            name="TOTPDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="totp_device", to=settings.AUTH_USER_MODEL)),
                ("secret", models.CharField(help_text="Base32 TOTP secret", max_length=64)),
                ("is_active", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "accounts_totp_device"},
        ),
        migrations.CreateModel(
            name="RecoveryCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recovery_codes", to="accounts.totpdevice")),
                ("code_hash", models.CharField(help_text="SHA-256 hex digest of the plaintext code", max_length=64)),
                ("is_used", models.BooleanField(db_index=True, default=False)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "accounts_recovery_code"},
        ),
        migrations.CreateModel(
            name="LoginEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="login_events", to=settings.AUTH_USER_MODEL)),
                ("method", models.CharField(choices=[("email", "Email / Password"), ("google", "Google"), ("apple", "Apple"), ("phone", "Phone OTP"), ("magic_link", "Magic Link"), ("totp", "2FA TOTP"), ("recovery_code", "Recovery Code")], max_length=20)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("success", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"db_table": "accounts_login_event", "ordering": ["-created_at"]},
        ),
    ]
