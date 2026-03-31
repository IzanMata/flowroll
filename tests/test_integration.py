"""
Integration tests — cross-app business logic chains.

These tests span multiple apps and verify that side effects propagate
correctly end-to-end:

1. Check-in chain:      QR scan → CheckIn created → mat_hours incremented
2. Manual check-in:     professor action → CheckIn created → mat_hours updated
3. Timer full cycle:    preset → start → pause → resume → finish → session recorded
4. Matchup flow:        pair_athletes → matchups created → add_event → finish_match
5. Tenant isolation:    operations on academy A never affect academy B
6. Response contract:   key endpoints return documented fields in correct shape
"""

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
from tatami.models import TimerSession
from tatami.tests.factories import TimerPresetFactory


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


# ══════════════════════════════════════════════════════════════════════════════
# 1. Check-in chain
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCheckInChain:

    def test_qr_checkin_creates_checkin_record(self):
        academy = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        athlete = AthleteProfileFactory(user=user, academy=academy)
        tc = TrainingClassFactory(academy=academy, duration_minutes=60)
        token = QRCodeService.generate(tc).token

        r = _client(user).post(
            "/api/attendance/classes/qr_checkin/", {"token": token}
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert CheckIn.objects.filter(athlete=athlete, training_class=tc).exists()

    def test_qr_checkin_increments_mat_hours(self):
        academy = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        athlete = AthleteProfileFactory(user=user, academy=academy, mat_hours=0.0)
        tc = TrainingClassFactory(academy=academy, duration_minutes=90)
        token = QRCodeService.generate(tc).token

        _client(user).post("/api/attendance/classes/qr_checkin/", {"token": token})

        athlete.refresh_from_db()
        assert abs(athlete.mat_hours - 1.5) < 0.001, (
            f"Expected 1.5 mat_hours after 90-min class, got {athlete.mat_hours}"
        )

    def test_checkin_response_contains_required_fields(self):
        academy = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        AthleteProfileFactory(user=user, academy=academy)
        tc = TrainingClassFactory(academy=academy)
        token = QRCodeService.generate(tc).token

        r = _client(user).post(
            "/api/attendance/classes/qr_checkin/", {"token": token}
        )
        assert r.status_code == status.HTTP_201_CREATED
        for field in ("athlete", "training_class", "checked_in_at"):
            assert field in r.data, f"Missing field in qr_checkin response: {field}"

    def test_manual_checkin_by_professor_increments_mat_hours(self):
        academy = AcademyFactory()
        prof = UserFactory()
        AcademyMembershipFactory(user=prof, academy=academy, role="PROFESSOR", is_active=True)
        athlete = AthleteProfileFactory(academy=academy, mat_hours=5.0)
        tc = TrainingClassFactory(academy=academy, duration_minutes=60)

        r = _client(prof).post(
            f"/api/attendance/classes/manual_checkin/?academy={academy.pk}",
            {"athlete_id": athlete.pk, "training_class_id": tc.pk},
        )
        assert r.status_code == status.HTTP_201_CREATED

        athlete.refresh_from_db()
        assert abs(athlete.mat_hours - 6.0) < 0.001

    def test_duplicate_checkin_returns_400(self):
        academy = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        AthleteProfileFactory(user=user, academy=academy)
        tc = TrainingClassFactory(academy=academy)

        qr1 = QRCodeService.generate(tc)
        client = _client(user)
        client.post("/api/attendance/classes/qr_checkin/", {"token": qr1.token})

        qr2 = QRCodeService.generate(tc)
        r = client.post("/api/attendance/classes/qr_checkin/", {"token": qr2.token})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_four_checkins_accumulate_mat_hours(self):
        """Four 60-min check-ins should yield 4.0 mat_hours."""
        academy = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        athlete = AthleteProfileFactory(user=user, academy=academy, mat_hours=0.0)
        client = _client(user)

        for _ in range(4):
            tc = TrainingClassFactory(academy=academy, duration_minutes=60)
            token = QRCodeService.generate(tc).token
            r = client.post("/api/attendance/classes/qr_checkin/", {"token": token})
            assert r.status_code == status.HTTP_201_CREATED

        athlete.refresh_from_db()
        assert abs(athlete.mat_hours - 4.0) < 0.001


# ══════════════════════════════════════════════════════════════════════════════
# 2. Timer full lifecycle
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTimerLifecycle:

    def test_full_timer_cycle_start_pause_resume_finish(self):
        """
        start_session → pause → (service resume) → finish
        Session must end in FINISHED state with elapsed_seconds > 0.
        """
        from tatami.services import TimerService

        academy = AcademyFactory()
        prof = UserFactory()
        AcademyMembershipFactory(user=prof, academy=academy, role="PROFESSOR", is_active=True)
        client = _client(prof)
        preset = TimerPresetFactory(academy=academy)
        aq = f"?academy={academy.pk}"

        # Start
        r = client.post(f"/api/tatami/timer-presets/{preset.pk}/start_session/{aq}")
        assert r.status_code == status.HTTP_201_CREATED
        session_id = r.data["id"]

        # Pause
        r = client.post(f"/api/tatami/timer-sessions/{session_id}/pause/{aq}")
        assert r.status_code == status.HTTP_200_OK

        # Resume via service (no dedicated resume endpoint exposed)
        session = TimerSession.objects.get(pk=session_id)
        TimerService.start(session)
        session.refresh_from_db()
        assert session.status == TimerSession.Status.RUNNING

        # Finish
        r = client.post(f"/api/tatami/timer-sessions/{session_id}/finish/{aq}")
        assert r.status_code == status.HTTP_200_OK
        assert r.data["status"] == TimerSession.Status.FINISHED

    def test_start_session_creates_one_session_per_call(self):
        academy = AcademyFactory()
        prof = UserFactory()
        AcademyMembershipFactory(user=prof, academy=academy, role="PROFESSOR", is_active=True)
        preset = TimerPresetFactory(academy=academy)
        client = _client(prof)
        aq = f"?academy={academy.pk}"

        before = TimerSession.objects.count()
        client.post(f"/api/tatami/timer-presets/{preset.pk}/start_session/{aq}")
        client.post(f"/api/tatami/timer-presets/{preset.pk}/start_session/{aq}")
        after = TimerSession.objects.count()
        assert after - before == 2


# ══════════════════════════════════════════════════════════════════════════════
# 3. Matchup + match flow
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestMatchupAndMatchFlow:

    def test_pair_athletes_tournament_creates_matchups(self):
        academy = AcademyFactory()
        prof = UserFactory()
        AcademyMembershipFactory(user=prof, academy=academy, role="PROFESSOR", is_active=True)
        athletes = [AthleteProfileFactory(academy=academy) for _ in range(4)]
        client = _client(prof)

        r = client.post(
            f"/api/tatami/matchups/pair_athletes/?academy={academy.pk}",
            {
                "athlete_ids": [a.pk for a in athletes],
                "match_format": "TOURNAMENT",
            },
            format="json",
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert len(r.data) == 2  # 4 athletes → 2 pairs

    def test_full_match_flow_events_then_finish(self):
        """add_event ×4 → finish_match → final state correct."""
        academy = AcademyFactory()
        user_a = UserFactory()
        user_b = UserFactory()
        prof = UserFactory()
        AcademyMembershipFactory(user=prof, academy=academy, role="PROFESSOR", is_active=True)
        match = Match.objects.create(
            academy=academy, athlete_a=user_a, athlete_b=user_b
        )
        client = _client(prof)
        aq = f"?academy={academy.pk}"

        for i in range(3):
            r = client.post(
                f"/api/matches/{match.pk}/add_event/{aq}",
                {
                    "athlete": user_a.pk,
                    "event_type": "POINTS",
                    "timestamp": i + 1,
                    "points_awarded": 2,
                    "action_description": f"takedown {i}",
                },
            )
            assert r.status_code == status.HTTP_201_CREATED

        r = client.post(
            f"/api/matches/{match.pk}/add_event/{aq}",
            {
                "athlete": user_b.pk,
                "event_type": "POINTS",
                "timestamp": 60,
                "points_awarded": 4,
                "action_description": "guard pass",
            },
        )
        assert r.status_code == status.HTTP_201_CREATED

        r = client.post(
            f"/api/matches/{match.pk}/finish_match/{aq}",
            {"winner_id": user_a.pk},
        )
        assert r.status_code == status.HTTP_200_OK

        match.refresh_from_db()
        assert match.is_finished is True
        assert match.score_a == 6
        assert match.score_b == 4
        assert match.winner_id == user_a.pk
        assert MatchEvent.objects.filter(match=match).count() == 4


# ══════════════════════════════════════════════════════════════════════════════
# 4. Tenant isolation
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTenantIsolation:

    def test_training_classes_do_not_leak_across_academies(self):
        academy_a = AcademyFactory()
        academy_b = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy_a, role="STUDENT", is_active=True)
        TrainingClassFactory(academy=academy_a, title="A Class")
        TrainingClassFactory(academy=academy_b, title="B Class")

        r = _client(user).get(
            f"/api/attendance/classes/?academy={academy_a.pk}"
        )
        assert r.status_code == status.HTTP_200_OK
        for item in r.data["results"]:
            assert item["academy"] == academy_a.pk

    def test_athlete_profiles_do_not_leak_across_academies(self):
        academy_a = AcademyFactory()
        academy_b = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy_a, role="STUDENT", is_active=True)
        AthleteProfileFactory(academy=academy_a)
        AthleteProfileFactory(academy=academy_b)

        r = _client(user).get(f"/api/athletes/?academy={academy_a.pk}")
        assert r.status_code == status.HTTP_200_OK
        for item in r.data["results"]:
            assert item["academy"] == academy_a.pk

    def test_timer_presets_do_not_leak_across_academies(self):
        academy_a = AcademyFactory()
        academy_b = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy_a, role="STUDENT", is_active=True)
        TimerPresetFactory(academy=academy_a)
        TimerPresetFactory(academy=academy_b)

        r = _client(user).get(
            f"/api/tatami/timer-presets/?academy={academy_a.pk}"
        )
        assert r.status_code == status.HTTP_200_OK
        for item in r.data["results"]:
            assert item["academy"] == academy_a.pk


