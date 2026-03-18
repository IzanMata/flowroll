from django.contrib.auth import get_user_model
from django.db import transaction
from matches.models import Match, MatchEvent
import random

User = get_user_model()


def seed_matches():
    """Create 20 matches (10 finished, 10 pending)."""

    if Match.objects.exists():
        print("  ⏭  Matches already seeded, skipping.")
        return

    with transaction.atomic():
        users = list(User.objects.all())
        matches_to_create = []

        for i in range(20):
            # Select two different athletes
            athlete_a, athlete_b = random.sample(users, 2)

            match = Match(
                athlete_a=athlete_a,
                athlete_b=athlete_b,
                duration_seconds=random.randint(300, 600),  # 5-10 minutes
            )
            matches_to_create.append(match)

        Match.objects.bulk_create(matches_to_create, ignore_conflicts=True, batch_size=20)

    print(f"  ✅ Matches: {Match.objects.count()} records")


def seed_match_events():
    """Create events for finished matches."""

    if MatchEvent.objects.exists():
        print("  ⏭  Match Events already seeded, skipping.")
        return

    with transaction.atomic():
        matches = list(Match.objects.all())

        # Make first 10 matches "finished" by adding events
        finished_matches = matches[:10]
        events_to_create = []

        for match in finished_matches:
            # Create 3-6 events per finished match
            event_count = random.randint(3, 6)

            for i in range(event_count):
                event_type = random.choice([
                    MatchEvent.TypeChoices.POINTS,
                    MatchEvent.TypeChoices.ADVANTAGE,
                    MatchEvent.TypeChoices.PENALTY,
                    MatchEvent.TypeChoices.SUBMISSION
                ])
                athlete = random.choice([match.athlete_a, match.athlete_b])

                if event_type == MatchEvent.TypeChoices.POINTS:
                    points = random.choice([2, 3, 4])  # Sweep, guard pass, mount/back
                    action = random.choice(['Sweep', 'Guard Pass', 'Mount', 'Back Control'])
                elif event_type == MatchEvent.TypeChoices.SUBMISSION:
                    points = 0
                    action = random.choice(['Armbar', 'Triangle', 'Rear Naked Choke', 'Kimura'])
                else:
                    points = 0
                    action = random.choice(['Advantage', 'Penalty', 'Stalling'])

                event = MatchEvent(
                    match=match,
                    athlete=athlete,
                    timestamp=random.randint(0, match.duration_seconds),
                    points_awarded=points,
                    action_description=action,
                    event_type=event_type,
                )
                events_to_create.append(event)

        MatchEvent.objects.bulk_create(events_to_create, ignore_conflicts=True, batch_size=50)

        # Update match scores and winners for finished matches
        for match in finished_matches:
            events_a = MatchEvent.objects.filter(match=match, athlete=match.athlete_a)
            events_b = MatchEvent.objects.filter(match=match, athlete=match.athlete_b)

            score_a = sum(event.points_awarded for event in events_a)
            score_b = sum(event.points_awarded for event in events_b)

            # Check for submissions (auto-win)
            sub_a = events_a.filter(event_type=MatchEvent.TypeChoices.SUBMISSION).exists()
            sub_b = events_b.filter(event_type=MatchEvent.TypeChoices.SUBMISSION).exists()

            if sub_a:
                winner = match.athlete_a
            elif sub_b:
                winner = match.athlete_b
            elif score_a > score_b:
                winner = match.athlete_a
            elif score_b > score_a:
                winner = match.athlete_b
            else:
                winner = None  # Draw

            # Update match (direct DB update to bypass service layer)
            Match.objects.filter(id=match.id).update(
                score_a=score_a,
                score_b=score_b,
                winner=winner,
                is_finished=True
            )

    print(f"  ✅ Match Events: {MatchEvent.objects.count()} records")
    print(f"  ✅ Finished Matches: {Match.objects.filter(is_finished=True).count()} records")