"""
Management command: setup_perf_data

Creates deterministic test accounts and data for performance / load testing.
Run once before starting the Locust test:

    python manage.py setup_perf_data

Credentials written to stdout so the locustfile can pick them up.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from academies.models import Academy
from athletes.models import AthleteProfile
from attendance.models import TrainingClass
from core.models import AcademyMembership, Belt
from tatami.models import TimerPreset, WeightClass


PERF_ACADEMY_NAME = "PerfTest Academy"
PERF_OWNER_USERNAME = "perf_owner"
PERF_PROF_USERNAME = "perf_professor"
PERF_STUDENT_USERNAME = "perf_student"
PERF_PASSWORD = "PerfTest123!"  # noqa: S105


class Command(BaseCommand):
    help = "Seed deterministic data for performance / load testing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete and re-create all perf test data.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            User.objects.filter(username__startswith="perf_").delete()
            Academy.objects.filter(name=PERF_ACADEMY_NAME).delete()
            self.stdout.write("  Deleted previous perf data.")

        # ── Academy ──────────────────────────────────────────────────────────
        academy, _ = Academy.objects.get_or_create(
            name=PERF_ACADEMY_NAME,
            defaults={
                "city": "Test City",
                "country": "ES",
                "email": "perf@example.com",
            },
        )

        # ── Users ─────────────────────────────────────────────────────────────
        owner = self._get_or_create_user(PERF_OWNER_USERNAME)
        professor = self._get_or_create_user(PERF_PROF_USERNAME)
        student = self._get_or_create_user(PERF_STUDENT_USERNAME)

        # ── Memberships ───────────────────────────────────────────────────────
        self._ensure_membership(owner, academy, AcademyMembership.Role.OWNER)
        self._ensure_membership(professor, academy, AcademyMembership.Role.PROFESSOR)
        self._ensure_membership(student, academy, AcademyMembership.Role.STUDENT)

        # ── AthleteProfiles ───────────────────────────────────────────────────
        white_belt = Belt.objects.filter(color="white").first()
        belt_color = white_belt.color if white_belt else "white"

        for user in (owner, professor, student):
            AthleteProfile.objects.get_or_create(
                user=user,
                defaults={"academy": academy, "belt": belt_color, "weight": 75.0},
            )

        # ── Training classes (10) ─────────────────────────────────────────────
        from django.utils import timezone

        for i in range(1, 11):
            TrainingClass.objects.get_or_create(
                title=f"Perf Class {i}",
                academy=academy,
                defaults={
                    "professor": professor,
                    "scheduled_at": timezone.now(),
                    "class_type": TrainingClass.ClassType.GI,
                },
            )

        # ── Timer preset ──────────────────────────────────────────────────────
        TimerPreset.objects.get_or_create(
            name="Perf Preset",
            academy=academy,
            defaults={
                "format": TimerPreset.Format.CUSTOM,
                "round_duration_seconds": 300,
                "rounds": 3,
            },
        )

        self.stdout.write(self.style.SUCCESS(
            f"\n✅  Perf data ready\n"
            f"   Academy ID : {academy.pk}\n"
            f"   Owner      : {PERF_OWNER_USERNAME} / {PERF_PASSWORD}\n"
            f"   Professor  : {PERF_PROF_USERNAME} / {PERF_PASSWORD}\n"
            f"   Student    : {PERF_STUDENT_USERNAME} / {PERF_PASSWORD}\n"
        ))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _get_or_create_user(self, username: str) -> User:
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@perf.test"},
        )
        if created or not user.check_password(PERF_PASSWORD):
            user.set_password(PERF_PASSWORD)
            user.save(update_fields=["password"])
        return user

    def _ensure_membership(self, user, academy, role) -> None:
        AcademyMembership.objects.update_or_create(
            user=user,
            academy=academy,
            defaults={"role": role, "is_active": True},
        )
