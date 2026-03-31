"""
Real concurrency tests for the FlowRoll API.

Each test spawns multiple threads that fire simultaneous requests (or service
calls) and asserts the final database state is mathematically exact.  All tests
use ``transaction=True`` so threads run in *real* committed transactions instead
of the savepoint-wrapped transactions used by normal pytest-django tests.

Scenarios covered
-----------------
1. mat_hours atomicity   — 20 athletes check in concurrently; F() must prevent
                            any lost update.
2. Duplicate check-in    — 10 threads race to check the same athlete into the
                            same class; unique_together + get_or_create must
                            allow exactly 1.
3. Match score integrity — 20 concurrent add_event calls (10 per athlete, 2 pts
                            each); select_for_update + F() must yield exact totals.
4. finish_match safety   — finish_match fires alongside 10 concurrent score
                            events; update() must not clobber pending scores.
5. Timer pause safety    — 5 threads race to pause the same RUNNING session;
                            select_for_update must allow exactly 1 to win.
6. Seminar anti-overbook — 10 athletes register concurrently for a 3-spot
                            seminar; select_for_update must keep confirmed ≤ 3.
7. DojoTab balance       — 20 concurrent charges of $1 each; F() must produce
                            an exact final balance of -$20.
"""

import threading
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from athletes.models import AthleteProfile
from attendance.models import CheckIn
from attendance.services import QRCodeService
from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    TrainingClassFactory,
    UserFactory,
)
from matches.models import Match, MatchEvent
from membership.models import (
    DojoTabBalance,
    Seminar,
    SeminarRegistration,
)
from membership.services import DojoTabService, SeminarService
from tatami.models import TimerSession
from tatami.tests.factories import TimerPresetFactory


# ─── helpers ─────────────────────────────────────────────────────────────────


