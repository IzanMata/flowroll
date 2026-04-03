from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("techniques", "0006_alter_technique_difficulty"),
    ]

    operations = [
        migrations.AddField(
            model_name="techniquevideo",
            name="duration_seconds",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text="Video duration in seconds.",
            ),
        ),
        migrations.AddField(
            model_name="techniquevideo",
            name="tags",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Comma-separated keywords for search (e.g. 'guard,sweep,gi').",
                max_length=500,
            ),
            preserve_default=False,
        ),
    ]
