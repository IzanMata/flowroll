import sys

from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.db import transaction


@receiver(post_migrate)
def auto_seed(sender, **kwargs):
    """Auto-seed database after migrations complete."""

    # Only fire once (when core app migrates)
    if sender.name != "core":
        return

    # Skip seeding during test runs to avoid polluting the test database
    if "pytest" in sys.modules:
        return

    print("🥋 FlowRoll: seeding database...")

    with transaction.atomic():
        # Import seeders
        from core.seeders.techniques import seed_belts, seed_technique_categories
        from core.seeders.tatami import seed_weight_classes
        from core.seeders.users import seed_users
        from core.seeders.academies import seed_academies, seed_memberships, seed_athlete_profiles
        from core.seeders.techniques import seed_techniques
        from core.seeders.attendance import seed_training_classes, seed_checkins, seed_qr_codes, seed_drop_in_visitors
        from core.seeders.matches import seed_matches, seed_match_events
        from core.seeders.tatami import seed_timer_presets, seed_timer_sessions, seed_matchups

        # Seed in dependency order
        seed_belts()                # No dependencies
        seed_weight_classes()       # No dependencies
        seed_technique_categories() # No dependencies
        seed_users()               # No dependencies
        seed_academies()           # Needs users
        seed_memberships()         # Needs users + academies
        seed_athlete_profiles()    # Needs users + academies
        seed_techniques()          # Needs categories + belts
        seed_training_classes()    # Needs academies + users
        seed_checkins()            # Needs users + training_classes
        seed_qr_codes()            # Needs training_classes
        seed_drop_in_visitors()    # Needs academies + training_classes
        seed_matches()             # Needs users
        seed_match_events()        # Needs matches + users
        seed_timer_presets()       # Needs academies
        seed_timer_sessions()      # Needs timer_presets
        seed_matchups()            # Needs academies + users + weight_classes

    print("✅ FlowRoll seed complete!")