def _client(user):
    """Return a fresh, independently authenticated APIClient per thread."""
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _run_threads(fn, n, barrier=None):
    """
    Spawn *n* threads each calling ``fn(idx)``.  If no barrier is supplied one
    is created so all threads start as simultaneously as possible.  Returns a
    list of return-values in thread-index order.
    """
    if barrier is None:
        barrier = threading.Barrier(n)

    results = [None] * n
    lock = threading.Lock()

    def wrapper(idx):
        try:
            val = fn(idx, barrier)
            with lock:
                results[idx] = val
        except Exception as exc:  # noqa: BLE001
            with lock:
                results[idx] = exc

    threads = [threading.Thread(target=wrapper, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 1. mat_hours atomicity
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
class TestConcurrentMatHours:
    """F() expression prevents lost updates when many check-ins land at once."""

    def test_parallel_checkins_exact_mat_hours(self):
        """
        20 athletes each check in to their own 60-min class simultaneously.
        Every athlete must end up with mat_hours == 1.0 — no lost update.
        """
        N = 20
        academy = AcademyFactory()

        athletes, clients, tokens = [], [], []
        for i in range(N):
            user = UserFactory(username=f"mh_athlete_{i}")
            AcademyMembershipFactory(
                user=user, academy=academy, role="STUDENT", is_active=True
            )
            athlete = AthleteProfileFactory(user=user, academy=academy, mat_hours=0.0)
            tc = TrainingClassFactory(academy=academy, duration_minutes=60)
            token = QRCodeService.generate(tc).token
            athletes.append(athlete)
            clients.append(_client(user))
            tokens.append(token)

        def checkin(idx, barrier):
            barrier.wait()
            r = clients[idx].post(
                "/api/attendance/classes/qr_checkin/", {"token": tokens[idx]}
            )
            return r.status_code

        results = _run_threads(checkin, N)

        assert all(r == status.HTTP_201_CREATED for r in results), (
            f"Some check-ins failed: {results}"
        )
        for athlete in athletes:
            athlete.refresh_from_db()
            assert abs(athlete.mat_hours - 1.0) < 0.001, (
                f"Lost update detected: athlete {athlete.pk} has "
                f"{athlete.mat_hours} mat_hours (expected 1.0)"
            )

    def test_single_athlete_accumulates_mat_hours_over_parallel_classes(self):
        """
        One athlete checks in to 5 different classes simultaneously (each 60 min).
        mat_hours must be exactly 5.0, not less due to a race.
        """
        N = 5
        academy = AcademyFactory()
        user = UserFactory(username="multi_class_athlete")
        AcademyMembershipFactory(
            user=user, academy=academy, role="STUDENT", is_active=True
        )
        athlete = AthleteProfileFactory(user=user, academy=academy, mat_hours=0.0)

        tokens = [
            QRCodeService.generate(
                TrainingClassFactory(academy=academy, duration_minutes=60)
            ).token
            for _ in range(N)
        ]
        client = _client(user)

        def checkin(idx, barrier):
            barrier.wait()
            r = client.post(
                "/api/attendance/classes/qr_checkin/", {"token": tokens[idx]}
            )
            return r.status_code

        results = _run_threads(checkin, N)

        assert all(r == status.HTTP_201_CREATED for r in results), (
            f"Unexpected failures: {results}"
        )
        athlete.refresh_from_db()
        assert abs(athlete.mat_hours - 5.0) < 0.001, (
            f"Lost update: expected 5.0 mat_hours, got {athlete.mat_hours}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Duplicate check-in prevention under concurrency
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
class TestConcurrentDuplicateCheckIn:
    """unique_together on CheckIn stops double-entry even under race conditions."""

    def test_only_one_checkin_succeeds(self):
        """
        10 threads race to check in the same athlete to the same class.
        get_or_create + unique_together guarantees exactly one CheckIn row.
        """
        N = 10
        academy = AcademyFactory()
        user = UserFactory(username="dup_racer")
        AcademyMembershipFactory(
            user=user, academy=academy, role="STUDENT", is_active=True
        )
        athlete = AthleteProfileFactory(user=user, academy=academy, mat_hours=0.0)
        tc = TrainingClassFactory(academy=academy, duration_minutes=60)

        # Each thread generates a fresh token so the QR validation passes —
        # the duplicate is on (athlete, training_class), not on the token.
        tokens = [QRCodeService.generate(tc).token for _ in range(N)]
        client = _client(user)

        def checkin(idx, barrier):
            barrier.wait()
            r = client.post(
                "/api/attendance/classes/qr_checkin/", {"token": tokens[idx]}
            )
            return r.status_code

        results = _run_threads(checkin, N)

        successes = [r for r in results if r == status.HTTP_201_CREATED]
        assert len(successes) == 1, (
            f"Expected exactly 1 success, got {len(successes)}. "
            f"All results: {results}"
        )
        assert CheckIn.objects.filter(athlete=athlete, training_class=tc).count() == 1

        # mat_hours must reflect only one check-in
        athlete.refresh_from_db()
        assert abs(athlete.mat_hours - 1.0) < 0.001, (
            f"mat_hours should be 1.0, got {athlete.mat_hours} "
            "(indicates duplicate check-in processed)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Match score integrity
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
class TestConcurrentMatchScores:
    """select_for_update + F() inside add_event prevent score races."""

    def _setup(self):
        academy = AcademyFactory()
        user_a = UserFactory(username="score_fighter_a")
        user_b = UserFactory(username="score_fighter_b")
        prof = UserFactory(username="score_ref")
        AcademyMembershipFactory(
            user=prof, academy=academy, role="PROFESSOR", is_active=True
        )
        match = Match.objects.create(
            academy=academy,
            athlete_a=user_a,
            athlete_b=user_b,
            duration_seconds=300,
        )
        return academy, match, user_a, user_b, prof

    def test_concurrent_score_events_exact_total(self):
        """
        20 threads simultaneously award 2 points each (10 for A, 10 for B).
        Final score_a and score_b must both equal exactly 20.
        """
        N = 20
        academy, match, user_a, user_b, prof = self._setup()
        aq = f"?academy={academy.pk}"

        def add_event(idx, barrier):
            athlete = user_a if idx % 2 == 0 else user_b
            client = _client(prof)
            barrier.wait()
            r = client.post(
                f"/api/matches/{match.pk}/add_event/{aq}",
                {
                    "athlete": athlete.pk,
                    "event_type": "POINTS",
                    "timestamp": idx + 1,
                    "points_awarded": 2,
                    "action_description": f"takedown_{idx}",
                },
            )
            return r.status_code

        results = _run_threads(add_event, N)

        assert all(r == status.HTTP_201_CREATED for r in results), (
            f"Some events failed: {results}"
        )
        match.refresh_from_db()
        assert match.score_a == 20, (
            f"Lost update on score_a: expected 20, got {match.score_a}"
        )
        assert match.score_b == 20, (
            f"Lost update on score_b: expected 20, got {match.score_b}"
        )
        assert MatchEvent.objects.filter(match=match).count() == N

    def test_finish_match_does_not_clobber_concurrent_scores(self):
        """
        10 add_event calls (+2 pts for athlete_a) race against 1 finish_match.
        finish_match uses .update(is_finished=True, winner_id=…) so it must
        NOT overwrite any score columns.
        """
        N_events = 10
        academy, match, user_a, user_b, prof = self._setup()
        aq = f"?academy={academy.pk}"

        barrier = threading.Barrier(N_events + 1)

        finish_result = [None]
        event_results = [None] * N_events
        lock = threading.Lock()

        def add_event(idx):
            client = _client(prof)
            barrier.wait()
            r = client.post(
                f"/api/matches/{match.pk}/add_event/{aq}",
                {
                    "athlete": user_a.pk,
                    "event_type": "POINTS",
                    "timestamp": idx + 1,
                    "points_awarded": 2,
                    "action_description": f"sweep_{idx}",
                },
            )
            with lock:
                event_results[idx] = r.status_code

        def finish():
            client = _client(prof)
            barrier.wait()
            r = client.post(
                f"/api/matches/{match.pk}/finish_match/{aq}",
                {"winner_id": user_a.pk},
            )
            with lock:
                finish_result[0] = r.status_code

        threads = [
            threading.Thread(target=add_event, args=(i,)) for i in range(N_events)
        ] + [threading.Thread(target=finish)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert finish_result[0] == status.HTTP_200_OK, (
            f"finish_match failed: {finish_result[0]}"
        )
        match.refresh_from_db()
        assert match.is_finished is True
        assert match.winner_id == user_a.pk

        # Count only successful events — finish_match must not have erased them
        successes = sum(1 for r in event_results if r == status.HTTP_201_CREATED)
        expected_score = successes * 2
        assert match.score_a == expected_score, (
            f"finish_match clobbered scores: expected score_a={expected_score}, "
            f"got {match.score_a}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Timer pause safety
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
class TestConcurrentTimerPause:
    """Only one concurrent pause request must win; elapsed_seconds must be sane."""

    def test_only_one_pause_wins(self):
        """
        5 threads simultaneously POST to pause/ on the same RUNNING session.
        select_for_update inside TimerService.pause ensures only 1 succeeds (200);
        the rest must return 400 (already paused).
        """
        academy = AcademyFactory()
        user = UserFactory(username="timer_racer")
        AcademyMembershipFactory(
            user=user, academy=academy, role="PROFESSOR", is_active=True
        )
        preset = TimerPresetFactory(academy=academy)
        session = TimerSession.objects.create(
            preset=preset,
            status=TimerSession.Status.RUNNING,
            started_at=timezone.now(),
            elapsed_seconds=0,
            current_round=1,
        )

        N = 5
        aq = f"?academy={academy.pk}"

        def pause(idx, barrier):
            client = _client(user)
            barrier.wait()
            r = client.post(f"/api/tatami/timer-sessions/{session.pk}/pause/{aq}")
            return r.status_code

        results = _run_threads(pause, N)

        successes = [r for r in results if r == status.HTTP_200_OK]
        failures = [r for r in results if r == status.HTTP_400_BAD_REQUEST]

        assert len(successes) == 1, (
            f"Expected exactly 1 pause success, got {len(successes)}. "
            f"Results: {results}. "
            "This indicates a missing select_for_update in TimerService.pause()."
        )
        assert len(failures) == N - 1, (
            f"Expected {N-1} failures (already paused), got {len(failures)}"
        )

        session.refresh_from_db()
        assert session.status == TimerSession.Status.PAUSED
        # elapsed_seconds must not be doubled (race condition accumulation)
        assert session.elapsed_seconds >= 0
        assert session.elapsed_seconds < 10, (
            f"elapsed_seconds={session.elapsed_seconds} looks doubled — "
            "concurrent pause accumulated time twice"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Seminar anti-overbooking
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
class TestConcurrentSeminarRegistration:
    """select_for_update on Seminar prevents confirmed registrations > capacity."""

    def test_concurrent_registrations_respect_capacity(self):
        """
        10 athletes race to register for a seminar with capacity=3.
        Exactly 3 must be CONFIRMED; the remaining 7 must be WAITLISTED.
        No overbooking regardless of interleaving.
        """
        CAPACITY = 3
        N = 10
        academy = AcademyFactory()
        from datetime import date, timedelta

        seminar = Seminar.objects.create(
            academy=academy,
            title="Pressure Passing Masterclass",
            event_date=date.today() + timedelta(days=30),
            capacity=CAPACITY,
            price=Decimal("50.00"),
            status=Seminar.Status.OPEN,
        )
        athletes = [
            AthleteProfileFactory(academy=academy) for _ in range(N)
        ]

        exceptions = []
        lock = threading.Lock()
        barrier = threading.Barrier(N)

        def register(idx):
            barrier.wait()
            try:
                SeminarService.register(athletes[idx], seminar)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    exceptions.append(exc)

        threads = [threading.Thread(target=register, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        confirmed = SeminarRegistration.objects.filter(
            seminar=seminar,
            status=SeminarRegistration.RegistrationStatus.CONFIRMED,
        ).count()
        waitlisted = SeminarRegistration.objects.filter(
            seminar=seminar,
            status=SeminarRegistration.RegistrationStatus.WAITLISTED,
        ).count()

        assert confirmed <= CAPACITY, (
            f"OVERBOOKING: {confirmed} confirmed registrations "
            f"but capacity is {CAPACITY}"
        )
        assert confirmed == CAPACITY, (
            f"Under-booked: only {confirmed}/{CAPACITY} spots filled "
            f"(check select_for_update logic)"
        )
        assert confirmed + waitlisted == N, (
            f"Missing registrations: {confirmed + waitlisted} total, expected {N}"
        )

    def test_capacity_one_under_max_concurrency(self):
        """
        Edge case: capacity=1 with 8 concurrent registrations.
        Exactly 1 must be confirmed; 7 waitlisted.
        """
        N = 8
        academy = AcademyFactory()
        from datetime import date, timedelta

        seminar = Seminar.objects.create(
            academy=academy,
            title="Private Session",
            event_date=date.today() + timedelta(days=7),
            capacity=1,
            price=Decimal("0.00"),
            status=Seminar.Status.OPEN,
        )
        athletes = [AthleteProfileFactory(academy=academy) for _ in range(N)]
        barrier = threading.Barrier(N)

        def register(idx):
            barrier.wait()
            try:
                SeminarService.register(athletes[idx], seminar)
            except Exception:  # noqa: BLE001
                pass

        threads = [threading.Thread(target=register, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        confirmed = SeminarRegistration.objects.filter(
            seminar=seminar,
            status=SeminarRegistration.RegistrationStatus.CONFIRMED,
        ).count()

        assert confirmed == 1, (
            f"OVERBOOKING with capacity=1: {confirmed} confirmed registrations"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 6. DojoTab balance atomicity
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
class TestConcurrentDojoTabBalance:
    """F() expression in _update_balance prevents lost updates on the balance."""

    def test_concurrent_charges_produce_exact_balance(self):
        """
        20 concurrent charges of $1.00 each must yield a final balance of -$20.00.
        If the update used read-modify-write instead of F(), some charges would
        be silently lost.
        """
        N = 20
        AMOUNT = Decimal("1.00")
        academy = AcademyFactory()
        athlete = AthleteProfileFactory(academy=academy)

        barrier = threading.Barrier(N)

        def charge(idx):
            barrier.wait()
            DojoTabService.charge(
                athlete, academy, AMOUNT, f"concurrent charge {idx}"
            )

        threads = [threading.Thread(target=charge, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final_balance = DojoTabService.get_balance(athlete, academy)
        expected = -(AMOUNT * N)

        assert final_balance == expected, (
            f"Lost update on DojoTab balance: expected {expected}, "
            f"got {final_balance} "
            f"(missed {abs(expected - final_balance)} in charges)"
        )
        assert DojoTabBalance.objects.filter(
            athlete=athlete, academy=academy
        ).count() == 1

    def test_concurrent_mixed_charges_and_credits_exact_balance(self):
        """
        10 charges of $2 and 10 credits of $1 fire simultaneously.
        Expected balance: -(10×$2) + (10×$1) = -$10.
        """
        N = 20
        academy = AcademyFactory()
        athlete = AthleteProfileFactory(academy=academy)
        barrier = threading.Barrier(N)

        def transact(idx):
            barrier.wait()
            if idx % 2 == 0:
                DojoTabService.charge(
                    athlete, academy, Decimal("2.00"), f"charge_{idx}"
                )
            else:
                DojoTabService.credit(
                    athlete, academy, Decimal("1.00"), f"credit_{idx}"
                )

        threads = [threading.Thread(target=transact, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final_balance = DojoTabService.get_balance(athlete, academy)
        # 10 debits × $2 = $20, 10 credits × $1 = $10 → net -$10
        assert final_balance == Decimal("-10.00"), (
            f"Balance mismatch: expected -10.00, got {final_balance}"
        )
