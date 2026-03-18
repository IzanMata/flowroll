from contextlib import contextmanager
from django.db.models.signals import post_save
from django.db import transaction
import random
from datetime import datetime, timedelta
from django.utils import timezone


@contextmanager
def mute_signals(*signal_pairs):
    """
    Temporarily disconnect Django signals during bulk operations.

    Usage:
      with mute_signals((post_save, MyModel)):
          MyModelFactory.create_batch(50)
    """
    disconnected = []
    for signal, sender in signal_pairs:
        try:
            signal.disconnect(sender=sender)
            disconnected.append((signal, sender))
        except Exception:
            pass  # Signal wasn't connected

    try:
        yield
    finally:
        for signal, sender in disconnected:
            try:
                signal.connect(sender=sender)
            except Exception:
                pass


def random_past_datetime(days_back=30):
    """Generate random datetime in the past N days."""
    return timezone.now() - timedelta(
        days=random.randint(1, days_back),
        hours=random.randint(6, 22),
        minutes=random.randint(0, 59)
    )


def random_future_datetime(days_ahead=14):
    """Generate random datetime in the future N days."""
    return timezone.now() + timedelta(
        days=random.randint(1, days_ahead),
        hours=random.randint(6, 22),
        minutes=random.randint(0, 59)
    )


def random_belt_choice():
    """Return random belt choice from core Belt model."""
    from core.models import Belt
    belts = ['white', 'blue', 'purple', 'brown', 'black']
    return random.choice(belts)


def random_weight_range(gender='M'):
    """Return realistic weight ranges for BJJ weight classes."""
    if gender == 'M':
        return random.randint(58, 120)  # 58kg to 120kg for males
    elif gender == 'F':
        return random.randint(48, 95)   # 48kg to 95kg for females
    else:
        return random.randint(48, 120)  # Open division


BJJ_TECHNIQUE_NAMES = [
    # Guard techniques
    "Closed Guard", "De La Riva Guard", "X-Guard", "Half Guard", "Spider Guard",
    "Butterfly Guard", "Lasso Guard", "50/50 Guard", "Rubber Guard", "Open Guard",

    # Submissions
    "Armbar", "Triangle Choke", "Rear Naked Choke", "Kimura", "Americana",
    "Omoplata", "Guillotine", "D'Arce Choke", "Anaconda Choke", "Heel Hook",
    "Kneebar", "Toe Hold", "Calf Slicer", "Bicep Slicer", "Ezekiel Choke",

    # Takedowns
    "Double Leg Takedown", "Single Leg Takedown", "Uchi Mata", "Seoi Nage",
    "Osoto Gari", "Kouchi Gari", "Ouchi Gari", "Hip Toss", "Foot Sweep",
    "Ankle Pick", "Duck Under", "Fireman's Carry", "Suplex", "Sprawl",

    # Sweeps
    "Scissor Sweep", "Flower Sweep", "Hook Sweep", "Pendulum Sweep",
    "X-Guard Sweep", "De La Riva Sweep", "Butterfly Sweep", "Hip Bump Sweep"
]

BJJ_ACADEMY_NAMES = [
    "Madrid BJJ Academy", "Barcelona Grappling", "Gracie Valencia",
    "Team Sevilla", "Toledo Jiu-Jitsu", "Bilbao Fight Club",
    "León Brazilian Jiu-Jitsu", "Zaragoza Combat Sports", "Málaga BJJ",
    "Vigo Submission Wrestling", "Alicante Grappling Academy"
]

BJJ_TRAINING_CLASS_TITLES = [
    "Fundamentals Gi", "Advanced No-Gi", "Open Mat", "Competition Prep",
    "Kids Fundamentals", "Beginner Gi", "Intermediate No-Gi", "Sparring Session",
    "Technique Drilling", "Tournament Training", "Women's Only Class",
    "Morning Flow", "Evening Gi", "Advanced Gi", "Submission Only"
]