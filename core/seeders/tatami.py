from django.contrib.auth import get_user_model
from django.db import transaction
from tatami.models import WeightClass, TimerPreset, TimerSession, Matchup
from academies.models import Academy
from athletes.models import AthleteProfile
from core.models import AcademyMembership
import random

User = get_user_model()


def seed_weight_classes():
    """Create 9 BJJ weight classes for each gender."""

    if WeightClass.objects.exists():
        print("  ⏭  Weight Classes already seeded, skipping.")
        return

    weight_classes_data = [
        # Male divisions
        {'name': 'Rooster', 'min_weight': 57.0, 'max_weight': 64.0, 'gender': WeightClass.Gender.MALE},
        {'name': 'Light-Feather', 'min_weight': 64.0, 'max_weight': 70.0, 'gender': WeightClass.Gender.MALE},
        {'name': 'Feather', 'min_weight': 70.0, 'max_weight': 76.0, 'gender': WeightClass.Gender.MALE},
        {'name': 'Light', 'min_weight': 76.0, 'max_weight': 82.0, 'gender': WeightClass.Gender.MALE},
        {'name': 'Middle', 'min_weight': 82.0, 'max_weight': 88.0, 'gender': WeightClass.Gender.MALE},
        {'name': 'Medium-Heavy', 'min_weight': 88.0, 'max_weight': 94.0, 'gender': WeightClass.Gender.MALE},
        {'name': 'Heavy', 'min_weight': 94.0, 'max_weight': 100.0, 'gender': WeightClass.Gender.MALE},
        {'name': 'Super-Heavy', 'min_weight': 100.0, 'max_weight': 110.0, 'gender': WeightClass.Gender.MALE},
        {'name': 'Ultra-Heavy', 'min_weight': 110.0, 'max_weight': 120.0, 'gender': WeightClass.Gender.MALE},

        # Female divisions (typically 10kg lighter)
        {'name': 'Light-Feather', 'min_weight': 48.0, 'max_weight': 53.0, 'gender': WeightClass.Gender.FEMALE},
        {'name': 'Feather', 'min_weight': 53.0, 'max_weight': 58.0, 'gender': WeightClass.Gender.FEMALE},
        {'name': 'Light', 'min_weight': 58.0, 'max_weight': 64.0, 'gender': WeightClass.Gender.FEMALE},
        {'name': 'Middle', 'min_weight': 64.0, 'max_weight': 69.0, 'gender': WeightClass.Gender.FEMALE},
        {'name': 'Medium-Heavy', 'min_weight': 69.0, 'max_weight': 74.0, 'gender': WeightClass.Gender.FEMALE},
        {'name': 'Heavy', 'min_weight': 74.0, 'max_weight': 79.0, 'gender': WeightClass.Gender.FEMALE},
        {'name': 'Super-Heavy', 'min_weight': 79.0, 'max_weight': 90.0, 'gender': WeightClass.Gender.FEMALE},
        {'name': 'Ultra-Heavy', 'min_weight': 90.0, 'max_weight': 100.0, 'gender': WeightClass.Gender.FEMALE},

        # Open divisions
        {'name': 'Open', 'min_weight': 48.0, 'max_weight': 120.0, 'gender': WeightClass.Gender.OPEN},
    ]

    with transaction.atomic():
        weight_classes_to_create = []

        for wc_data in weight_classes_data:
            weight_class = WeightClass(
                name=wc_data['name'],
                min_weight=wc_data['min_weight'],
                max_weight=wc_data['max_weight'],
                gender=wc_data['gender'],
            )
            weight_classes_to_create.append(weight_class)

        WeightClass.objects.bulk_create(weight_classes_to_create, ignore_conflicts=True, batch_size=20)

    print(f"  ✅ Weight Classes: {WeightClass.objects.count()} records")


