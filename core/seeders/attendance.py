from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from attendance.models import TrainingClass, CheckIn, QRCode, DropInVisitor
from academies.models import Academy
from athletes.models import AthleteProfile
from core.models import AcademyMembership
from core.seeders.utils import BJJ_TRAINING_CLASS_TITLES, random_past_datetime, random_future_datetime
import random
import uuid

User = get_user_model()


def seed_training_classes():
    """Create 15 training classes per academy (45 total)."""

    if TrainingClass.objects.exists():
        print("  ⏭  Training Classes already seeded, skipping.")
        return

    with transaction.atomic():
        academies = list(Academy.objects.all())
        classes_to_create = []

        for academy in academies:
            # Get professors for this academy
            professors = list(AcademyMembership.objects.filter(
                academy=academy,
                role__in=[AcademyMembership.Role.PROFESSOR, AcademyMembership.Role.OWNER],
                is_active=True
            ).select_related('user'))

            for i in range(15):
                # Mix of past and future classes
                if i < 10:  # 10 past classes
                    scheduled_at = random_past_datetime(30)
                else:  # 5 future classes
                    scheduled_at = random_future_datetime(14)

                # Get a professor from this academy or first user as fallback
                professor = random.choice(professors).user if professors else User.objects.first()

                training_class = TrainingClass(
                    academy=academy,
                    title=random.choice(BJJ_TRAINING_CLASS_TITLES),
                    class_type=random.choice([
                        TrainingClass.ClassType.GI,
                        TrainingClass.ClassType.NOGI,
                        TrainingClass.ClassType.OPEN_MAT,
                        TrainingClass.ClassType.KIDS,
                        TrainingClass.ClassType.COMPETITION
                    ]),
                    professor=professor,
                    scheduled_at=scheduled_at,
                    duration_minutes=random.choice([60, 90, 120]),
                    max_capacity=random.randint(15, 30),
                    notes=f"Training session at {academy.name}",
                )
                classes_to_create.append(training_class)

        TrainingClass.objects.bulk_create(classes_to_create, ignore_conflicts=True, batch_size=50)

    print(f"  ✅ Training Classes: {TrainingClass.objects.count()} records")


def seed_checkins():
    """Create 3-5 check-ins per past training class."""

    if CheckIn.objects.exists():
        print("  ⏭  Check-ins already seeded, skipping.")
        return

    with transaction.atomic():
        # Only past training classes should have check-ins
        past_classes = list(TrainingClass.objects.filter(scheduled_at__lt=timezone.now()))
        checkins_to_create = []

        for training_class in past_classes:
            # Get athlete profiles from this academy
            athlete_profiles = list(AthleteProfile.objects.filter(
                academy=training_class.academy,
                role=AthleteProfile.RoleChoices.STUDENT
            ))

            if athlete_profiles:
                # 3-5 students check in to each past class
                checkin_count = min(random.randint(3, 5), len(athlete_profiles))
                selected_athletes = random.sample(athlete_profiles, checkin_count)

                for athlete in selected_athletes:
                    checkin = CheckIn(
                        athlete=athlete,
                        training_class=training_class,
                        method=random.choice([CheckIn.Method.QR, CheckIn.Method.MANUAL]),
                    )
                    checkins_to_create.append(checkin)

        CheckIn.objects.bulk_create(checkins_to_create, ignore_conflicts=True, batch_size=100)

    print(f"  ✅ Check-ins: {CheckIn.objects.count()} records")


def seed_qr_codes():
    """Create QR codes for all training classes."""

    if QRCode.objects.exists():
        print("  ⏭  QR Codes already seeded, skipping.")
        return

    with transaction.atomic():
        training_classes = list(TrainingClass.objects.all())
        qr_codes_to_create = []

        for training_class in training_classes:
            # QR expires 2 hours after class starts
            expires_at = training_class.scheduled_at + timedelta(hours=2)
            is_active = expires_at > timezone.now()  # Active for future classes

            qr_code = QRCode(
                training_class=training_class,
                token=str(uuid.uuid4())[:32],  # 32-char token
                expires_at=expires_at,
                is_active=is_active,
            )
            qr_codes_to_create.append(qr_code)

        QRCode.objects.bulk_create(qr_codes_to_create, ignore_conflicts=True, batch_size=50)

    print(f"  ✅ QR Codes: {QRCode.objects.count()} records")


def seed_drop_in_visitors():
    """Create 2 drop-in visitors per academy."""

    if DropInVisitor.objects.exists():
        print("  ⏭  Drop-in Visitors already seeded, skipping.")
        return

    with transaction.atomic():
        academies = list(Academy.objects.all())
        visitors_to_create = []

        spanish_first_names = ['Miguel', 'Ana', 'Carlos', 'Maria', 'José', 'Carmen', 'Antonio', 'Isabel']
        spanish_last_names = ['García', 'Martínez', 'López', 'Sánchez', 'González', 'Rodríguez', 'Fernández', 'Pérez']

        for academy in academies:
            # Get some training classes from this academy for visitors
            academy_classes = list(TrainingClass.objects.filter(academy=academy)[:5])

            for i in range(2):  # 2 visitors per academy
                first_name = random.choice(spanish_first_names)
                last_name = random.choice(spanish_last_names)

                visitor = DropInVisitor(
                    academy=academy,
                    first_name=first_name,
                    last_name=last_name,
                    email=f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 99)}@gmail.com",
                    phone=f"+34 6{random.randint(10000000, 99999999)}",
                    training_class=random.choice(academy_classes) if academy_classes else None,
                    expires_at=timezone.now() + timedelta(days=random.randint(1, 14)),
                )
                visitors_to_create.append(visitor)

        DropInVisitor.objects.bulk_create(visitors_to_create, ignore_conflicts=True, batch_size=20)

    print(f"  ✅ Drop-in Visitors: {DropInVisitor.objects.count()} records")