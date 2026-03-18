from django.db import transaction
from core.models import Belt
from techniques.models import TechniqueCategory, Technique, TechniqueVariation, TechniqueFlow
from core.seeders.utils import BJJ_TECHNIQUE_NAMES
import random


def seed_belts():
    """Create the 5 standard BJJ belt colors."""

    if Belt.objects.exists():
        print("  ⏭  Belts already seeded, skipping.")
        return

    belts_data = [
        {'color': Belt.BeltColor.WHITE, 'order': 1},
        {'color': Belt.BeltColor.BLUE, 'order': 2},
        {'color': Belt.BeltColor.PURPLE, 'order': 3},
        {'color': Belt.BeltColor.BROWN, 'order': 4},
        {'color': Belt.BeltColor.BLACK, 'order': 5},
    ]

    with transaction.atomic():
        for belt_data in belts_data:
            Belt.objects.get_or_create(
                color=belt_data['color'],
                defaults={'order': belt_data['order']}
            )

    print(f"  ✅ Belts: {Belt.objects.count()} records")


def seed_technique_categories():
    """Create the 8 main BJJ technique categories."""

    if TechniqueCategory.objects.exists():
        print("  ⏭  Technique Categories already seeded, skipping.")
        return

    categories_data = [
        {'name': 'Guard', 'description': 'Guard positions and techniques'},
        {'name': 'Submissions', 'description': 'Joint locks and chokes'},
        {'name': 'Takedowns', 'description': 'Standing takedown techniques'},
        {'name': 'Escapes', 'description': 'Escape techniques from bad positions'},
        {'name': 'Sweeps', 'description': 'Guard sweep techniques'},
        {'name': 'Passing', 'description': 'Guard passing techniques'},
        {'name': 'Back Attacks', 'description': 'Back control and submissions'},
        {'name': 'Leg Locks', 'description': 'Leg submission techniques'},
    ]

    with transaction.atomic():
        for cat_data in categories_data:
            TechniqueCategory.objects.get_or_create(
                name=cat_data['name'],
                defaults={'description': cat_data['description']}
            )

    print(f"  ✅ Technique Categories: {TechniqueCategory.objects.count()} records")


def seed_techniques():
    """Create 40 techniques with variations and flows."""

    if Technique.objects.exists():
        print("  ⏭  Techniques already seeded, skipping.")
        return

    with transaction.atomic():
        categories = list(TechniqueCategory.objects.all())
        belts = list(Belt.objects.all())

        # Create 5 techniques per category = 40 total
        techniques_created = []

        for category in categories:
            category_techniques = []
            for i in range(5):
                technique_name = random.choice(BJJ_TECHNIQUE_NAMES)

                # Ensure unique names
                while Technique.objects.filter(name=technique_name).exists():
                    technique_name = f"{random.choice(BJJ_TECHNIQUE_NAMES)} {random.choice(['Classic', 'Modern', 'Advanced'])}"

                technique = Technique(
                    name=technique_name,
                    description=f"Detailed breakdown of {technique_name} technique execution",
                    difficulty=random.randint(1, 5),
                    min_belt=random.choice([Belt.BeltColor.WHITE, Belt.BeltColor.BLUE, Belt.BeltColor.PURPLE, Belt.BeltColor.BROWN, Belt.BeltColor.BLACK]),
                )
                category_techniques.append(technique)

            Technique.objects.bulk_create(category_techniques, ignore_conflicts=True, batch_size=20)

            # Add categories to created techniques
            created_techniques = Technique.objects.filter(
                name__in=[t.name for t in category_techniques]
            )
            for technique in created_techniques:
                technique.categories.add(category)
                techniques_created.append(technique)

        # Create variations (1-2 per technique)
        variations_to_create = []
        for technique in techniques_created:
            variation_count = random.randint(1, 2)
            for i in range(variation_count):
                variation_type = random.choice(['Setup', 'Finish', 'Counter', 'Entry', 'Transition'])
                variation = TechniqueVariation(
                    technique=technique,
                    name=f"{technique.name} - {variation_type}",
                    description=f"Alternative {variation_type.lower()} for {technique.name}"
                )
                variations_to_create.append(variation)

        TechniqueVariation.objects.bulk_create(variations_to_create, ignore_conflicts=True, batch_size=50)

        # Create flows (connect related techniques)
        flows_to_create = []
        technique_pairs = random.sample(techniques_created, min(20, len(techniques_created)))

        for i in range(0, len(technique_pairs) - 1, 2):
            if i + 1 < len(technique_pairs):
                from_tech = technique_pairs[i]
                to_tech = technique_pairs[i + 1]

                flow = TechniqueFlow(
                    from_technique=from_tech,
                    to_technique=to_tech,
                    transition_type=random.choice(['chain', 'counter', 'escape', 'setup']),
                    description=f"Flow from {from_tech.name} to {to_tech.name}"
                )
                flows_to_create.append(flow)

        TechniqueFlow.objects.bulk_create(flows_to_create, ignore_conflicts=True, batch_size=30)

    print(f"  ✅ Techniques: {Technique.objects.count()} records")
    print(f"  ✅ Technique Variations: {TechniqueVariation.objects.count()} records")
    print(f"  ✅ Technique Flows: {TechniqueFlow.objects.count()} records")