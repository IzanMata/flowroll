from django.contrib.auth import get_user_model
from django.db import transaction
from academies.models import Academy
from core.models import AcademyMembership, Belt
from athletes.models import AthleteProfile
from academies.tests.factories import AcademyFactory, AcademyMembershipFactory
from athletes.tests.factories import AthleteProfileFactory
from core.seeders.utils import BJJ_ACADEMY_NAMES
import random

User = get_user_model()


def seed_academies():
    """Create academies for professors."""

    if Academy.objects.exists():
        print("  ⏭  Academies already seeded, skipping.")
        return

    with transaction.atomic():
        academy_names = BJJ_ACADEMY_NAMES[:3]  # Create 3 academies

        for academy_name in academy_names:
            Academy.objects.get_or_create(name=academy_name)

    print(f"  ✅ Academies: {Academy.objects.count()} records")


def seed_memberships():
    """Create academy memberships for all users."""

    if AcademyMembership.objects.exists():
        print("  ⏭  Academy Memberships already seeded, skipping.")
        return

    with transaction.atomic():
        academies = list(Academy.objects.all())
        users = list(User.objects.all())

        memberships_to_create = []

        # Assign professors to academies first
        professors = [user for user in users if user.username.startswith('professor')]
        for i, professor in enumerate(professors):
            if i < len(academies):
                # Professor becomes OWNER of academy
                membership = AcademyMembership(
                    user=professor,
                    academy=academies[i],
                    role=AcademyMembership.Role.OWNER,
                    is_active=True
                )
                memberships_to_create.append(membership)

        # Now assign other users
        for user in users:
            # Skip professors who are already owners
            if user.username.startswith('professor'):
                continue

            # Each user belongs to at least 1 academy, some to multiple
            academy_count = random.choices([1, 2, 3], weights=[70, 25, 5])[0]
            user_academies = random.sample(academies, min(academy_count, len(academies)))

            for academy in user_academies:
                membership = AcademyMembership(
                    user=user,
                    academy=academy,
                    role=AcademyMembership.Role.STUDENT,
                    is_active=True
                )
                memberships_to_create.append(membership)

        AcademyMembership.objects.bulk_create(memberships_to_create, ignore_conflicts=True, batch_size=50)

    print(f"  ✅ Academy Memberships: {AcademyMembership.objects.count()} records")


def seed_athlete_profiles():
    """Create athlete profiles for all users."""

    if AthleteProfile.objects.exists():
        print("  ⏭  Athlete Profiles already seeded, skipping.")
        return

    with transaction.atomic():
        users = User.objects.all()
        profiles_to_create = []

        for user in users:
            # Get user's primary academy (first membership)
            membership = AcademyMembership.objects.filter(user=user, is_active=True).first()

            if membership:
                # Determine role
                if membership.role == AcademyMembership.Role.PROFESSOR or membership.role == AcademyMembership.Role.OWNER:
                    profile_role = AthleteProfile.RoleChoices.PROFESSOR
                else:
                    profile_role = AthleteProfile.RoleChoices.STUDENT

                # Random belt and attributes
                belt = random.choice([Belt.BeltColor.WHITE, Belt.BeltColor.BLUE, Belt.BeltColor.PURPLE, Belt.BeltColor.BROWN, Belt.BeltColor.BLACK])
                stripes = random.randint(0, 4)
                weight = random.uniform(50.0, 120.0)

                profile = AthleteProfile(
                    user=user,
                    academy=membership.academy,
                    role=profile_role,
                    belt=belt,
                    stripes=stripes,
                    weight=weight
                )
                profiles_to_create.append(profile)

        AthleteProfile.objects.bulk_create(profiles_to_create, ignore_conflicts=True, batch_size=50)

    print(f"  ✅ Athlete Profiles: {AthleteProfile.objects.count()} records")