"""
State machine tests for TimerSession and Match.

TimerSession valid transitions:
    IDLE ──start──► RUNNING ──pause──► PAUSED ──start──► RUNNING
                        └───finish──► FINISHED ◄──finish──┘

Invalid transitions must return 400.

Match state:
    is_finished=False ──finish_match──► is_finished=True (terminal)
"""

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    UserFactory,
)
from matches.models import Match
from tatami.models import TimerSession
from tatami.tests.factories import TimerPresetFactory


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _prof_setup():
    academy = AcademyFactory()
    prof = UserFactory()
    AcademyMembershipFactory(user=prof, academy=academy, role="PROFESSOR", is_active=True)
    return academy, prof, _client(prof)


def _create_session(academy, status_=TimerSession.Status.IDLE, started_at=None):
    preset = TimerPresetFactory(academy=academy)
    return TimerSession.objects.create(
        preset=preset,
        status=status_,
        started_at=started_at or (timezone.now() if status_ == TimerSession.Status.RUNNING else None),
        elapsed_seconds=0,
        current_round=1,
    )


# ══════════════════════════════════════════════════════════════════════════════
# TimerSession state machine
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTimerSessionStateMachine:
    """Full valid + invalid transition matrix."""

    # ── Valid transitions ──────────────────────────────────────────────────

    def test_idle_to_running_via_start_session(self):
        academy, prof, client = _prof_setup()
        preset = TimerPresetFactory(academy=academy)
        r = client.post(
            f"/api/v1/tatami/timer-presets/{preset.pk}/start_session/"
            f"?academy={academy.pk}"
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.data["status"] == TimerSession.Status.RUNNING
        assert r.data["started_at"] is not None

    def test_running_to_paused_via_pause(self):
        academy, prof, client = _prof_setup()
        session = _create_session(academy, TimerSession.Status.RUNNING)
        r = client.post(
            f"/api/v1/tatami/timer-sessions/{session.pk}/pause/"
            f"?academy={academy.pk}"
        )
        assert r.status_code == status.HTTP_200_OK
        session.refresh_from_db()
        assert session.status == TimerSession.Status.PAUSED
        assert session.paused_at is not None
        assert session.elapsed_seconds >= 0

    def test_paused_to_running_via_start_session_on_preset(self):
        """
        A PAUSED session is resumed by calling start_session again on its preset.
        TimerService.start() accepts IDLE and PAUSED states.
        """
        academy, prof, client = _prof_setup()
        # Create a paused session manually
        preset = TimerPresetFactory(academy=academy)
        session = TimerSession.objects.create(
            preset=preset,
            status=TimerSession.Status.PAUSED,
            started_at=timezone.now() - timezone.timedelta(seconds=10),
            paused_at=timezone.now(),
            elapsed_seconds=10,
            current_round=1,
        )
        # Resume via the session-level start: call start_session to create a
        # new one is NOT the right approach — the service handles resume
        # by accepting PAUSED state in start().
        from tatami.services import TimerService
        TimerService.start(session)
        session.refresh_from_db()
        assert session.status == TimerSession.Status.RUNNING

    def test_running_to_finished_via_finish(self):
        academy, prof, client = _prof_setup()
        session = _create_session(academy, TimerSession.Status.RUNNING)
        r = client.post(
            f"/api/v1/tatami/timer-sessions/{session.pk}/finish/"
            f"?academy={academy.pk}"
        )
        assert r.status_code == status.HTTP_200_OK
        session.refresh_from_db()
        assert session.status == TimerSession.Status.FINISHED

    def test_paused_to_finished_via_finish(self):
        academy, prof, client = _prof_setup()
        session = _create_session(academy, TimerSession.Status.RUNNING)
        # Pause first
        client.post(
            f"/api/v1/tatami/timer-sessions/{session.pk}/pause/"
            f"?academy={academy.pk}"
        )
        # Then finish
        r = client.post(
            f"/api/v1/tatami/timer-sessions/{session.pk}/finish/"
            f"?academy={academy.pk}"
        )
        assert r.status_code == status.HTTP_200_OK
        session.refresh_from_db()
        assert session.status == TimerSession.Status.FINISHED

    # ── Invalid transitions ────────────────────────────────────────────────

    def test_pause_idle_session_returns_400(self):
        academy, prof, client = _prof_setup()
        session = _create_session(academy, TimerSession.Status.IDLE)
        r = client.post(
            f"/api/v1/tatami/timer-sessions/{session.pk}/pause/"
            f"?academy={academy.pk}"
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_pause_already_paused_session_returns_400(self):
        academy, prof, client = _prof_setup()
        session = _create_session(academy, TimerSession.Status.RUNNING)
        # First pause succeeds
        client.post(
            f"/api/v1/tatami/timer-sessions/{session.pk}/pause/?academy={academy.pk}"
        )
        # Second pause must fail
        r = client.post(
            f"/api/v1/tatami/timer-sessions/{session.pk}/pause/?academy={academy.pk}"
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_pause_finished_session_returns_400(self):
        academy, prof, client = _prof_setup()
        session = _create_session(academy, TimerSession.Status.RUNNING)
        client.post(
            f"/api/v1/tatami/timer-sessions/{session.pk}/finish/?academy={academy.pk}"
        )
        r = client.post(
            f"/api/v1/tatami/timer-sessions/{session.pk}/pause/?academy={academy.pk}"
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_start_finished_session_raises(self):
        """TimerService.start() must refuse FINISHED state."""
        from tatami.services import TimerService
        academy, _, _ = _prof_setup()
        session = _create_session(academy, TimerSession.Status.RUNNING)
        TimerService.finish(session)
        session.refresh_from_db()
        with pytest.raises(ValueError, match="Cannot start"):
            TimerService.start(session)

    # ── elapsed_seconds accumulation ──────────────────────────────────────

    def test_elapsed_seconds_accumulates_across_pause_resume(self):
        """
        Start → pause (≥0 elapsed) → resume → pause again.
        Each pause must *add* to elapsed_seconds, not reset it.
        """
        from tatami.services import TimerService
        academy, _, _ = _prof_setup()
        session = _create_session(academy, TimerSession.Status.RUNNING)

        # First pause
        TimerService.pause(session)
        session.refresh_from_db()
        first_elapsed = session.elapsed_seconds
        assert first_elapsed >= 0

        # Resume
        TimerService.start(session)
        session.refresh_from_db()
        assert session.status == TimerSession.Status.RUNNING

        # Second pause — elapsed_seconds must be strictly ≥ first
        TimerService.pause(session)
        session.refresh_from_db()
        assert session.elapsed_seconds >= first_elapsed, (
            f"elapsed_seconds regressed: {first_elapsed} → {session.elapsed_seconds}"
        )

    def test_start_session_response_contains_required_fields(self):
        academy, prof, client = _prof_setup()
        preset = TimerPresetFactory(academy=academy)
        r = client.post(
            f"/api/v1/tatami/timer-presets/{preset.pk}/start_session/"
            f"?academy={academy.pk}"
        )
        assert r.status_code == status.HTTP_201_CREATED
        for field in ("id", "status", "started_at", "elapsed_seconds", "current_round"):
            assert field in r.data, f"Missing field in start_session response: {field}"


# ══════════════════════════════════════════════════════════════════════════════
# Match state machine
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestMatchStateMachine:

    def _setup(self):
        academy = AcademyFactory()
        user_a = UserFactory()
        user_b = UserFactory()
        prof = UserFactory()
        AcademyMembershipFactory(user=prof, academy=academy, role="PROFESSOR", is_active=True)
        match = Match.objects.create(
            academy=academy, athlete_a=user_a, athlete_b=user_b
        )
        return academy, match, user_a, user_b, _client(prof)

    def test_match_starts_unfinished(self):
        _, match, _, _, _ = self._setup()
        assert match.is_finished is False
        assert match.winner is None

    def test_finish_match_sets_is_finished_true(self):
        academy, match, user_a, _, client = self._setup()
        r = client.post(
            f"/api/v1/matches/{match.pk}/finish_match/?academy={academy.pk}",
            {"winner_id": user_a.pk},
        )
        assert r.status_code == status.HTTP_200_OK
        match.refresh_from_db()
        assert match.is_finished is True
        assert match.winner_id == user_a.pk

    def test_finish_match_response_is_serialized_match(self):
        academy, match, user_a, _, client = self._setup()
        r = client.post(
            f"/api/v1/matches/{match.pk}/finish_match/?academy={academy.pk}",
            {"winner_id": user_a.pk},
        )
        assert r.status_code == status.HTTP_200_OK
        for field in ("id", "is_finished", "score_a", "score_b"):
            assert field in r.data, f"Missing field: {field}"
        assert r.data["is_finished"] is True

    def test_score_starts_at_zero(self):
        academy, match, _, _, client = self._setup()
        r = client.get(f"/api/v1/matches/{match.pk}/?academy={academy.pk}")
        assert r.status_code == status.HTTP_200_OK
        assert r.data["score_a"] == 0
        assert r.data["score_b"] == 0

    def test_add_points_event_increments_score_a(self):
        academy, match, user_a, _, client = self._setup()
        r = client.post(
            f"/api/v1/matches/{match.pk}/add_event/?academy={academy.pk}",
            {
                "athlete": user_a.pk,
                "event_type": "POINTS",
                "timestamp": 30,
                "points_awarded": 4,
                "action_description": "guard pass",
            },
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.data["score_a"] == 4
        assert r.data["score_b"] == 0

    def test_add_submission_event_does_not_change_score(self):
        """SUBMISSION events have no points_awarded but are logged."""
        academy, match, user_a, _, client = self._setup()
        r = client.post(
            f"/api/v1/matches/{match.pk}/add_event/?academy={academy.pk}",
            {
                "athlete": user_a.pk,
                "event_type": "SUBMISSION",
                "timestamp": 90,
                "points_awarded": 0,
                "action_description": "rear naked choke",
            },
        )
        assert r.status_code == status.HTTP_201_CREATED
        match.refresh_from_db()
        assert match.score_a == 0
        assert match.score_b == 0

    def test_sequential_score_events_accumulate(self):
        academy, match, user_a, user_b, client = self._setup()
        events = [
            (user_a, 2, "takedown"),
            (user_b, 4, "guard pass"),
            (user_a, 3, "back take"),
        ]
        for athlete, pts, desc in events:
            r = client.post(
                f"/api/v1/matches/{match.pk}/add_event/?academy={academy.pk}",
                {
                    "athlete": athlete.pk,
                    "event_type": "POINTS",
                    "timestamp": 10,
                    "points_awarded": pts,
                    "action_description": desc,
                },
            )
            assert r.status_code == status.HTTP_201_CREATED

        match.refresh_from_db()
        assert match.score_a == 5   # 2 + 3
        assert match.score_b == 4