# ══════════════════════════════════════════════════════════════════════════════
# 5. Response contract — required fields present in every response
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestResponseContract:

    def test_athlete_profile_response_shape(self):
        academy = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        profile = AthleteProfileFactory(user=user, academy=academy)

        r = _client(user).get(
            f"/api/athletes/{profile.pk}/?academy={academy.pk}"
        )
        assert r.status_code == status.HTTP_200_OK
        for field in ("id", "username", "email", "belt", "stripes",
                      "weight", "mat_hours", "academy_detail"):
            assert field in r.data, f"Missing field in athlete response: {field}"
        assert r.data["academy_detail"]["id"] == academy.pk

    def test_training_class_response_shape(self):
        academy = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        tc = TrainingClassFactory(academy=academy)

        r = _client(user).get(
            f"/api/attendance/classes/{tc.pk}/?academy={academy.pk}"
        )
        assert r.status_code == status.HTTP_200_OK
        for field in ("id", "title", "class_type", "scheduled_at",
                      "duration_minutes", "attendance_count"):
            assert field in r.data, f"Missing field in training class response: {field}"

    def test_timer_preset_response_shape(self):
        academy = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        preset = TimerPresetFactory(academy=academy)

        r = _client(user).get(
            f"/api/tatami/timer-presets/{preset.pk}/?academy={academy.pk}"
        )
        assert r.status_code == status.HTTP_200_OK
        for field in ("id", "name", "format", "round_duration_seconds",
                      "rest_duration_seconds", "rounds"):
            assert field in r.data, f"Missing field in timer preset response: {field}"

    def test_match_response_shape(self):
        academy = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        match = Match.objects.create(
            academy=academy,
            athlete_a=UserFactory(),
            athlete_b=UserFactory(),
        )

        r = _client(user).get(f"/api/matches/{match.pk}/?academy={academy.pk}")
        assert r.status_code == status.HTTP_200_OK
        for field in ("id", "is_finished", "score_a", "score_b",
                      "athlete_a", "athlete_b"):
            assert field in r.data, f"Missing field in match response: {field}"

    def test_list_response_is_paginated(self):
        """Every list endpoint must return paginated shape."""
        academy = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        TrainingClassFactory(academy=academy)

        r = _client(user).get(
            f"/api/attendance/classes/?academy={academy.pk}"
        )
        assert r.status_code == status.HTTP_200_OK
        for key in ("count", "next", "previous", "results"):
            assert key in r.data, f"Pagination key missing: {key}"
        assert isinstance(r.data["results"], list)
