import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("athletes", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AthleteMatchStats",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("total_matches", models.PositiveIntegerField(default=0)),
                ("wins", models.PositiveIntegerField(default=0)),
                ("losses", models.PositiveIntegerField(default=0)),
                ("draws", models.PositiveIntegerField(default=0)),
                ("total_points_scored", models.PositiveIntegerField(default=0)),
                ("total_points_conceded", models.PositiveIntegerField(default=0)),
                ("submissions_won", models.PositiveIntegerField(default=0)),
                (
                    "athlete",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="match_stats",
                        to="athletes.athleteprofile",
                    ),
                ),
            ],
            options={
                "verbose_name": "Athlete Match Stats",
                "verbose_name_plural": "Athlete Match Stats",
            },
        ),
    ]
