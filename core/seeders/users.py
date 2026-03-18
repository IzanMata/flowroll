from django.contrib.auth import get_user_model
from django.db import transaction
from core.tests.factories import SuperUserFactory, ProfessorFactory, StudentFactory

User = get_user_model()


def seed_users():
    """Create superadmin, professors, and students with known credentials."""

    # Guard: check if we already have seeded users
    if User.objects.filter(username='admin').exists():
        print("  ⏭  Users already seeded, skipping.")
        return

    with transaction.atomic():
        # 1. Create superuser
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@flowroll.com',
                'first_name': 'Super',
                'last_name': 'Admin',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin.set_password('FlowRoll2024!')
            admin.save()

        # 2. Create professors (academy owners)
        prof1, created = User.objects.get_or_create(
            username='professor1',
            defaults={
                'email': 'professor1@flowroll.com',
                'first_name': 'Carlos',
                'last_name': 'Gracie',
            }
        )
        if created:
            prof1.set_password('FlowRoll2024!')
            prof1.save()

        prof2, created = User.objects.get_or_create(
            username='professor2',
            defaults={
                'email': 'professor2@flowroll.com',
                'first_name': 'Ricardo',
                'last_name': 'De La Riva',
            }
        )
        if created:
            prof2.set_password('FlowRoll2024!')
            prof2.save()

        # 3. Create known student
        student1, created = User.objects.get_or_create(
            username='student1',
            defaults={
                'email': 'student1@flowroll.com',
                'first_name': 'João',
                'last_name': 'Silva',
            }
        )
        if created:
            student1.set_password('FlowRoll2024!')
            student1.save()

        # 4. Bulk create additional students
        existing_count = User.objects.count()
        if existing_count < 23:  # We want 23 total users
            students_needed = 23 - existing_count
            students_to_create = []

            for i in range(students_needed):
                user = StudentFactory.build()
                students_to_create.append(user)

            User.objects.bulk_create(students_to_create, ignore_conflicts=True, batch_size=20)

            # Set passwords for bulk created users (can't use bulk_create with hashed passwords)
            for user in User.objects.filter(username__startswith='student').exclude(username='student1'):
                user.set_password('FlowRoll2024!')
                user.save()

    print(f"  ✅ Users: {User.objects.count()} records")