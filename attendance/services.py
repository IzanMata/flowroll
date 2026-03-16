from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from athletes.models import AthleteProfile

from .models import CheckIn, DropInVisitor, QRCode, TrainingClass


class QRCodeService:
    """Handles generation and validation of check-in QR codes."""

    DEFAULT_EXPIRY_MINUTES = 30

    @staticmethod
    def generate(training_class: TrainingClass, expiry_minutes: int = DEFAULT_EXPIRY_MINUTES) -> QRCode:
        """Create (or refresh) the QR code for a training class."""
        expires_at = timezone.now() + timedelta(minutes=expiry_minutes)
        qr, created = QRCode.objects.update_or_create(
            training_class=training_class,
            defaults={"expires_at": expires_at, "is_active": True},
        )
        # Force token regeneration on refresh
        if not created:
            import secrets
            qr.token = secrets.token_urlsafe(48)
            qr.expires_at = expires_at
            qr.save(update_fields=["token", "expires_at", "is_active"])
        return qr

    @staticmethod
    def validate(token: str) -> QRCode:
        """
        Return the QRCode if the token is valid.
        Raises ValueError if expired or not found.
        """
        try:
            qr = QRCode.objects.select_related("training_class").get(token=token, is_active=True)
        except QRCode.DoesNotExist:
            raise ValueError("Invalid or inactive QR code token.")
        if not qr.is_valid:
            raise ValueError("QR code has expired.")
        return qr

    @staticmethod
    def deactivate(training_class: TrainingClass) -> None:
        QRCode.objects.filter(training_class=training_class).update(is_active=False)


class CheckInService:
    """Handles athlete check-in and mat-hours accounting."""

    @staticmethod
    @transaction.atomic
    def check_in_via_qr(athlete: AthleteProfile, token: str) -> CheckIn:
        """Validate QR token and register the athlete's check-in."""
        qr = QRCodeService.validate(token)
        return CheckInService._create_check_in(athlete, qr.training_class, CheckIn.Method.QR)

    @staticmethod
    @transaction.atomic
    def check_in_manual(athlete: AthleteProfile, training_class: TrainingClass) -> CheckIn:
        """Professor-triggered manual check-in."""
        return CheckInService._create_check_in(athlete, training_class, CheckIn.Method.MANUAL)

    @staticmethod
    def _create_check_in(
        athlete: AthleteProfile,
        training_class: TrainingClass,
        method: str,
    ) -> CheckIn:
        check_in, created = CheckIn.objects.get_or_create(
            athlete=athlete,
            training_class=training_class,
            defaults={"method": method},
        )
        if not created:
            raise ValueError("Athlete has already checked in to this class.")

        # H-5 fix: use F() expression to avoid lost-update race condition.
        # The stale Python value `athlete.mat_hours` must NOT be used here.
        mat_hours_delta = training_class.duration_minutes / 60.0
        AthleteProfile.objects.filter(pk=athlete.pk).update(
            mat_hours=F("mat_hours") + mat_hours_delta
        )
        return check_in


class DropInService:
    """Manages drop-in visitor onboarding and token lifecycle."""

    DEFAULT_EXPIRY_HOURS = 24

    @staticmethod
    @transaction.atomic
    def register(
        academy,
        first_name: str,
        last_name: str,
        email: str,
        training_class: TrainingClass = None,
        phone: str = "",
        expiry_hours: int = DEFAULT_EXPIRY_HOURS,
    ) -> DropInVisitor:
        expires_at = timezone.now() + timedelta(hours=expiry_hours)
        visitor = DropInVisitor.objects.create(
            academy=academy,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            training_class=training_class,
            expires_at=expires_at,
            status=DropInVisitor.Status.ACTIVE,
        )
        return visitor

    @staticmethod
    def expire_stale() -> int:
        """Mark all past-expiry visitors as EXPIRED. Returns count updated."""
        return DropInVisitor.objects.filter(
            status=DropInVisitor.Status.ACTIVE,
            expires_at__lt=timezone.now(),
        ).update(status=DropInVisitor.Status.EXPIRED)
