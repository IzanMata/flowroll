from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_add_auth_improvements"),
    ]

    operations = [
        migrations.AddField(
            model_name="totpdevice",
            name="last_otp_counter",
            field=models.BigIntegerField(
                blank=True,
                null=True,
                help_text="Last successfully used TOTP counter (floor(epoch/30)) — prevents code reuse within the 90-second validity window.",
            ),
        ),
    ]