def seed_timer_presets():
    """Create 3 timer presets per academy."""

    if TimerPreset.objects.exists():
        print("  ⏭  Timer Presets already seeded, skipping.")
        return

    with transaction.atomic():
        academies = list(Academy.objects.all())
        presets_to_create = []

        preset_configs = [
            {'name': 'IBJJF Tournament', 'format': TimerPreset.Format.IBJJF, 'duration': 300, 'rest': 60, 'rounds': 1},
            {'name': 'ADCC Rules', 'format': TimerPreset.Format.ADCC, 'duration': 600, 'rest': 90, 'rounds': 1},
            {'name': 'Positional Sparring', 'format': TimerPreset.Format.POSITIONAL, 'duration': 180, 'rest': 30, 'rounds': 3},
        ]

        for academy in academies:
            for config in preset_configs:
                preset = TimerPreset(
                    academy=academy,
                    name=config['name'],
                    format=config['format'],
                    round_duration_seconds=config['duration'],
                    rest_duration_seconds=config['rest'],
                    overtime_seconds=random.choice([0, 60, 120]),
                    rounds=config['rounds'],
                )
                presets_to_create.append(preset)

        TimerPreset.objects.bulk_create(presets_to_create, ignore_conflicts=True, batch_size=20)

    print(f"  ✅ Timer Presets: {TimerPreset.objects.count()} records")


def seed_timer_sessions():
    """Create 2 timer sessions per academy."""

    if TimerSession.objects.exists():
        print("  ⏭  Timer Sessions already seeded, skipping.")
        return

    with transaction.atomic():
        presets = list(TimerPreset.objects.all())
        sessions_to_create = []

        # Create 2 sessions per academy
        academies = Academy.objects.all()
        for academy in academies:
            academy_presets = [p for p in presets if p.academy == academy]

            if academy_presets:
                # 1 finished session, 1 idle session
                finished_preset = random.choice(academy_presets)
                idle_preset = random.choice(academy_presets)

                finished_session = TimerSession(
                    preset=finished_preset,
                    status=TimerSession.Status.FINISHED,
                    current_round=finished_preset.rounds,
                    elapsed_seconds=finished_preset.round_duration_seconds * finished_preset.rounds,
                )

                idle_session = TimerSession(
                    preset=idle_preset,
                    status=TimerSession.Status.IDLE,
                    current_round=1,
                    elapsed_seconds=0,
                )

                sessions_to_create.extend([finished_session, idle_session])

        TimerSession.objects.bulk_create(sessions_to_create, ignore_conflicts=True, batch_size=20)

    print(f"  ✅ Timer Sessions: {TimerSession.objects.count()} records")


def seed_matchups():
    """Create 5 matchups per academy."""

    if Matchup.objects.exists():
        print("  ⏭  Matchups already seeded, skipping.")
        return

    with transaction.atomic():
        academies = list(Academy.objects.all())
        weight_classes = list(WeightClass.objects.all())
        matchups_to_create = []

        for academy in academies:
            # Get athlete profiles for this academy
            athletes = list(AthleteProfile.objects.filter(academy=academy))

            if len(athletes) >= 2:
                for i in range(5):  # 5 matchups per academy
                    athlete_a, athlete_b = random.sample(athletes, 2)

                    matchup = Matchup(
                        academy=academy,
                        athlete_a=athlete_a,
                        athlete_b=athlete_b,
                        weight_class=random.choice(weight_classes),
                        match_format=random.choice([
                            Matchup.MatchFormat.TOURNAMENT,
                            Matchup.MatchFormat.SURVIVAL
                        ]),
                        round_number=random.randint(1, 3),
                        status=random.choice([
                            Matchup.Status.PENDING,
                            Matchup.Status.COMPLETED
                        ]),
                    )

                    # Set winner for completed matchups
                    if matchup.status == Matchup.Status.COMPLETED:
                        matchup.winner = random.choice([athlete_a, athlete_b])

                    matchups_to_create.append(matchup)

        Matchup.objects.bulk_create(matchups_to_create, ignore_conflicts=True, batch_size=30)

    print(f"  ✅ Matchups: {Matchup.objects.count()} records")