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
            name="Tournament",
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
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("date", models.DateField()),
                ("location", models.CharField(blank=True, max_length=300)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("OPEN", "Open for Registration"),
                            ("IN_PROGRESS", "In Progress"),
                            ("COMPLETED", "Completed"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                (
                    "format",
                    models.CharField(
                        choices=[
                            ("BRACKET", "Single-Elimination Bracket"),
                            ("ROUND_ROBIN", "Round Robin"),
                        ],
                        default="BRACKET",
                        max_length=20,
                    ),
                ),
                (
                    "max_participants",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        help_text="Leave blank for unlimited participants.",
                    ),
                ),
                (
                    "academy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="competitions_tournament_set",
                        to="academies.academy",
                    ),
                ),
            ],
            options={
                "ordering": ["-date"],
            },
        ),
        migrations.CreateModel(
            name="TournamentDivision",
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
                ("name", models.CharField(max_length=200)),
                (
                    "belt_min",
                    models.CharField(
                        help_text="Minimum belt required to enter this division.",
                        max_length=10,
                    ),
                ),
                (
                    "belt_max",
                    models.CharField(
                        help_text="Maximum belt allowed in this division.",
                        max_length=10,
                    ),
                ),
                (
                    "weight_min",
                    models.FloatField(
                        blank=True,
                        null=True,
                        help_text="Minimum weight in kg (inclusive).",
                    ),
                ),
                (
                    "weight_max",
                    models.FloatField(
                        blank=True,
                        null=True,
                        help_text="Maximum weight in kg (inclusive).",
                    ),
                ),
                (
                    "tournament",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="divisions",
                        to="competitions.tournament",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("tournament", "name")},
            },
        ),
        migrations.CreateModel(
            name="TournamentParticipant",
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
                            ("PENDING", "Pending"),
                            ("CONFIRMED", "Confirmed"),
                            ("WITHDRAWN", "Withdrawn"),
                            ("CHECKED_IN", "Checked In"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("belt_at_registration", models.CharField(blank=True, max_length=10)),
                ("weight_at_registration", models.FloatField(blank=True, null=True)),
                (
                    "seed",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        help_text="Seeding position assigned before bracket generation.",
                    ),
                ),
                (
                    "athlete",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tournament_entries",
                        to="athletes.athleteprofile",
                    ),
                ),
                (
                    "division",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participants",
                        to="competitions.tournamentdivision",
                    ),
                ),
                (
                    "tournament",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participants",
                        to="competitions.tournament",
                    ),
                ),
            ],
            options={
                "ordering": ["seed", "athlete__user__username"],
                "unique_together": {("tournament", "athlete")},
            },
        ),
        migrations.CreateModel(
            name="TournamentMatch",
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
                ("round_number", models.PositiveSmallIntegerField(default=1)),
                ("score_a", models.SmallIntegerField(default=0)),
                ("score_b", models.SmallIntegerField(default=0)),
                ("is_finished", models.BooleanField(default=False)),
                ("notes", models.CharField(blank=True, max_length=300)),
                (
                    "athlete_a",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tournament_matches_as_a",
                        to="athletes.athleteprofile",
                    ),
                ),
                (
                    "athlete_b",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tournament_matches_as_b",
                        to="athletes.athleteprofile",
                    ),
                ),
                (
                    "division",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="matches",
                        to="competitions.tournamentdivision",
                    ),
                ),
                (
                    "tournament",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="matches",
                        to="competitions.tournament",
                    ),
                ),
                (
                    "winner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tournament_match_wins",
                        to="athletes.athleteprofile",
                    ),
                ),
            ],
            options={
                "ordering": ["round_number", "id"],
            },
        ),
    ]
