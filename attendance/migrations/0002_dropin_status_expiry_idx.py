from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="dropinvisitor",
            index=models.Index(
                fields=["status", "expires_at"],
                name="dropin_status_expiry_idx",
            ),
        ),
    ]
