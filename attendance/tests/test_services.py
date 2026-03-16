"""Tests for attendance services: QRCodeService, CheckInService, DropInService."""
import pytest
from datetime import timedelta

from django.utils import timezone

from attendance.models import CheckIn, DropInVisitor, QRCode
from attendance.services import CheckInService, DropInService, QRCodeService
from factories import AthleteProfileFactory, AcademyFactory, QRCodeFactory, TrainingClassFactory


class TestQRCodeServiceGenerate:
    def test_generates_qr_code_for_class(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        qr = QRCodeService.generate(tc)
        assert qr.pk is not None
        assert qr.training_class == tc
        assert qr.is_active is True

    def test_qr_is_valid_after_generation(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        qr = QRCodeService.generate(tc, expiry_minutes=30)
        assert qr.is_valid is True

    def test_expiry_respects_parameter(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        before = timezone.now()
        qr = QRCodeService.generate(tc, expiry_minutes=60)
        after = timezone.now()
        # expires_at should be ~60 minutes from now (±2 seconds tolerance)
        expected_min = before + timedelta(minutes=60) - timedelta(seconds=2)
        expected_max = after + timedelta(minutes=60) + timedelta(seconds=2)
        assert expected_min <= qr.expires_at <= expected_max

    def test_refreshing_existing_qr_regenerates_token(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        qr1 = QRCodeService.generate(tc)
        original_token = qr1.token
        qr2 = QRCodeService.generate(tc)
        assert qr2.pk == qr1.pk  # same record updated
        qr2.refresh_from_db()
        assert qr2.token != original_token

    def test_only_one_qr_per_training_class(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        QRCodeService.generate(tc)
        QRCodeService.generate(tc)
        assert QRCode.objects.filter(training_class=tc).count() == 1


class TestQRCodeServiceValidate:
    def test_valid_token_returns_qr(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        qr = QRCodeService.generate(tc, expiry_minutes=30)
        result = QRCodeService.validate(qr.token)
        assert result == qr

    def test_invalid_token_raises_value_error(self, db):
        with pytest.raises(ValueError, match="Invalid or inactive"):
            QRCodeService.validate("totally-invalid-token")

    def test_expired_token_raises_value_error(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        qr = QRCodeFactory(
            training_class=tc,
            is_active=True,
            expires_at=timezone.now() - timedelta(minutes=5),
        )
        with pytest.raises(ValueError, match="expired"):
            QRCodeService.validate(qr.token)

    def test_inactive_token_raises_value_error(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        qr = QRCodeFactory(
            training_class=tc,
            is_active=False,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        with pytest.raises(ValueError, match="Invalid or inactive"):
            QRCodeService.validate(qr.token)


class TestQRCodeServiceDeactivate:
    def test_deactivates_qr_for_class(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        QRCodeService.generate(tc)
        QRCodeService.deactivate(tc)
        assert not QRCode.objects.filter(training_class=tc, is_active=True).exists()


class TestCheckInServiceQR:
    def test_check_in_via_qr_creates_record(self, db, academy):
        tc = TrainingClassFactory(academy=academy, duration_minutes=60)
        athlete = AthleteProfileFactory(academy=academy)
        qr = QRCodeService.generate(tc)
        check_in = CheckInService.check_in_via_qr(athlete, qr.token)
        assert check_in.pk is not None
        assert check_in.method == CheckIn.Method.QR
        assert check_in.athlete == athlete

    def test_check_in_increments_mat_hours(self, db, academy):
        tc = TrainingClassFactory(academy=academy, duration_minutes=90)
        athlete = AthleteProfileFactory(academy=academy, mat_hours=0.0)
        qr = QRCodeService.generate(tc)
        CheckInService.check_in_via_qr(athlete, qr.token)
        athlete.refresh_from_db()
        assert abs(athlete.mat_hours - 1.5) < 0.001

    def test_check_in_60_min_adds_one_hour(self, db, academy):
        tc = TrainingClassFactory(academy=academy, duration_minutes=60)
        athlete = AthleteProfileFactory(academy=academy, mat_hours=10.0)
        qr = QRCodeService.generate(tc)
        CheckInService.check_in_via_qr(athlete, qr.token)
        athlete.refresh_from_db()
        assert abs(athlete.mat_hours - 11.0) < 0.001

    def test_duplicate_checkin_raises_value_error(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        athlete = AthleteProfileFactory(academy=academy)
        qr = QRCodeService.generate(tc)
        CheckInService.check_in_via_qr(athlete, qr.token)
        # Must re-generate a fresh valid QR to attempt second check-in
        qr2 = QRCodeService.generate(tc)
        with pytest.raises(ValueError, match="already checked in"):
            CheckInService.check_in_via_qr(athlete, qr2.token)

    def test_invalid_token_propagates_error(self, db, academy):
        athlete = AthleteProfileFactory(academy=academy)
        with pytest.raises(ValueError):
            CheckInService.check_in_via_qr(athlete, "bad-token")


class TestCheckInServiceManual:
    def test_manual_check_in_creates_record(self, db, academy):
        tc = TrainingClassFactory(academy=academy, duration_minutes=60)
        athlete = AthleteProfileFactory(academy=academy)
        check_in = CheckInService.check_in_manual(athlete, tc)
        assert check_in.method == CheckIn.Method.MANUAL

    def test_manual_check_in_increments_mat_hours(self, db, academy):
        tc = TrainingClassFactory(academy=academy, duration_minutes=120)
        athlete = AthleteProfileFactory(academy=academy, mat_hours=0.0)
        CheckInService.check_in_manual(athlete, tc)
        athlete.refresh_from_db()
        assert abs(athlete.mat_hours - 2.0) < 0.001

    def test_duplicate_manual_check_in_raises(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        athlete = AthleteProfileFactory(academy=academy)
        CheckInService.check_in_manual(athlete, tc)
        with pytest.raises(ValueError, match="already checked in"):
            CheckInService.check_in_manual(athlete, tc)

    def test_multiple_athletes_can_check_in_to_same_class(self, db, academy):
        tc = TrainingClassFactory(academy=academy, duration_minutes=60)
        a1 = AthleteProfileFactory(academy=academy)
        a2 = AthleteProfileFactory(academy=academy)
        CheckInService.check_in_manual(a1, tc)
        CheckInService.check_in_manual(a2, tc)
        assert CheckIn.objects.filter(training_class=tc).count() == 2


class TestDropInService:
    def test_register_creates_visitor(self, db, academy):
        visitor = DropInService.register(
            academy=academy,
            first_name="Carlos",
            last_name="Gracie",
            email="carlos@gracie.com",
        )
        assert visitor.pk is not None
        assert visitor.first_name == "Carlos"
        assert visitor.status == DropInVisitor.Status.ACTIVE

    def test_register_sets_active_status(self, db, academy):
        visitor = DropInService.register(
            academy=academy, first_name="A", last_name="B", email="a@b.com"
        )
        assert visitor.status == DropInVisitor.Status.ACTIVE

    def test_register_with_training_class(self, db, academy):
        tc = TrainingClassFactory(academy=academy)
        visitor = DropInService.register(
            academy=academy,
            first_name="A",
            last_name="B",
            email="a@b.com",
            training_class=tc,
        )
        assert visitor.training_class == tc

    def test_expire_stale_marks_expired(self, db, academy):
        from datetime import timedelta
        # Create one stale and one fresh visitor
        stale = DropInVisitor.objects.create(
            academy=academy,
            first_name="Old",
            last_name="Guy",
            email="old@test.com",
            expires_at=timezone.now() - timedelta(hours=1),
            status=DropInVisitor.Status.ACTIVE,
        )
        fresh = DropInService.register(
            academy=academy, first_name="New", last_name="Guy", email="new@test.com"
        )
        count = DropInService.expire_stale()
        assert count == 1
        stale.refresh_from_db()
        fresh.refresh_from_db()
        assert stale.status == DropInVisitor.Status.EXPIRED
        assert fresh.status == DropInVisitor.Status.ACTIVE

    def test_expire_stale_returns_zero_when_none(self, db, academy):
        count = DropInService.expire_stale()
        assert count == 0
