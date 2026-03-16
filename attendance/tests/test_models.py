"""Tests for attendance models."""
import pytest
from django.db import IntegrityError
from django.utils import timezone
from datetime import timedelta

from attendance.models import CheckIn, DropInVisitor, QRCode, TrainingClass
from factories import (
    AthleteProfileFactory,
    AcademyFactory,
    CheckInFactory,
    DropInVisitorFactory,
    QRCodeFactory,
    TrainingClassFactory,
    UserFactory,
)


class TestTrainingClass:
    def test_create_training_class(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        assert tc.pk is not None
        assert tc.duration_minutes == 60

    def test_str_includes_title_and_date(self, db, academy):
        tc = TrainingClassFactory(academy=academy, title="Morning GI")
        assert "Morning GI" in str(tc)

    def test_default_class_type_is_gi(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        assert tc.class_type == TrainingClass.ClassType.GI

    def test_all_class_types_valid(self, db):
        expected = {"GI", "NOGI", "OPEN_MAT", "KIDS", "COMPETITION"}
        choices = {c for c, _ in TrainingClass.ClassType.choices}
        assert choices == expected

    def test_timestamps_auto_set(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        assert tc.created_at is not None
        assert tc.updated_at is not None

    def test_ordering_newest_first(self, db, academy):
        past = TrainingClassFactory(
            academy=academy,
            scheduled_at=timezone.now() - timedelta(hours=2),
        )
        future = TrainingClassFactory(
            academy=academy,
            scheduled_at=timezone.now() + timedelta(hours=2),
        )
        classes = list(TrainingClass.objects.filter(academy=academy))
        assert classes[0] == future  # newest first

    def test_max_capacity_nullable(self, db, academy):
        tc = TrainingClassFactory(academy=academy, max_capacity=None)
        assert tc.max_capacity is None


class TestQRCode:
    def test_token_auto_generated_on_save(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        qr = QRCodeFactory(training_class=tc)
        assert len(qr.token) > 0

    def test_token_is_unique(self, db, academy):
        tc1 = TrainingClassFactory(academy=academy)
        tc2 = TrainingClassFactory(academy=academy)
        qr1 = QRCodeFactory(training_class=tc1)
        qr2 = QRCodeFactory(training_class=tc2)
        assert qr1.token != qr2.token

    def test_is_valid_when_active_and_not_expired(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        qr = QRCodeFactory(
            training_class=tc,
            is_active=True,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        assert qr.is_valid is True

    def test_is_invalid_when_expired(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        qr = QRCodeFactory(
            training_class=tc,
            is_active=True,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        assert qr.is_valid is False

    def test_is_invalid_when_inactive(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        qr = QRCodeFactory(
            training_class=tc,
            is_active=False,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        assert qr.is_valid is False

    def test_one_to_one_with_training_class(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        qr = QRCodeFactory(training_class=tc)
        assert tc.qr_code == qr

    def test_str_shows_truncated_token(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        qr = QRCodeFactory(training_class=tc)
        assert "QR:" in str(qr)


class TestCheckIn:
    def test_create_check_in(self, db, academy):
        athlete = AthleteProfileFactory(academy=academy)
        tc = TrainingClassFactory(academy=academy)
        ci = CheckInFactory(athlete=athlete, training_class=tc)
        assert ci.pk is not None

    def test_unique_together_athlete_and_class(self, db, academy):
        athlete = AthleteProfileFactory(academy=academy)
        tc = TrainingClassFactory(academy=academy)
        CheckInFactory(athlete=athlete, training_class=tc)
        with pytest.raises(IntegrityError):
            CheckInFactory(athlete=athlete, training_class=tc)

    def test_different_athletes_same_class_allowed(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        a1 = AthleteProfileFactory(academy=academy)
        a2 = AthleteProfileFactory(academy=academy)
        CheckInFactory(athlete=a1, training_class=tc)
        CheckInFactory(athlete=a2, training_class=tc)
        assert CheckIn.objects.filter(training_class=tc).count() == 2

    def test_method_choices(self, db):
        expected = {"QR", "MANUAL"}
        choices = {c for c, _ in CheckIn.Method.choices}
        assert choices == expected

    def test_str_representation(self, db, academy):
        athlete = AthleteProfileFactory(academy=academy)
        tc = TrainingClassFactory(academy=academy)
        ci = CheckInFactory(athlete=athlete, training_class=tc)
        assert "@" in str(ci)


class TestDropInVisitor:
    def test_create_visitor(self, db, academy):
        visitor = DropInVisitorFactory(academy=academy)
        assert visitor.pk is not None
        assert visitor.access_token is not None

    def test_access_token_is_unique_uuid(self, db, academy):
        v1 = DropInVisitorFactory(academy=academy)
        v2 = DropInVisitorFactory(academy=academy)
        assert v1.access_token != v2.access_token

    def test_status_choices(self):
        choices = {c for c, _ in DropInVisitor.Status.choices}
        assert choices == {"PENDING", "ACTIVE", "EXPIRED"}

    def test_str_representation(self, db, academy):
        visitor = DropInVisitorFactory(
            academy=academy, first_name="John", last_name="Doe"
        )
        assert "John" in str(visitor)
        assert "Doe" in str(visitor)

    def test_training_class_nullable(self, db, academy):
        visitor = DropInVisitorFactory(academy=academy, training_class=None)
        assert visitor.training_class is None
