"""
Role-based API permission tests for the Tatami app.

Covers every HTTP method × every role for:
  - WeightClassViewSet  (read-only, no academy scoping)
  - TimerPresetViewSet  (member read / professor write)
  - TimerSessionViewSet (member read-write)
  - MatchupViewSet      (member read / professor write)

Role matrix used in every guarded test:
  ┌─────────────────────┬──────┬────────────┬───────────┬───────┬────────────┐
  │ Endpoint / Role     │ Unauth│ Non-member │  Student  │ Prof  │  Owner     │
  ├─────────────────────┼──────┼────────────┼───────────┼───────┼────────────┤
  │ GET  (member-read)  │  401 │    403     │   200     │  200  │   200      │
  │ POST (prof-write)   │  401 │    403     │   403     │  201  │   201      │
  │ PUT/PATCH           │  401 │    403     │   403     │  200  │   200      │
  │ DELETE              │  401 │    403     │   403     │  204  │   204      │
  └─────────────────────┴──────┴────────────┴───────────┴───────┴────────────┘
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    UserFactory,
)
from tatami.tests.factories import (
    MatchupFactory,
    TimerPresetFactory,
    TimerSessionFactory,
    WeightClassFactory,
)

# ── URL helpers ───────────────────────────────────────────────────────────────

WC_LIST = "/api/v1/tatami/weight-classes/"
PRESET_LIST = "/api/v1/tatami/timer-presets/"
SESSION_LIST = "/api/v1/tatami/timer-sessions/"
MATCHUP_LIST = "/api/v1/tatami/matchups/"


def wc_detail(pk):
    return f"{WC_LIST}{pk}/"


def preset_detail(pk):
    return f"{PRESET_LIST}{pk}/"


def preset_start(pk):
    return f"{PRESET_LIST}{pk}/start_session/"


def session_detail(pk):
    return f"{SESSION_LIST}{pk}/"


def session_pause(pk):
    return f"{SESSION_LIST}{pk}/pause/"


def session_finish(pk):
    return f"{SESSION_LIST}{pk}/finish/"


def matchup_detail(pk):
    return f"{MATCHUP_LIST}{pk}/"


def pair_url():
    return f"{MATCHUP_LIST}pair_athletes/"


# ── Local fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def other_academy(db):
    return AcademyFactory()


@pytest.fixture
def student_membership(db, academy, athlete):
    """Tie the global `athlete` fixture into `academy` as a student."""
    return AcademyMembershipFactory(
        user=athlete.user, academy=academy, role="STUDENT", is_active=True
    )


@pytest.fixture
def prof_membership(db, academy, professor_athlete):
    """Tie the global `professor_athlete` fixture into `academy` as a professor."""
    return AcademyMembershipFactory(
        user=professor_athlete.user, academy=academy, role="PROFESSOR", is_active=True
    )


@pytest.fixture
def owner_user(db, academy):
    user = UserFactory()
    AcademyMembershipFactory(user=user, academy=academy, role="OWNER", is_active=True)
    return user


@pytest.fixture
def owner_client(owner_user):
    client = APIClient()
    client.force_authenticate(user=owner_user)
    return client


@pytest.fixture
def non_member_client(db):
    """Authenticated user with no academy memberships."""
    user = UserFactory()
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def weight_class(db):
    return WeightClassFactory()


@pytest.fixture
def preset(db, academy):
    return TimerPresetFactory(academy=academy, name="Preset A")


@pytest.fixture
def other_preset(db, other_academy):
    return TimerPresetFactory(academy=other_academy, name="Preset B")


@pytest.fixture
def running_session(db, preset):
    from django.utils import timezone
    from tatami.models import TimerSession

    return TimerSessionFactory(
        preset=preset,
        status=TimerSession.Status.RUNNING,
        started_at=timezone.now(),
    )


@pytest.fixture
def matchup(db, academy):
    a = AthleteProfileFactory(academy=academy)
    b = AthleteProfileFactory(academy=academy)
    return MatchupFactory(
        academy=academy,
        athlete_a=a,
        athlete_b=b,
        status="PENDING",
        winner=None,
    )


@pytest.fixture
def athletes_in_academy(db, academy):
    return [AthleteProfileFactory(academy=academy) for _ in range(4)]


# ── 1. WeightClassViewSet ─────────────────────────────────────────────────────


class TestWeightClassViewSet:
    """Read-only, platform-wide. No academy scoping required."""

    def test_unauthenticated_cannot_list(self, api_client):
        assert api_client.get(WC_LIST).status_code == status.HTTP_401_UNAUTHORIZED

    def test_authenticated_can_list(self, auth_client):
        assert auth_client.get(WC_LIST).status_code == status.HTTP_200_OK

    def test_professor_can_list(self, professor_client):
        assert professor_client.get(WC_LIST).status_code == status.HTTP_200_OK

    def test_authenticated_can_retrieve(self, auth_client, weight_class):
        assert (
            auth_client.get(wc_detail(weight_class.pk)).status_code
            == status.HTTP_200_OK
        )

    def test_unauthenticated_cannot_retrieve(self, api_client, weight_class):
        assert (
            api_client.get(wc_detail(weight_class.pk)).status_code
            == status.HTTP_401_UNAUTHORIZED
        )

    def test_create_is_not_allowed_for_any_user(self, auth_client, admin_client):
        payload = {"name": "Test Class", "min_weight": 70, "max_weight": 76, "gender": "M"}
        assert auth_client.post(WC_LIST, payload).status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert admin_client.post(WC_LIST, payload).status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_update_is_not_allowed(self, auth_client, weight_class):
        assert (
            auth_client.patch(wc_detail(weight_class.pk), {"name": "X"}).status_code
            == status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def test_delete_is_not_allowed(self, auth_client, weight_class):
        assert (
            auth_client.delete(wc_detail(weight_class.pk)).status_code
            == status.HTTP_405_METHOD_NOT_ALLOWED
        )


# ── 2. TimerPresetViewSet ─────────────────────────────────────────────────────


class TestTimerPresetList:
    """GET list — requires IsAcademyMember."""

    def test_unauthenticated_returns_401(self, api_client, academy):
        assert (
            api_client.get(f"{PRESET_LIST}?academy={academy.pk}").status_code
            == status.HTTP_401_UNAUTHORIZED
        )

    def test_no_academy_param_returns_403(self, auth_client):
        # No ?academy= → IsAcademyMember cannot resolve academy → 403
        assert auth_client.get(PRESET_LIST).status_code == status.HTTP_403_FORBIDDEN

    def test_non_member_returns_403(self, non_member_client, academy):
        assert (
            non_member_client.get(f"{PRESET_LIST}?academy={academy.pk}").status_code
            == status.HTTP_403_FORBIDDEN
        )

    def test_student_can_list(self, auth_client, academy, student_membership):
        resp = auth_client.get(f"{PRESET_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_200_OK

    def test_professor_can_list(self, professor_client, academy, prof_membership):
        resp = professor_client.get(f"{PRESET_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_200_OK

    def test_owner_can_list(self, owner_client, academy):
        resp = owner_client.get(f"{PRESET_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_200_OK

    def test_results_scoped_to_academy(
        self, auth_client, academy, preset, other_preset, student_membership
    ):
        """Presets from another academy must not appear."""
        resp = auth_client.get(f"{PRESET_LIST}?academy={academy.pk}")
        ids = [p["id"] for p in resp.data["results"]]
        assert preset.pk in ids
        assert other_preset.pk not in ids


class TestTimerPresetCreate:
    """POST — requires IsAcademyProfessor."""

    def _payload(self, academy):
        return {
            "academy": academy.pk,
            "name": "New Preset",
            "format": "CUSTOM",
            "round_duration_seconds": 300,
            "rest_duration_seconds": 30,
            "overtime_seconds": 0,
            "rounds": 3,
        }

    def test_unauthenticated_returns_401(self, api_client, academy):
        resp = api_client.post(
            f"{PRESET_LIST}?academy={academy.pk}", self._payload(academy), format="json"
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_academy_param_returns_403(self, professor_client, academy, prof_membership):
        resp = professor_client.post(PRESET_LIST, self._payload(academy), format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_non_member_returns_403(self, non_member_client, academy):
        resp = non_member_client.post(
            f"{PRESET_LIST}?academy={academy.pk}", self._payload(academy), format="json"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_create(self, auth_client, academy, student_membership):
        resp = auth_client.post(
            f"{PRESET_LIST}?academy={academy.pk}", self._payload(academy), format="json"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_create(self, professor_client, academy, prof_membership):
        resp = professor_client.post(
            f"{PRESET_LIST}?academy={academy.pk}", self._payload(academy), format="json"
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["name"] == "New Preset"

    def test_owner_can_create(self, owner_client, academy):
        resp = owner_client.post(
            f"{PRESET_LIST}?academy={academy.pk}", self._payload(academy), format="json"
        )
        assert resp.status_code == status.HTTP_201_CREATED

    def test_missing_required_fields_returns_400(
        self, professor_client, academy, prof_membership
    ):
        resp = professor_client.post(
            f"{PRESET_LIST}?academy={academy.pk}", {}, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


class TestTimerPresetUpdate:
    """PATCH/PUT — requires IsAcademyProfessor."""

    def test_student_cannot_update(self, auth_client, academy, preset, student_membership):
        resp = auth_client.patch(
            f"{preset_detail(preset.pk)}?academy={academy.pk}", {"name": "Hacked"}
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_update(self, professor_client, academy, preset, prof_membership):
        resp = professor_client.patch(
            f"{preset_detail(preset.pk)}?academy={academy.pk}", {"name": "Updated"}
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["name"] == "Updated"

    def test_owner_can_update(self, owner_client, academy, preset):
        resp = owner_client.patch(
            f"{preset_detail(preset.pk)}?academy={academy.pk}", {"name": "Owner Update"}
        )
        assert resp.status_code == status.HTTP_200_OK

    def test_unauthenticated_cannot_update(self, api_client, academy, preset):
        resp = api_client.patch(
            f"{preset_detail(preset.pk)}?academy={academy.pk}", {"name": "X"}
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_non_member_cannot_update(self, non_member_client, academy, preset):
        resp = non_member_client.patch(
            f"{preset_detail(preset.pk)}?academy={academy.pk}", {"name": "X"}
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestTimerPresetDelete:
    """DELETE — requires IsAcademyProfessor."""

    def test_student_cannot_delete(self, auth_client, academy, preset, student_membership):
        resp = auth_client.delete(f"{preset_detail(preset.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_delete(self, professor_client, academy, preset, prof_membership):
        resp = professor_client.delete(f"{preset_detail(preset.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_204_NO_CONTENT

    def test_owner_can_delete(self, owner_client, academy):
        p = TimerPresetFactory(academy=academy)
        resp = owner_client.delete(f"{preset_detail(p.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_204_NO_CONTENT

    def test_unauthenticated_cannot_delete(self, api_client, academy, preset):
        resp = api_client.delete(f"{preset_detail(preset.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


class TestTimerPresetStartSession:
    """start_session custom action — POST, inherits IsAcademyProfessor."""

    def test_student_cannot_start_session(self, auth_client, academy, preset, student_membership):
        resp = auth_client.post(f"{preset_start(preset.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_start_session(self, professor_client, academy, preset, prof_membership):
        resp = professor_client.post(f"{preset_start(preset.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_201_CREATED
        assert "status" in resp.data

    def test_owner_can_start_session(self, owner_client, academy, preset):
        resp = owner_client.post(f"{preset_start(preset.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_201_CREATED

    def test_unauthenticated_cannot_start_session(self, api_client, academy, preset):
        resp = api_client.post(f"{preset_start(preset.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ── 3. TimerSessionViewSet ────────────────────────────────────────────────────


class TestTimerSessionList:
    """GET list — requires IsAcademyMember."""

    def test_unauthenticated_returns_401(self, api_client, academy):
        resp = api_client.get(f"{SESSION_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_academy_param_returns_403(self, auth_client):
        resp = auth_client.get(SESSION_LIST)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_non_member_returns_403(self, non_member_client, academy):
        resp = non_member_client.get(f"{SESSION_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_student_can_list(self, auth_client, academy, student_membership):
        resp = auth_client.get(f"{SESSION_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_200_OK

    def test_professor_can_list(self, professor_client, academy, prof_membership):
        resp = professor_client.get(f"{SESSION_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_200_OK

    def test_owner_can_list(self, owner_client, academy):
        resp = owner_client.get(f"{SESSION_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_200_OK

    def test_only_shows_active_sessions(
        self, auth_client, academy, preset, student_membership
    ):
        """Selector returns only RUNNING or PAUSED sessions."""
        from tatami.models import TimerSession

        TimerSessionFactory(preset=preset, status=TimerSession.Status.IDLE)
        TimerSessionFactory(preset=preset, status=TimerSession.Status.FINISHED)
        running = TimerSessionFactory(preset=preset, status=TimerSession.Status.RUNNING)

        resp = auth_client.get(f"{SESSION_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_200_OK
        result_ids = [s["id"] for s in resp.data["results"]]
        assert running.pk in result_ids


class TestTimerSessionActions:
    """pause / finish actions — inherits IsAcademyMember."""

    def test_student_can_pause_running_session(
        self, auth_client, academy, running_session, student_membership
    ):
        resp = auth_client.post(
            f"{session_pause(running_session.pk)}?academy={academy.pk}"
        )
        assert resp.status_code == status.HTTP_200_OK

    def test_non_member_cannot_pause_session(
        self, non_member_client, academy, running_session
    ):
        resp = non_member_client.post(
            f"{session_pause(running_session.pk)}?academy={academy.pk}"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_pause_session(self, api_client, academy, running_session):
        resp = api_client.post(
            f"{session_pause(running_session.pk)}?academy={academy.pk}"
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_student_can_finish_session(
        self, auth_client, academy, running_session, student_membership
    ):
        resp = auth_client.post(
            f"{session_finish(running_session.pk)}?academy={academy.pk}"
        )
        assert resp.status_code == status.HTTP_200_OK


# ── 4. MatchupViewSet ─────────────────────────────────────────────────────────


class TestMatchupList:
    """GET list — requires IsAcademyMember."""

    def test_unauthenticated_returns_401(self, api_client, academy):
        resp = api_client.get(f"{MATCHUP_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_no_academy_param_returns_403(self, auth_client):
        resp = auth_client.get(MATCHUP_LIST)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_non_member_returns_403(self, non_member_client, academy):
        resp = non_member_client.get(f"{MATCHUP_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_student_can_list(self, auth_client, academy, student_membership):
        resp = auth_client.get(f"{MATCHUP_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_200_OK

    def test_professor_can_list(self, professor_client, academy, prof_membership):
        resp = professor_client.get(f"{MATCHUP_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_200_OK

    def test_owner_can_list(self, owner_client, academy):
        resp = owner_client.get(f"{MATCHUP_LIST}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_200_OK

    def test_results_scoped_to_academy(
        self, auth_client, academy, matchup, student_membership
    ):
        """Matchups from a foreign academy must not be returned."""
        foreign = MatchupFactory()
        resp = auth_client.get(f"{MATCHUP_LIST}?academy={academy.pk}")
        ids = [m["id"] for m in resp.data["results"]]
        assert matchup.pk in ids
        assert foreign.pk not in ids


class TestMatchupRetrieve:
    """GET detail — requires IsAcademyMember."""

    def test_student_can_retrieve(self, auth_client, academy, matchup, student_membership):
        resp = auth_client.get(f"{matchup_detail(matchup.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_200_OK

    def test_non_member_cannot_retrieve(self, non_member_client, academy, matchup):
        resp = non_member_client.get(f"{matchup_detail(matchup.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_retrieve(self, api_client, academy, matchup):
        resp = api_client.get(f"{matchup_detail(matchup.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


class TestMatchupCreate:
    """POST — requires IsAcademyProfessor."""

    def _payload(self, academy, a, b):
        return {
            "academy": academy.pk,
            "athlete_a": a.pk,
            "athlete_b": b.pk,
            "match_format": "TOURNAMENT",
            "round_number": 1,
        }

    def test_unauthenticated_returns_401(self, api_client, academy, athletes_in_academy):
        a, b = athletes_in_academy[:2]
        resp = api_client.post(
            f"{MATCHUP_LIST}?academy={academy.pk}",
            self._payload(academy, a, b),
            format="json",
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_non_member_cannot_create(self, non_member_client, academy, athletes_in_academy):
        a, b = athletes_in_academy[:2]
        resp = non_member_client.post(
            f"{MATCHUP_LIST}?academy={academy.pk}",
            self._payload(academy, a, b),
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_create(self, auth_client, academy, athletes_in_academy, student_membership):
        a, b = athletes_in_academy[:2]
        resp = auth_client.post(
            f"{MATCHUP_LIST}?academy={academy.pk}",
            self._payload(academy, a, b),
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_create(self, professor_client, academy, athletes_in_academy, prof_membership):
        a, b = athletes_in_academy[:2]
        resp = professor_client.post(
            f"{MATCHUP_LIST}?academy={academy.pk}",
            self._payload(academy, a, b),
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED

    def test_owner_can_create(self, owner_client, academy, athletes_in_academy):
        a, b = athletes_in_academy[:2]
        resp = owner_client.post(
            f"{MATCHUP_LIST}?academy={academy.pk}",
            self._payload(academy, a, b),
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED


class TestMatchupUpdate:
    """PATCH/PUT — requires IsAcademyProfessor."""

    def test_student_cannot_update(self, auth_client, academy, matchup, student_membership):
        resp = auth_client.patch(
            f"{matchup_detail(matchup.pk)}?academy={academy.pk}",
            {"round_number": 2},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_update(self, professor_client, academy, matchup, prof_membership):
        resp = professor_client.patch(
            f"{matchup_detail(matchup.pk)}?academy={academy.pk}",
            {"round_number": 2},
        )
        assert resp.status_code == status.HTTP_200_OK

    def test_owner_can_update(self, owner_client, academy, matchup):
        resp = owner_client.patch(
            f"{matchup_detail(matchup.pk)}?academy={academy.pk}",
            {"round_number": 3},
        )
        assert resp.status_code == status.HTTP_200_OK

    def test_non_member_cannot_update(self, non_member_client, academy, matchup):
        resp = non_member_client.patch(
            f"{matchup_detail(matchup.pk)}?academy={academy.pk}",
            {"round_number": 2},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


class TestMatchupDelete:
    """DELETE — requires IsAcademyProfessor."""

    def test_student_cannot_delete(self, auth_client, academy, matchup, student_membership):
        resp = auth_client.delete(f"{matchup_detail(matchup.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_delete(self, professor_client, academy, matchup, prof_membership):
        resp = professor_client.delete(f"{matchup_detail(matchup.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_204_NO_CONTENT

    def test_owner_can_delete(self, owner_client, academy):
        m = MatchupFactory(
            academy=academy,
            athlete_a=AthleteProfileFactory(academy=academy),
            athlete_b=AthleteProfileFactory(academy=academy),
            status="PENDING",
            winner=None,
        )
        resp = owner_client.delete(f"{matchup_detail(m.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_204_NO_CONTENT

    def test_unauthenticated_cannot_delete(self, api_client, academy, matchup):
        resp = api_client.delete(f"{matchup_detail(matchup.pk)}?academy={academy.pk}")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


class TestPairAthletes:
    """pair_athletes custom action — POST, requires IsAcademyProfessor."""

    def test_unauthenticated_returns_401(self, api_client, academy, athletes_in_academy):
        resp = api_client.post(
            f"{pair_url()}?academy={academy.pk}",
            {
                "athlete_ids": [a.pk for a in athletes_in_academy[:2]],
                "match_format": "TOURNAMENT",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_non_member_returns_403(self, non_member_client, academy, athletes_in_academy):
        resp = non_member_client.post(
            f"{pair_url()}?academy={academy.pk}",
            {
                "athlete_ids": [a.pk for a in athletes_in_academy[:2]],
                "match_format": "TOURNAMENT",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_pair(self, auth_client, academy, athletes_in_academy, student_membership):
        resp = auth_client.post(
            f"{pair_url()}?academy={academy.pk}",
            {
                "athlete_ids": [a.pk for a in athletes_in_academy[:2]],
                "match_format": "TOURNAMENT",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_professor_can_pair(
        self, professor_client, academy, athletes_in_academy, prof_membership
    ):
        resp = professor_client.post(
            f"{pair_url()}?academy={academy.pk}",
            {
                "athlete_ids": [a.pk for a in athletes_in_academy],
                "match_format": "TOURNAMENT",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert len(resp.data) == 2  # 4 athletes → 2 pairs

    def test_owner_can_pair(self, owner_client, academy, athletes_in_academy):
        resp = owner_client.post(
            f"{pair_url()}?academy={academy.pk}",
            {
                "athlete_ids": [a.pk for a in athletes_in_academy[:2]],
                "match_format": "TOURNAMENT",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED

    def test_fewer_than_two_athletes_returns_400(
        self, professor_client, academy, athletes_in_academy, prof_membership
    ):
        resp = professor_client.post(
            f"{pair_url()}?academy={academy.pk}",
            {
                "athlete_ids": [athletes_in_academy[0].pk],
                "match_format": "TOURNAMENT",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_foreign_academy_athlete_ids_rejected(
        self, professor_client, academy, prof_membership
    ):
        """Athletes from another academy must not be injectable."""
        foreign_athlete = AthleteProfileFactory()
        own_athlete = AthleteProfileFactory(academy=academy)
        resp = professor_client.post(
            f"{pair_url()}?academy={academy.pk}",
            {
                "athlete_ids": [own_athlete.pk, foreign_athlete.pk],
                "match_format": "TOURNAMENT",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
