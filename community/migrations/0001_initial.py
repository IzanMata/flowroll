import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("academies", "0001_initial"),
        ("athletes", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Achievement",
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
                ("name", models.CharField(max_length=80, unique=True)),
                ("description", models.TextField()),
                ("icon_url", models.URLField(blank=True)),
                (
                    "trigger_type",
                    models.CharField(
                        choices=[
                            ("CHECKIN_COUNT", "Total check-ins"),
                            ("MAT_HOURS", "Cumulative mat hours"),
                            ("STREAK_DAYS", "Consecutive training days"),
                            ("MANUAL", "Manually awarded by professor"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "trigger_value",
                    models.FloatField(
                        blank=True,
                        help_text="Numeric threshold at which this achievement is automatically awarded.",
                        null=True,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="OpenMatSession",
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
                ("title", models.CharField(default="Open Mat", max_length=120)),
                ("event_date", models.DateField()),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField(blank=True, null=True)),
                ("max_capacity", models.PositiveIntegerField(blank=True, null=True)),
                ("description", models.TextField(blank=True)),
                ("is_cancelled", models.BooleanField(default=False)),
                (
                    "academy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="community_openmatsession_set",
                        to="academies.academy",
                    ),
                ),
            ],
            options={
                "ordering": ["-event_date"],
                "indexes": [
                    models.Index(
                        fields=["academy", "event_date"],
                        name="community_openmatsession_academy_event_date_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="OpenMatRSVP",
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
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("GOING", "Going"),
                            ("NOT_GOING", "Not Going"),
                            ("MAYBE", "Maybe"),
                        ],
                        default="GOING",
                        max_length=10,
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rsvps",
                        to="community.openmatsession",
                    ),
                ),
                (
                    "athlete",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="open_mat_rsvps",
                        to="athletes.athleteprofile",
                    ),
                ),
            ],
            options={
                "unique_together": {("session", "athlete")},
                "indexes": [
                    models.Index(
                        fields=["session", "status"],
                        name="openmatrsvp_session_status_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="AthleteAchievement",
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
                (
                    "athlete",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="achievements",
                        to="athletes.athleteprofile",
                    ),
                ),
                (
                    "achievement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="athlete_achievements",
                        to="community.achievement",
                    ),
                ),
                (
                    "awarded_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Professor who manually awarded this badge.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="achievements_awarded",
                        to="athletes.athleteprofile",
                    ),
                ),
            ],
            options={
                "unique_together": {("athlete", "achievement")},
            },
        ),
    ]
