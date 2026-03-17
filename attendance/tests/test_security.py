"""
Security tests for attendance app.

Covers:
  H-5: mat_hours update is based on DB value, not stale Python snapshot
  H-6: manual_checkin cannot be used to check-in athletes from a foreign academy
  M-1: training class list requires academy membership
  M-2: drop-in visitor creation requires professor role
  M-7: QR expiry is clamped to safe range
"""

import pytest
from django.utils import timezone
from rest_framework import status

from attendance.models import CheckIn
from attendance.services import CheckInService
from factories import (AcademyFactory, AcademyMembershipFactory,
                       AthleteProfileFactory, TrainingClassFactory,
                       UserFactory)

# ─── H-5: mat_hours atomicity (F() expression) ───────────────────────────────


class TestMatHoursAtomicity:
    def test_mat_hours_uses_db_value_not_stale_snapshot(self, db, academy):
        """
        The mat_hours update must use F("mat_hours") + delta so that a
        concurrent check-in doesn't clobber a value written between fetch
        and save. We simulate a stale snapshot by manually bumping mat_hours
        after the athlete object is loaded but before check-in.
        """
        tc = TrainingClassFactory(academy=academy, duration_minutes=60)
        athlete = AthleteProfileFactory(academy=academy, mat_hours=10.0)

        # Simulate another process having incremented mat_hours to 15.0
        # before this check-in's F() update fires.
        from athletes.models import AthleteProfile

        AthleteProfile.objects.filter(pk=athlete.pk).update(mat_hours=15.0)

        qr = __import__("attendance.services", fromlist=["QRCodeService"]).QRCodeService
        qr_code = qr.generate(tc)
        CheckInService.check_in_via_qr(athlete, qr_code.token)

        athlete.refresh_from_db()
        # Should be 15 + 1 = 16, NOT the stale 10 + 1 = 11
        assert abs(athlete.mat_hours - 16.0) < 0.001, (
            f"Expected 16.0 (DB 15 + 1 hr), got {athlete.mat_hours}. "
            "This indicates a lost-update race condition."
        )


# ─── H-6: manual_checkin IDOR prevention ─────────────────────────────────────


class TestManualCheckinIDORPrevention:
    @pytest.fixture
    def setup(self, db):
        academy_a = AcademyFactory(name="Academy A")
        academy_b = AcademyFactory(name="Academy B")
        # Professor belongs to Academy A only
        prof_user = UserFactory(username="idor_professor")
        AcademyMembershipFactory(
            user=prof_user, academy=academy_a, role="PROFESSOR", is_active=True
        )
        # Athlete belongs to Academy B
        athlete_b = AthleteProfileFactory(academy=academy_b)
        # Training class in Academy A
        tc_a = TrainingClassFactory(academy=academy_a)
        return academy_a, academy_b, prof_user, athlete_b, tc_a

    def test_professor_cannot_checkin_foreign_athlete(self, api_client, setup):
        """A professor of Academy A cannot check in an athlete from Academy B."""
        academy_a, _, prof_user, athlete_b, tc_a = setup
        api_client.force_authenticate(user=prof_user)
        url = f"/api/attendance/classes/manual_checkin/?academy={academy_a.pk}"
        response = api_client.post(
            url,
            {
                "athlete_id": athlete_b.pk,
                "training_class_id": tc_a.pk,
            },
        )
        # athlete_b is in Academy B, not Academy A → 404 (scoped get_object_or_404)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert not CheckIn.objects.filter(
            athlete=athlete_b, training_class=tc_a
        ).exists()

    def test_professor_cannot_checkin_into_foreign_training_class(
        self, api_client, setup
    ):
        """A professor of Academy A cannot register attendance for a class from Academy B."""
        academy_a, academy_b, prof_user, _, _ = setup
        athlete_a = AthleteProfileFactory(academy=academy_a)
        tc_b = TrainingClassFactory(academy=academy_b)
        api_client.force_authenticate(user=prof_user)
        url = f"/api/attendance/classes/manual_checkin/?academy={academy_a.pk}"
        response = api_client.post(
            url,
            {
                "athlete_id": athlete_a.pk,
                "training_class_id": tc_b.pk,
            },
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert not CheckIn.objects.filter(
            athlete=athlete_a, training_class=tc_b
        ).exists()


# ─── M-1: training class list requires academy membership ────────────────────


class TestTrainingClassMembershipGuard:
    def test_non_member_cannot_see_classes(self, db, api_client, academy):
        TrainingClassFactory(academy=academy)
        outsider = UserFactory()
        api_client.force_authenticate(user=outsider)
        response = api_client.get(f"/api/attendance/classes/?academy={academy.pk}")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0  # silently empty, not leaking data

    def test_member_can_see_classes(self, db, api_client, academy):
        user = UserFactory()
        AcademyMembershipFactory(
            user=user, academy=academy, role="STUDENT", is_active=True
        )
        TrainingClassFactory(academy=academy)
        api_client.force_authenticate(user=user)
        response = api_client.get(f"/api/attendance/classes/?academy={academy.pk}")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1


# ─── M-2: drop-in visitor creation requires professor role ───────────────────


class TestDropInVisitorPermissions:
    def test_student_cannot_create_drop_in_visitor(self, db, api_client, academy):
        student = UserFactory()
        AcademyMembershipFactory(
            user=student, academy=academy, role="STUDENT", is_active=True
        )
        api_client.force_authenticate(user=student)
        response = api_client.post(
            "/api/attendance/drop-ins/",
            {
                "academy": academy.pk,
                "first_name": "Test",
                "last_name": "Visitor",
                "email": "tv@example.com",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_create_drop_in_visitor(
        self, db, api_client, academy, professor_membership  # noqa: F811
    ):
        from factories import AcademyMembershipFactory as AMF

        prof = UserFactory(username="dropin_prof")
        AMF(user=prof, academy=academy, role="PROFESSOR", is_active=True)
        api_client.force_authenticate(user=prof)
        response = api_client.post(
            "/api/attendance/drop-ins/",
            {
                "academy": academy.pk,
                "first_name": "Guest",
                "last_name": "Person",
                "email": "guest@example.com",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED


# ─── M-7: QR expiry clamping ─────────────────────────────────────────────────


class TestQRExpiryClamping:
    def test_absurdly_large_expiry_is_clamped(
        self, db, professor_client, academy, professor_membership
    ):
        tc = TrainingClassFactory(academy=academy)
        url = f"/api/attendance/classes/{tc.pk}/generate_qr/?academy={academy.pk}"
        response = professor_client.post(url, {"expiry_minutes": 99999999})
        assert response.status_code == status.HTTP_200_OK
        # expires_at should be ≤ 1440 minutes from now (24 hours max)
        import dateutil.parser

        expires_at = dateutil.parser.isoparse(response.data["expires_at"])
        delta = expires_at - timezone.now()
        assert delta.total_seconds() <= 1440 * 60 + 5  # +5s tolerance

    def test_zero_expiry_is_raised_to_minimum(
        self, db, professor_client, academy, professor_membership
    ):
        tc = TrainingClassFactory(academy=academy)
        url = f"/api/attendance/classes/{tc.pk}/generate_qr/?academy={academy.pk}"
        response = professor_client.post(url, {"expiry_minutes": 0})
        assert response.status_code == status.HTTP_200_OK
        # Should not be in the past
        import dateutil.parser

        expires_at = dateutil.parser.isoparse(response.data["expires_at"])
        assert expires_at > timezone.now()
