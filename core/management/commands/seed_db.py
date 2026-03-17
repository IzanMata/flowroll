"""
Professional data seeding management command for FlowRoll.

Usage:
    python manage.py seed_db --env dev
    python manage.py seed_db --env staging --fresh
    python manage.py seed_db --count 200

Idempotent: running twice will not duplicate data.
Uses factory-boy for realistic relational data + existing fixtures for catalog data.
"""
import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from faker import Faker

from academies.models import Academy
from athletes.models import AthleteProfile
from attendance.models import TrainingClass, CheckIn, DropInVisitor
from community.models import Achievement, AthleteAchievement, OpenMatSession, OpenMatRSVP
from core.models import AcademyMembership, Belt
from learning.models import ClassTechniqueJournal, VideoLibraryItem, SparringNote
from matches.models import Match, MatchEvent
from membership.models import (
    MembershipPlan, Subscription, PromotionRequirement,
    DojoTabTransaction, DojoTabBalance, Seminar, SeminarRegistration
)
from tatami.models import WeightClass, TimerPreset, TimerSession, Matchup
from techniques.models import Technique, TechniqueCategory

from factories import *

fake = Faker()


class Command(BaseCommand):
    help = "Seed database with realistic BJJ academy data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--env",
            choices=["dev", "staging"],
            default="dev",
            help="Environment scaling (dev=small, staging=realistic volume)"
        )
        parser.add_argument(
            "--fresh",
            action="store_true",
            help="Wipe existing data before seeding (destructive)"
        )
        parser.add_argument(
            "--count",
            type=int,
            help="Override default record counts per model"
        )

    def handle(self, *args, **options):
        env = options["env"]
        fresh = options["fresh"]
        count_override = options.get("count")

        # Environment-based scaling
        if count_override:
            counts = self._get_scaled_counts(count_override)
        elif env == "dev":
            counts = self._get_scaled_counts(50)  # Dev: small for testing
        else:  # staging
            counts = self._get_scaled_counts(200)  # Staging: realistic volume

        self.stdout.write(f"\n🏟️  Seeding FlowRoll database ({env} environment)")
        if fresh:
            self.stdout.write(self.style.WARNING("⚠️  FRESH MODE: This will delete ALL existing data!"))
            if input("Continue? [y/N]: ").lower() != 'y':
                return

        try:
            with transaction.atomic():
                if fresh:
                    self._wipe_data()

                # Seed in dependency order
                self._seed_catalog_data()
                academies = self._seed_academies(counts["academies"])
                users = self._seed_users_and_memberships(academies, counts["users"])
                athletes = self._seed_athletes(academies, users, counts["athletes"])
                self._seed_techniques_and_learning(counts["techniques"], counts["videos"])
                classes = self._seed_attendance(academies, athletes, counts["classes"])
                self._seed_tatami_and_matches(academies, athletes, counts["matchups"])
                self._seed_membership_plans(academies, athletes, counts["plans"])
                self._seed_community(academies, athletes, counts["achievements"])

                self._print_summary()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Seeding failed: {e}"))
            raise

    def _get_scaled_counts(self, base):
        """Scale all counts proportionally from base number."""
        return {
            "academies": max(3, base // 25),       # 2 for dev, 8 for staging
            "users": base,                         # 50 for dev, 200 for staging
            "athletes": int(base * 0.8),          # 40 for dev, 160 for staging
            "classes": base * 2,                   # 100 for dev, 400 for staging
            "techniques": max(20, base // 5),      # 20 for dev, 40 for staging
            "videos": max(30, base // 3),          # 30 for dev, 66 for staging
            "matchups": base // 2,                 # 25 for dev, 100 for staging
            "plans": max(8, base // 10),           # 8 for dev, 20 for staging
            "achievements": 15,                    # Fixed: achievement types
        }

    def _wipe_data(self):
        """Destructively remove all seeded data in reverse dependency order."""
        self.stdout.write("🗑️  Wiping existing data...")

        # Clear in reverse dependency order
        models_to_clear = [
            SeminarRegistration, DojoTabTransaction, DojoTabBalance,
            AthleteAchievement, OpenMatRSVP, MatchEvent,
            CheckIn, ClassTechniqueJournal, SparringNote,
            VideoLibraryItem, TimerSession, Match, Matchup,
            Subscription, DropInVisitor, OpenMatSession, TrainingClass,
            Seminar, TimerPreset, MembershipPlan, PromotionRequirement,
            Achievement, AthleteProfile, AcademyMembership, Academy
        ]

        for model in models_to_clear:
            count = model.objects.count()
            if count > 0:
                model.objects.all().delete()
                self.stdout.write(f"   Deleted {count} {model.__name__} records")

        # Clear users (except superusers)
        user_count = User.objects.filter(is_superuser=False).count()
        if user_count > 0:
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write(f"   Deleted {user_count} non-superuser User records")

    def _seed_catalog_data(self):
        """Load static catalog data from fixtures."""
        self.stdout.write("📚 Loading catalog data (belts, techniques, categories)...")

        # Skip if data already exists
        if Belt.objects.exists() and Technique.objects.exists():
            self.stdout.write("   Catalog data already exists, skipping fixtures")
            return

        try:
            call_command("loaddata", "belts.json", verbosity=0)
            call_command("loaddata", "categories.json", verbosity=0)
            call_command("loaddata", "techniques.json", verbosity=0)
            call_command("loaddata", "flows.json", verbosity=0)
            call_command("loaddata", "variations.json", verbosity=0)

            belts = Belt.objects.count()
            techniques = Technique.objects.count()
            categories = TechniqueCategory.objects.count()

            self.stdout.write(f"   ✅ Loaded {belts} belts, {techniques} techniques, {categories} categories")

        except Exception as e:
            self.stdout.write(f"   ⚠️  Fixture loading failed ({e}), continuing with factory data")
            # Fallback: create minimal belt data
            if not Belt.objects.exists():
                for i, color in enumerate(["white", "blue", "purple", "brown", "black"], 1):
                    Belt.objects.get_or_create(color=color, defaults={"order": i})

    def _seed_academies(self, count):
        """Create academies with realistic variety."""
        self.stdout.write(f"🏛️  Creating {count} academies...")

        if Academy.objects.exists():
            academies = list(Academy.objects.all()[:count])
            self.stdout.write(f"   Using existing {len(academies)} academies")
            return academies

        academy_types = [
            "Brazilian Jiu-Jitsu", "Gracie Jiu-Jitsu", "BJJ Academy",
            "Mixed Martial Arts", "Combat Sports Academy", "Submission Grappling"
        ]

        academies = []
        for i in range(count):
            academy_type = fake.random_element(academy_types)
            city_name = fake.city()

            academy = AcademyFactory(
                name=f"{city_name} {academy_type}",
                city=city_name
            )
            academies.append(academy)

        self.stdout.write(f"   ✅ Created {len(academies)} academies")
        return academies

    def _seed_users_and_memberships(self, academies, count):
        """Create users and establish academy memberships with realistic distribution."""
        self.stdout.write(f"👥 Creating {count} users with academy memberships...")

        if User.objects.filter(is_superuser=False).exists():
            users = list(User.objects.filter(is_superuser=False)[:count])
            self.stdout.write(f"   Using existing {len(users)} users")
            return users

        users = []
        for i in range(count):
            first_name = fake.first_name()
            last_name = fake.last_name()
            username = f"{first_name.lower()}.{last_name.lower()}{i}"

            user = UserFactory(
                username=username,
                email=f"{username}@{fake.domain_name()}",
                first_name=first_name,
                last_name=last_name
            )
            users.append(user)

            # Each user belongs to 1-2 academies (85% single, 15% multiple)
            academy_count = 1 if random.random() < 0.85 else 2
            selected_academies = random.sample(academies, min(academy_count, len(academies)))

            for academy in selected_academies:
                # Role distribution: 80% student, 15% professor, 5% owner
                role_choice = random.choices(
                    ["STUDENT", "PROFESSOR", "OWNER"],
                    weights=[80, 15, 5]
                )[0]

                AcademyMembershipFactory(
                    user=user,
                    academy=academy,
                    role=role_choice
                )

        memberships = AcademyMembership.objects.count()
        self.stdout.write(f"   ✅ Created {len(users)} users with {memberships} academy memberships")
        return users

    def _seed_athletes(self, academies, users, count):
        """Create athlete profiles with realistic belt/stripe/weight distribution."""
        self.stdout.write(f"🥋 Creating {count} athlete profiles...")

        if AthleteProfile.objects.exists():
            athletes = list(AthleteProfile.objects.all()[:count])
            self.stdout.write(f"   Using existing {len(athletes)} athlete profiles")
            return athletes

        # Realistic belt distribution (typical academy demographics)
        belt_weights = {
            "white": 40,   # 40% white belts
            "blue": 30,    # 30% blue belts
            "purple": 20,  # 20% purple belts
            "brown": 8,    # 8% brown belts
            "black": 2     # 2% black belts
        }

        athletes = []
        for i in range(min(count, len(users))):
            user = users[i]
            membership = user.academy_memberships.first()

            if not membership:
                continue

            belt = random.choices(
                list(belt_weights.keys()),
                weights=list(belt_weights.values())
            )[0]

            # Stripes: weighted toward lower counts
            if belt != "black":  # Black belts use degrees, not stripes
                stripes = random.choices([0, 1, 2, 3, 4], weights=[30, 25, 20, 15, 10])[0]
            else:
                stripes = 0

            # Weight: realistic distribution by gender (inferred from name)
            is_likely_female = user.first_name in fake.first_name_female() if hasattr(fake, 'first_name_female') else random.random() < 0.3
            if is_likely_female:
                weight = round(random.normalvariate(62, 12), 1)  # ~62kg ± 12kg
                weight = max(45, min(85, weight))  # Clamp to realistic range
            else:
                weight = round(random.normalvariate(78, 15), 1)  # ~78kg ± 15kg
                weight = max(55, min(120, weight))

            # Mat hours: correlated with belt level
            base_hours = {"white": 50, "blue": 200, "purple": 500, "brown": 800, "black": 1200}[belt]
            mat_hours = round(random.normalvariate(base_hours, base_hours * 0.3), 1)
            mat_hours = max(0, mat_hours)

            athlete = AthleteProfileFactory(
                user=user,
                academy=membership.academy,
                belt=belt,
                stripes=stripes,
                weight=weight,
                mat_hours=mat_hours,
                role="PROFESSOR" if membership.role in ["PROFESSOR", "OWNER"] else "STUDENT"
            )
            athletes.append(athlete)

        self.stdout.write(f"   ✅ Created {len(athletes)} athlete profiles")
        return athletes

    def _seed_techniques_and_learning(self, technique_count, video_count):
        """Enhance techniques with learning materials."""
        self.stdout.write(f"📖 Creating learning materials ({video_count} videos)...")

        # Videos for existing techniques
        techniques = list(Technique.objects.all())
        if not techniques:
            self.stdout.write("   ⚠️  No techniques found, skipping learning materials")
            return

        video_sources = ["YOUTUBE", "VIMEO", "OTHER"]
        visibilities = ["PUBLIC", "PROFESSORS", "PRIVATE"]

        videos_created = 0
        for academy in Academy.objects.all():
            academy_video_count = video_count // Academy.objects.count()

            for _ in range(academy_video_count):
                technique = random.choice(techniques)

                VideoLibraryItemFactory(
                    academy=academy,
                    title=f"{technique.name} - {fake.catch_phrase()}",
                    url=f"https://youtube.com/watch?v={fake.lexify('??????????')}",
                    source=random.choice(video_sources),
                    visibility=random.choice(visibilities),
                    technique=technique,
                    belt_level=random.choice(["white", "blue", "purple", "brown", "black"]),
                    description=fake.paragraph()
                )
                videos_created += 1

        self.stdout.write(f"   ✅ Created {videos_created} video library items")

    def _seed_attendance(self, academies, athletes, class_count):
        """Create training classes with realistic attendance patterns."""
        self.stdout.write(f"📅 Creating {class_count} training classes with attendance...")

        classes = []
        checkins_created = 0
        journal_entries = 0
        sparring_notes = 0

        # Get professors for each academy
        academy_professors = {}
        for academy in academies:
            academy_professors[academy.id] = list(
                User.objects.filter(
                    academy_memberships__academy=academy,
                    academy_memberships__role__in=["PROFESSOR", "OWNER"]
                )[:5]  # Max 5 professors per academy
            )

        class_types = ["GI", "NOGI", "OPEN_MAT", "KIDS", "COMPETITION"]

        for academy in academies:
            academy_class_count = class_count // len(academies)
            academy_athletes = [a for a in athletes if a.academy_id == academy.id]
            professors = academy_professors.get(academy.id, [])

            if not academy_athletes or not professors:
                continue

            # Generate classes over the past 6 months
            start_date = timezone.now() - timedelta(days=180)

            for i in range(academy_class_count):
                # Realistic class scheduling: mostly weekday evenings + weekend afternoons
                class_date = fake.date_time_between(start_date=start_date, end_date='now')

                if class_date.weekday() < 5:  # Weekday
                    class_hour = random.choice([18, 19, 20])  # 6-8 PM
                else:  # Weekend
                    class_hour = random.choice([10, 14, 16])  # Morning or afternoon

                scheduled_at = class_date.replace(
                    hour=class_hour,
                    minute=random.choice([0, 30]),
                    second=0,
                    microsecond=0
                )

                training_class = TrainingClassFactory(
                    academy=academy,
                    title=f"{fake.word().title()} {random.choice(['Fundamentals', 'Advanced', 'Competition', 'Flow'])}",
                    class_type=random.choice(class_types),
                    professor=random.choice(professors),
                    scheduled_at=scheduled_at,
                    duration_minutes=random.choice([60, 75, 90]),
                    max_capacity=random.randint(15, 30)
                )
                classes.append(training_class)

                # Realistic attendance: 40-80% of academy athletes attend each class
                attendance_rate = random.uniform(0.4, 0.8)
                attending_athletes = random.sample(
                    academy_athletes,
                    int(len(academy_athletes) * attendance_rate)
                )

                techniques_drilled = list(Technique.objects.order_by('?')[:random.randint(2, 5)])

                for athlete in attending_athletes:
                    # Create check-in
                    CheckInFactory(
                        athlete=athlete,
                        training_class=training_class,
                        method=random.choice(["QR", "MANUAL"])
                    )
                    checkins_created += 1

                    # Update mat hours (simulate CheckInService)
                    duration_hours = training_class.duration_minutes / 60
                    athlete.mat_hours += duration_hours
                    athlete.save(update_fields=["mat_hours"])

                    # 30% chance to add sparring notes
                    if random.random() < 0.3:
                        opponent = random.choice(attending_athletes)
                        if opponent != athlete:
                            SparringNoteFactory(
                                athlete=athlete,
                                training_class=training_class,
                                opponent_name=f"{opponent.user.first_name} {opponent.user.last_name}",
                                session_date=training_class.scheduled_at.date(),
                                performance_rating=random.randint(1, 5),
                                notes=fake.paragraph()
                            )
                            sparring_notes += 1

                # Record techniques taught in class
                for technique in techniques_drilled:
                    ClassTechniqueJournal.objects.create(
                        training_class=training_class,
                        technique=technique,
                        professor_notes=fake.sentence() if random.random() < 0.4 else ""
                    )
                    journal_entries += 1

        self.stdout.write(f"   ✅ Created {len(classes)} classes, {checkins_created} check-ins, {journal_entries} technique logs, {sparring_notes} sparring notes")
        return classes

    def _seed_tatami_and_matches(self, academies, athletes, matchup_count):
        """Create tatami equipment and competition matches."""
        self.stdout.write(f"⚔️  Creating tatami sessions and {matchup_count} matches...")

        # Weight classes (global, shared across academies)
        if not WeightClass.objects.exists():
            weight_classes = [
                # Male divisions (IBJJF-inspired)
                ("Rooster", 57.5, 57.5, "M"), ("Light Feather", 64.0, 64.0, "M"),
                ("Feather", 70.0, 70.0, "M"), ("Light", 76.0, 76.0, "M"),
                ("Middle", 82.5, 82.5, "M"), ("Medium Heavy", 88.5, 88.5, "M"),
                ("Heavy", 94.5, 94.5, "M"), ("Super Heavy", 100.5, 120.0, "M"),
                # Female divisions
                ("Light Feather", 53.5, 53.5, "F"), ("Feather", 58.5, 58.5, "F"),
                ("Light", 64.0, 64.0, "F"), ("Middle", 69.0, 69.0, "F"),
                ("Medium Heavy", 74.0, 74.0, "F"), ("Heavy", 79.5, 100.0, "F"),
            ]

            for name, min_w, max_w, gender in weight_classes:
                WeightClass.objects.create(
                    name=name, min_weight=min_w, max_weight=max_w, gender=gender
                )

        weight_classes = list(WeightClass.objects.all())

        # Timer presets for each academy
        presets_created = 0
        for academy in academies:
            preset_configs = [
                ("IBJJF Adult", "IBJJF", 300, 0, 0, 1),   # 5min rounds
                ("IBJJF Juvenile", "IBJJF", 240, 0, 0, 1), # 4min rounds
                ("ADCC", "ADCC", 600, 0, 300, 1),          # 10min + 5min OT
                ("Positional Rounds", "POSITIONAL", 300, 60, 0, 3),  # 5min x3 with rest
                ("Quick Rounds", "CUSTOM", 180, 30, 0, 5),  # 3min x5 for drilling
            ]

            for name, format, round_dur, rest_dur, ot, rounds in preset_configs:
                TimerPresetFactory(
                    academy=academy,
                    name=name,
                    format=format,
                    round_duration_seconds=round_dur,
                    rest_duration_seconds=rest_dur,
                    overtime_seconds=ot,
                    rounds=rounds
                )
                presets_created += 1

        # Create matchups and matches
        matchups_created = 0
        matches_created = 0

        for academy in academies:
            academy_athletes = [a for a in athletes if a.academy_id == academy.id]
            academy_matchup_count = matchup_count // len(academies)

            for _ in range(academy_matchup_count):
                if len(academy_athletes) < 2:
                    continue

                # Pick two athletes with similar belt/weight for realistic matchmaking
                athlete_a = random.choice(academy_athletes)

                # Find suitable opponents (similar belt and weight)
                suitable_opponents = [
                    a for a in academy_athletes
                    if a != athlete_a
                    and abs(a.weight - athlete_a.weight) <= 10  # Within 10kg
                    and a.belt == athlete_a.belt  # Same belt level
                ]

                if not suitable_opponents:
                    suitable_opponents = [a for a in academy_athletes if a != athlete_a]

                if not suitable_opponents:
                    continue

                athlete_b = random.choice(suitable_opponents)

                # Find appropriate weight class
                avg_weight = (athlete_a.weight + athlete_b.weight) / 2
                suitable_weights = [
                    wc for wc in weight_classes
                    if wc.min_weight <= avg_weight <= wc.max_weight
                ]
                weight_class = random.choice(suitable_weights) if suitable_weights else None

                matchup = MatchupFactory(
                    academy=academy,
                    athlete_a=athlete_a,
                    athlete_b=athlete_b,
                    weight_class=weight_class,
                    match_format=random.choice(["TOURNAMENT", "SURVIVAL"]),
                    status=random.choice(["PENDING", "IN_PROGRESS", "COMPLETED"])
                )
                matchups_created += 1

                # 70% chance to create actual match records for completed matchups
                if matchup.status == "COMPLETED" and random.random() < 0.7:
                    match = Match.objects.create(
                        academy=academy,
                        athlete_a=athlete_a.user,
                        athlete_b=athlete_b.user,
                        date=fake.date_time_between(start_date='-30d', end_date='now'),
                        duration_seconds=random.randint(180, 600),
                        is_finished=True,
                        score_a=random.randint(0, 12),
                        score_b=random.randint(0, 12),
                        winner=random.choice([athlete_a.user, athlete_b.user, None])  # Can be draw
                    )

                    # Add some match events
                    event_count = random.randint(2, 8)
                    for i in range(event_count):
                        MatchEvent.objects.create(
                            match=match,
                            athlete=random.choice([athlete_a.user, athlete_b.user]),
                            timestamp=random.randint(10, match.duration_seconds - 10),
                            points_awarded=random.choice([2, 3, 4]),  # IBJJF points
                            action_description=random.choice([
                                "Takedown", "Guard pass", "Mount", "Back control",
                                "Knee on belly", "Sweep", "Reversal"
                            ]),
                            event_type="POINTS"
                        )
                    matches_created += 1

        self.stdout.write(f"   ✅ Created {presets_created} timer presets, {matchups_created} matchups, {matches_created} matches")

    def _seed_membership_plans(self, academies, athletes, plan_count):
        """Create membership plans and subscriptions."""
        self.stdout.write(f"💳 Creating membership plans and subscriptions...")

        plans_created = 0
        subscriptions_created = 0
        transactions_created = 0
        seminars_created = 0

        for academy in academies:
            # Standard plan types for each academy
            plan_configs = [
                ("Unlimited Monthly", "MONTHLY", 149.99, 30, None),
                ("Annual Membership", "ANNUAL", 1499.99, 365, None),
                ("10-Class Pass", "CLASS_PASS", 199.99, 90, 10),
                ("20-Class Pass", "CLASS_PASS", 379.99, 120, 20),
                ("Drop-In Rate", "DROP_IN", 25.00, None, 1),
                ("Student Monthly", "MONTHLY", 99.99, 30, None),
            ]

            academy_athletes = [a for a in athletes if a.academy_id == academy.id]

            for name, plan_type, price, duration, class_limit in plan_configs:
                plan = MembershipPlanFactory(
                    academy=academy,
                    name=name,
                    plan_type=plan_type,
                    price=Decimal(str(price)),
                    duration_days=duration,
                    class_limit=class_limit,
                    is_active=random.random() < 0.9  # 10% inactive legacy plans
                )
                plans_created += 1

                # Create subscriptions for 60-80% of academy athletes
                subscription_rate = random.uniform(0.6, 0.8)
                subscribing_athletes = random.sample(
                    academy_athletes,
                    int(len(academy_athletes) * subscription_rate)
                )

                for athlete in subscribing_athletes:
                    # Only create 1 subscription per athlete per academy
                    if not Subscription.objects.filter(athlete=athlete, plan__academy=academy).exists():
                        start_date = fake.date_between(start_date='-90d', end_date='today')
                        end_date = None
                        if duration:
                            end_date = start_date + timedelta(days=duration)

                        subscription = SubscriptionFactory(
                            athlete=athlete,
                            plan=plan,
                            start_date=start_date,
                            end_date=end_date,
                            status=random.choice(["ACTIVE", "EXPIRED", "CANCELLED"]),
                            classes_remaining=class_limit
                        )
                        subscriptions_created += 1

                        # Create some dojo tab transactions
                        if random.random() < 0.3:  # 30% have tab transactions
                            for _ in range(random.randint(1, 5)):
                                transaction_type = random.choice(["DEBIT", "CREDIT"])
                                amount = Decimal(str(random.uniform(5.0, 50.0)))

                                DojoTabTransactionFactory(
                                    academy=academy,
                                    athlete=athlete,
                                    transaction_type=transaction_type,
                                    amount=amount,
                                    description=random.choice([
                                        "Gear purchase", "Private lesson", "Seminar fee",
                                        "Payment received", "Refund", "Late fee"
                                    ])
                                )
                                transactions_created += 1

                        # Update dojo tab balance based on transactions
                        balance = DojoTabTransaction.objects.filter(
                            academy=academy, athlete=athlete
                        ).aggregate(
                            total=Sum('amount')
                        )['total'] or Decimal('0.00')

                        if balance != 0:
                            DojoTabBalance.objects.update_or_create(
                                academy=academy,
                                athlete=athlete,
                                defaults={'balance': balance}
                            )

            # Create seminars for the academy
            for _ in range(random.randint(2, 5)):
                event_date = fake.date_between(start_date='-30d', end_date='+60d')

                seminar = SeminarFactory(
                    academy=academy,
                    title=f"{fake.name()}: {random.choice(['Guard Retention', 'Leg Locks', 'Takedowns', 'Back Attacks', 'Escapes'])} Seminar",
                    instructor_name=fake.name(),
                    event_date=event_date,
                    capacity=random.randint(15, 40),
                    price=Decimal(str(random.uniform(75.0, 200.0))),
                    status=random.choice(["OPEN", "FULL", "COMPLETED"])
                )
                seminars_created += 1

                # Register some athletes for seminars
                registration_rate = random.uniform(0.2, 0.6)
                registering_athletes = random.sample(
                    academy_athletes,
                    min(int(len(academy_athletes) * registration_rate), seminar.capacity)
                )

                for athlete in registering_athletes:
                    SeminarRegistrationFactory(
                        seminar=seminar,
                        athlete=athlete,
                        status=random.choice(["CONFIRMED", "WAITLISTED"]),
                        payment_status=random.choice(["PENDING", "PAID"])
                    )

        # Create global promotion requirements
        if not PromotionRequirement.objects.exists():
            belt_requirements = [
                ("blue", 150.0, 12, 4),
                ("purple", 400.0, 24, 4),
                ("brown", 700.0, 36, 4),
                ("black", 1000.0, 48, 4),
            ]

            for belt, hours, months, stripes in belt_requirements:
                PromotionRequirementFactory(
                    academy=None,  # Global requirements
                    belt=belt,
                    min_mat_hours=hours,
                    min_months_at_belt=months,
                    min_stripes_before_promotion=stripes
                )

        self.stdout.write(f"   ✅ Created {plans_created} plans, {subscriptions_created} subscriptions, {transactions_created} tab transactions, {seminars_created} seminars")

    def _seed_community(self, academies, athletes, achievement_count):
        """Create community achievements and open mat sessions."""
        self.stdout.write(f"🏆 Creating community features ({achievement_count} achievements)...")

        # Create achievement types
        achievements_created = 0
        if not Achievement.objects.exists():
            achievement_configs = [
                # Check-in based achievements
                ("First Steps", "Complete your first training session", "CHECKIN_COUNT", 1),
                ("Getting Started", "Attend 10 training sessions", "CHECKIN_COUNT", 10),
                ("Dedicated Student", "Attend 50 training sessions", "CHECKIN_COUNT", 50),
                ("Regular", "Attend 100 training sessions", "CHECKIN_COUNT", 100),
                ("Academy Veteran", "Attend 250 training sessions", "CHECKIN_COUNT", 250),

                # Mat hours achievements
                ("20 Hours", "Accumulate 20 hours of training", "MAT_HOURS", 20),
                ("50 Hours", "Accumulate 50 hours of training", "MAT_HOURS", 50),
                ("100 Hours", "Accumulate 100 hours of training", "MAT_HOURS", 100),
                ("500 Hours", "Accumulate 500 hours of training", "MAT_HOURS", 500),

                # Streak achievements
                ("Weekly Warrior", "Train 7 days in a row", "STREAK_DAYS", 7),
                ("Monthly Machine", "Train 30 days in a row", "STREAK_DAYS", 30),
                ("Unstoppable", "Train 100 days in a row", "STREAK_DAYS", 100),

                # Manual achievements
                ("Competition Ready", "Competed in a tournament", "MANUAL", None),
                ("Helper", "Assisted with teaching a class", "MANUAL", None),
                ("Community Builder", "Organized an academy event", "MANUAL", None),
            ]

            for name, desc, trigger, value in achievement_configs:
                AchievementFactory(
                    name=name,
                    description=desc,
                    trigger_type=trigger,
                    trigger_value=value
                )
                achievements_created += 1

        achievements = list(Achievement.objects.all())

        # Award achievements to athletes based on their stats
        awards_created = 0
        for athlete in athletes:
            checkin_count = CheckIn.objects.filter(athlete=athlete).count()

            # Award check-in based achievements
            for achievement in achievements:
                if achievement.trigger_type == "CHECKIN_COUNT":
                    if checkin_count >= achievement.trigger_value:
                        AthleteAchievement.objects.get_or_create(
                            athlete=athlete,
                            achievement=achievement,
                            defaults={'awarded_by': None}
                        )
                        awards_created += 1

                elif achievement.trigger_type == "MAT_HOURS":
                    if athlete.mat_hours >= achievement.trigger_value:
                        AthleteAchievement.objects.get_or_create(
                            athlete=athlete,
                            achievement=achievement,
                            defaults={'awarded_by': None}
                        )
                        awards_created += 1

                elif achievement.trigger_type == "MANUAL":
                    # Randomly award some manual achievements
                    if random.random() < 0.15:  # 15% chance
                        AthleteAchievement.objects.get_or_create(
                            athlete=athlete,
                            achievement=achievement,
                            defaults={'awarded_by': None}
                        )
                        awards_created += 1

        # Create open mat sessions
        open_mats_created = 0
        rsvps_created = 0

        for academy in academies:
            academy_athletes = [a for a in athletes if a.academy_id == academy.id]

            # Generate open mats for next 8 weeks (Saturdays)
            start_date = date.today()
            for week in range(8):
                saturday = start_date + timedelta(days=(5 - start_date.weekday()) + (week * 7))

                session = OpenMatSessionFactory(
                    academy=academy,
                    title="Saturday Open Mat",
                    event_date=saturday,
                    start_time="10:00:00",
                    end_time="12:00:00",
                    max_capacity=random.randint(20, 35),
                    is_cancelled=random.random() < 0.05  # 5% cancellation rate
                )
                open_mats_created += 1

                # Athletes RSVP with realistic patterns
                if not session.is_cancelled:
                    rsvp_rate = random.uniform(0.3, 0.7)  # 30-70% RSVP rate
                    rsvp_athletes = random.sample(
                        academy_athletes,
                        int(len(academy_athletes) * rsvp_rate)
                    )

                    for athlete in rsvp_athletes:
                        status = random.choices(
                            ["GOING", "MAYBE", "NOT_GOING"],
                            weights=[60, 25, 15]
                        )[0]

                        OpenMatRSVP.objects.create(
                            session=session,
                            athlete=athlete,
                            status=status
                        )
                        rsvps_created += 1

        self.stdout.write(f"   ✅ Created {achievements_created} achievements, {awards_created} athlete awards, {open_mats_created} open mats, {rsvps_created} RSVPs")

    def _print_summary(self):
        """Print final summary of all seeded data."""
        self.stdout.write("\n📊 Database Seeding Summary:")
        self.stdout.write("=" * 50)

        counts = {
            "Academies": Academy.objects.count(),
            "Users": User.objects.filter(is_superuser=False).count(),
            "Academy Memberships": AcademyMembership.objects.count(),
            "Athletes": AthleteProfile.objects.count(),
            "Belts": Belt.objects.count(),
            "Techniques": Technique.objects.count(),
            "Technique Categories": TechniqueCategory.objects.count(),
            "Training Classes": TrainingClass.objects.count(),
            "Check-ins": CheckIn.objects.count(),
            "Drop-in Visitors": DropInVisitor.objects.count(),
            "Video Library Items": VideoLibraryItem.objects.count(),
            "Sparring Notes": SparringNote.objects.count(),
            "Weight Classes": WeightClass.objects.count(),
            "Timer Presets": TimerPreset.objects.count(),
            "Matchups": Matchup.objects.count(),
            "Matches": Match.objects.count(),
            "Match Events": MatchEvent.objects.count(),
            "Membership Plans": MembershipPlan.objects.count(),
            "Subscriptions": Subscription.objects.count(),
            "Dojo Tab Transactions": DojoTabTransaction.objects.count(),
            "Seminars": Seminar.objects.count(),
            "Seminar Registrations": SeminarRegistration.objects.count(),
            "Achievements": Achievement.objects.count(),
            "Athlete Achievements": AthleteAchievement.objects.count(),
            "Open Mat Sessions": OpenMatSession.objects.count(),
            "Open Mat RSVPs": OpenMatRSVP.objects.count(),
        }

        for model, count in counts.items():
            if count > 0:
                self.stdout.write(f"  {model:25} {count:6}")

        self.stdout.write("=" * 50)
        self.stdout.write(self.style.SUCCESS("✅ Database seeding completed successfully!"))
        self.stdout.write("\nNext steps:")
        self.stdout.write("• Visit http://localhost:8080/admin/ to browse the data")
        self.stdout.write("• Test the API endpoints at http://localhost:8080/api/docs/")
        self.stdout.write("• Run tests: pytest")