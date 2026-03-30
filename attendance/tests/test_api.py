"""API endpoint tests for attendance views."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from attendance.models import CheckIn, TrainingClass
from attendance.services import QRCodeService
from core.models import AcademyMembership
from factories import AcademyFactory, TrainingClassFactory


@pytest.fixture
def training_class(db, academy):
    return TrainingClassFactory(academy=academy, duration_minutes=60)


@pytest.fixture
def professor_membership(db, academy, professor_athlete):
    return AcademyMembership.objects.get_or_create(
        user=professor_athlete.user,
        academy=academy,
        defaults={"role": "PROFESSOR", "is_active": True},
    )[0]


# ─── TrainingClass list/detail ────────────────────────────────────────────────


class TestTrainingClassList:
    def test_requires_authentication(self, api_client, academy):
        url = f"/api/attendance/classes/?academy={academy.pk}"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_returns_classes_for_academy(self, auth_client, academy, training_class, athlete):
        from factories import AcademyMembershipFactory

        AcademyMembershipFactory(user=athlete.user, academy=academy, role="STUDENT", is_active=True)
        url = f"/api/attendance/classes/?academy={academy.pk}"
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1

    def test_returns_empty_without_academy_param(self, auth_client):
        url = "/api/attendance/classes/"
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_does_not_return_other_academy_classes(self, auth_client, academy):
        other_academy = AcademyFactory()
        TrainingClassFactory(academy=other_academy)
        url = f"/api/attendance/classes/?academy={academy.pk}"
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        # Only our academy's classes (zero in this case)
        for item in response.data["results"]:
            assert item["academy"] == academy.pk


# ─── generate_qr action ──────────────────────────────────────────────────────


class TestGenerateQR:
    def test_professor_can_generate_qr(
        self, db, professor_client, academy, training_class, professor_membership
    ):
        url = f"/api/attendance/classes/{training_class.pk}/generate_qr/?academy={academy.pk}"
        response = professor_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert "token" in response.data
        assert response.data["is_active"] is True

    def test_student_cannot_generate_qr(self, auth_client, academy, training_class):
        # auth_client is a regular student
        url = f"/api/attendance/classes/{training_class.pk}/generate_qr/?academy={academy.pk}"
        response = auth_client.post(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_generate_qr(
        self, api_client, academy, training_class
    ):
        url = f"/api/attendance/classes/{training_class.pk}/generate_qr/?academy={academy.pk}"
        response = api_client.post(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── qr_checkin action ───────────────────────────────────────────────────────


class TestQRCheckIn:
    def test_valid_token_creates_checkin(
        self, db, auth_client, academy, training_class, athlete
    ):
        qr = QRCodeService.generate(training_class)
        url = "/api/attendance/classes/qr_checkin/"
        response = auth_client.post(url, {"token": qr.token})
        assert response.status_code == status.HTTP_201_CREATED
        assert CheckIn.objects.filter(
            athlete=athlete, training_class=training_class
        ).exists()

    def test_invalid_token_returns_400(self, auth_client):
        url = "/api/attendance/classes/qr_checkin/"
        response = auth_client.post(url, {"token": "bad-token"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_duplicate_checkin_returns_400(
        self, db, auth_client, academy, training_class, athlete
    ):
        qr = QRCodeService.generate(training_class)
        url = "/api/attendance/classes/qr_checkin/"
        auth_client.post(url, {"token": qr.token})
        qr2 = QRCodeService.generate(training_class)
        response = auth_client.post(url, {"token": qr2.token})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_returns_401(self, api_client, academy, training_class):
        qr = QRCodeService.generate(training_class)
        url = "/api/attendance/classes/qr_checkin/"
        response = api_client.post(url, {"token": qr.token})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_mat_hours_updated_after_checkin(
        self, db, auth_client, academy, training_class, athlete
    ):
        from athletes.models import AthleteProfile

        AthleteProfile.objects.filter(pk=athlete.pk).update(mat_hours=0.0)
        athlete.refresh_from_db()
        TrainingClass.objects.filter(pk=training_class.pk).update(duration_minutes=90)
        training_class.refresh_from_db()
        qr = QRCodeService.generate(training_class)
        url = "/api/attendance/classes/qr_checkin/"
        auth_client.post(url, {"token": qr.token})
        athlete.refresh_from_db()
        assert abs(athlete.mat_hours - 1.5) < 0.001


# ─── manual_checkin action ────────────────────────────────────────────────────


class TestManualCheckIn:
    def test_professor_can_manually_check_in_athlete(
        self,
        db,
        professor_client,
        academy,
        training_class,
        professor_membership,
    ):
        from factories import AthleteProfileFactory

        athlete = AthleteProfileFactory(academy=academy)
        url = f"/api/attendance/classes/manual_checkin/?academy={academy.pk}"
        response = professor_client.post(
            url,
            {
                "athlete_id": athlete.pk,
                "training_class_id": training_class.pk,
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert CheckIn.objects.filter(
            athlete=athlete, training_class=training_class
        ).exists()

    def test_student_cannot_manually_check_in(
        self, auth_client, academy, training_class, athlete
    ):
        url = f"/api/attendance/classes/manual_checkin/?academy={academy.pk}"
        response = auth_client.post(
            url,
            {
                "athlete_id": athlete.pk,
                "training_class_id": training_class.pk,
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_nonexistent_athlete_returns_404(
        self, db, professor_client, academy, training_class, professor_membership
    ):
        url = f"/api/attendance/classes/manual_checkin/?academy={academy.pk}"
        response = professor_client.post(
            url,
            {
                "athlete_id": 99999,
                "training_class_id": training_class.pk,
            },
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ─── DropIn visitor ───────────────────────────────────────────────────────────


class TestDropInVisitorAPI:
    def test_create_drop_in_visitor(self, professor_client, academy, professor_membership):
        url = f"/api/attendance/drop-ins/?academy={academy.pk}"
        response = professor_client.post(
            url,
            {
                "academy": academy.pk,
                "first_name": "Guest",
                "last_name": "Visitor",
                "email": "guest@example.com",
                "expires_at": (timezone.now() + timedelta(hours=24)).isoformat(),
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["first_name"] == "Guest"

    def test_list_drop_ins_by_academy(self, auth_client, academy, athlete):
        from factories import AcademyMembershipFactory

        AcademyMembershipFactory(user=athlete.user, academy=academy, role="STUDENT", is_active=True)
        url = f"/api/attendance/drop-ins/?academy={academy.pk}"
        response = auth_client.get(url)
        assert response.status_code == status.HTTP_200_OK
