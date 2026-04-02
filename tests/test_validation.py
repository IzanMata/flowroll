"""
Input validation tests — every writable endpoint must reject bad data with 400.

Tests cover:
- Missing required fields
- Invalid choice values
- Out-of-range numeric fields (validators)
- Wrong data types
- Business-rule violations on write
"""

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    TrainingClassFactory,
    UserFactory,
)
from matches.models import Match
from tatami.tests.factories import TimerPresetFactory


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _professor_setup():
    """Return (academy, prof_user, prof_client)."""
    academy = AcademyFactory()
    prof = UserFactory()
    AcademyMembershipFactory(user=prof, academy=academy, role="PROFESSOR", is_active=True)
    return academy, prof, _client(prof)


# ══════════════════════════════════════════════════════════════════════════════
# AthleteProfile — stripes / weight validators
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAthleteProfileValidation:
    """stripes ∈ [0, 4]; weight ≥ 0.1 when provided."""

    def _own_client_and_profile(self, stripes=0):
        academy = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        profile = AthleteProfileFactory(user=user, academy=academy, stripes=stripes)
        return _client(user), profile, academy

    # stripes boundaries
    def test_stripes_above_maximum_returns_400(self):
        client, profile, academy = self._own_client_and_profile()
        r = client.patch(
            f"/api/v1/athletes/{profile.pk}/?academy={academy.pk}",
            {"stripes": 5},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_stripes_negative_returns_400(self):
        client, profile, academy = self._own_client_and_profile()
        r = client.patch(
            f"/api/v1/athletes/{profile.pk}/?academy={academy.pk}",
            {"stripes": -1},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_stripes_at_maximum_accepted(self):
        client, profile, academy = self._own_client_and_profile()
        r = client.patch(
            f"/api/v1/athletes/{profile.pk}/?academy={academy.pk}",
            {"stripes": 4},
        )
        assert r.status_code == status.HTTP_200_OK

    def test_stripes_at_zero_accepted(self):
        client, profile, academy = self._own_client_and_profile(stripes=2)
        r = client.patch(
            f"/api/v1/athletes/{profile.pk}/?academy={academy.pk}",
            {"stripes": 0},
        )
        assert r.status_code == status.HTTP_200_OK

    # weight boundaries
    def test_weight_below_minimum_returns_400(self):
        client, profile, academy = self._own_client_and_profile()
        r = client.patch(
            f"/api/v1/athletes/{profile.pk}/?academy={academy.pk}",
            {"weight": 0.05},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_weight_zero_returns_400(self):
        client, profile, academy = self._own_client_and_profile()
        r = client.patch(
            f"/api/v1/athletes/{profile.pk}/?academy={academy.pk}",
            {"weight": 0},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_weight_negative_returns_400(self):
        client, profile, academy = self._own_client_and_profile()
        r = client.patch(
            f"/api/v1/athletes/{profile.pk}/?academy={academy.pk}",
            {"weight": -10.0},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_weight_minimum_valid_accepted(self):
        client, profile, academy = self._own_client_and_profile()
        r = client.patch(
            f"/api/v1/athletes/{profile.pk}/?academy={academy.pk}",
            {"weight": 0.1},
        )
        assert r.status_code == status.HTTP_200_OK

    def test_weight_null_accepted_when_optional(self):
        """weight is nullable; explicit null should be accepted."""
        client, profile, academy = self._own_client_and_profile()
        r = client.patch(
            f"/api/v1/athletes/{profile.pk}/?academy={academy.pk}",
            {"weight": None},
            format="json",
        )
        assert r.status_code == status.HTTP_200_OK
        profile.refresh_from_db()
        assert profile.weight is None

    def test_non_numeric_stripes_returns_400(self):
        client, profile, academy = self._own_client_and_profile()
        r = client.patch(
            f"/api/v1/athletes/{profile.pk}/?academy={academy.pk}",
            {"stripes": "many"},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_belt_choice_returns_400(self):
        client, profile, academy = self._own_client_and_profile()
        r = client.patch(
            f"/api/v1/athletes/{profile.pk}/?academy={academy.pk}",
            {"belt": "rainbow"},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ══════════════════════════════════════════════════════════════════════════════
# TrainingClass — required fields and invalid choices
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTrainingClassValidation:

    def test_missing_title_returns_400(self):
        academy, prof, client = _professor_setup()
        r = client.post(
            f"/api/v1/attendance/classes/?academy={academy.pk}",
            {
                "academy": academy.pk,
                "class_type": "GI",
                "scheduled_at": timezone.now().isoformat(),
                "duration_minutes": 60,
            },
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert "title" in r.data

    def test_missing_class_type_uses_default_gi(self):
        """class_type defaults to GI when omitted — not a required field."""
        academy, prof, client = _professor_setup()
        r = client.post(
            f"/api/v1/attendance/classes/?academy={academy.pk}",
            {
                "academy": academy.pk,
                "title": "Evening Class",
                "scheduled_at": timezone.now().isoformat(),
                "duration_minutes": 60,
            },
            format="json",
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.data["class_type"] == "GI"

    def test_invalid_class_type_choice_returns_400(self):
        academy, prof, client = _professor_setup()
        r = client.post(
            f"/api/v1/attendance/classes/?academy={academy.pk}",
            {
                "academy": academy.pk,
                "title": "Weird Class",
                "class_type": "WRESTLING",        # not a valid choice
                "scheduled_at": timezone.now().isoformat(),
                "duration_minutes": 60,
            },
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert "class_type" in r.data

    def test_zero_duration_minutes_returns_400(self):
        academy, prof, client = _professor_setup()
        r = client.post(
            f"/api/v1/attendance/classes/?academy={academy.pk}",
            {
                "academy": academy.pk,
                "title": "Zero-duration",
                "class_type": "GI",
                "scheduled_at": timezone.now().isoformat(),
                "duration_minutes": 0,
            },
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_negative_duration_returns_400(self):
        academy, prof, client = _professor_setup()
        r = client.post(
            f"/api/v1/attendance/classes/?academy={academy.pk}",
            {
                "academy": academy.pk,
                "title": "Negative time",
                "class_type": "GI",
                "scheduled_at": timezone.now().isoformat(),
                "duration_minutes": -30,
            },
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_malformed_scheduled_at_returns_400(self):
        academy, prof, client = _professor_setup()
        r = client.post(
            f"/api/v1/attendance/classes/?academy={academy.pk}",
            {
                "academy": academy.pk,
                "title": "Bad Date",
                "class_type": "GI",
                "scheduled_at": "not-a-date",
                "duration_minutes": 60,
            },
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert "scheduled_at" in r.data

    def test_valid_all_class_types_accepted(self):
        """All three valid class_type choices must be accepted."""
        academy, prof, client = _professor_setup()
        for ct in ("GI", "NOGI", "OPEN_MAT"):
            r = client.post(
                f"/api/v1/attendance/classes/?academy={academy.pk}",
                {
                    "academy": academy.pk,
                    "title": f"{ct} class",
                    "class_type": ct,
                    "scheduled_at": timezone.now().isoformat(),
                    "duration_minutes": 60,
                },
                format="json",
            )
            assert r.status_code == status.HTTP_201_CREATED, (
                f"class_type={ct!r} was rejected: {r.data}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# Match — add_event and finish_match input validation
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestMatchEventValidation:

    def _match(self):
        academy = AcademyFactory()
        user_a = UserFactory()
        user_b = UserFactory()
        prof = UserFactory()
        AcademyMembershipFactory(user=prof, academy=academy, role="PROFESSOR", is_active=True)
        match = Match.objects.create(
            academy=academy, athlete_a=user_a, athlete_b=user_b
        )
        return academy, match, user_a, user_b, _client(prof)

    def test_add_event_missing_athlete_returns_400(self):
        academy, match, user_a, _, client = self._match()
        r = client.post(
            f"/api/v1/matches/{match.pk}/add_event/?academy={academy.pk}",
            {
                "event_type": "POINTS",
                "timestamp": 30,
                "points_awarded": 2,
                "action_description": "takedown",
            },
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_add_event_invalid_event_type_returns_400(self):
        academy, match, user_a, _, client = self._match()
        r = client.post(
            f"/api/v1/matches/{match.pk}/add_event/?academy={academy.pk}",
            {
                "athlete": user_a.pk,
                "event_type": "GOAL",          # not a valid choice
                "timestamp": 30,
                "points_awarded": 2,
                "action_description": "something",
            },
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_add_event_non_participant_returns_400(self):
        academy, match, _, _, client = self._match()
        outsider = UserFactory()
        r = client.post(
            f"/api/v1/matches/{match.pk}/add_event/?academy={academy.pk}",
            {
                "athlete": outsider.pk,
                "event_type": "POINTS",
                "timestamp": 30,
                "points_awarded": 2,
                "action_description": "cheating",
            },
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_finish_match_missing_winner_returns_400(self):
        academy, match, _, _, client = self._match()
        r = client.post(
            f"/api/v1/matches/{match.pk}/finish_match/?academy={academy.pk}",
            {},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert "winner_id" in str(r.data).lower()

    def test_finish_match_non_participant_winner_returns_400(self):
        academy, match, _, _, client = self._match()
        r = client.post(
            f"/api/v1/matches/{match.pk}/finish_match/?academy={academy.pk}",
            {"winner_id": 99999},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_finish_match_string_winner_id_returns_400(self):
        academy, match, _, _, client = self._match()
        r = client.post(
            f"/api/v1/matches/{match.pk}/finish_match/?academy={academy.pk}",
            {"winner_id": "notanint"},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ══════════════════════════════════════════════════════════════════════════════
# TimerPreset — invalid format choice
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTimerPresetValidation:

    def test_invalid_format_choice_returns_400(self):
        academy, prof, client = _professor_setup()
        r = client.post(
            f"/api/v1/tatami/timer-presets/?academy={academy.pk}",
            {
                "academy": academy.pk,
                "name": "Bad Preset",
                "format": "WRESTLING",           # not a valid choice
                "round_duration_seconds": 300,
                "rest_duration_seconds": 30,
                "rounds": 1,
            },
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_name_returns_400(self):
        academy, prof, client = _professor_setup()
        r = client.post(
            f"/api/v1/tatami/timer-presets/?academy={academy.pk}",
            {
                "academy": academy.pk,
                "format": "IBJJF",
                "round_duration_seconds": 300,
                "rest_duration_seconds": 30,
                "rounds": 1,
            },
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert "name" in r.data

    def test_valid_all_formats_accepted(self):
        academy, prof, client = _professor_setup()
        for fmt in ("IBJJF", "ADCC", "POSITIONAL", "CUSTOM"):
            r = client.post(
                f"/api/v1/tatami/timer-presets/?academy={academy.pk}",
                {
                    "academy": academy.pk,
                    "name": f"{fmt} preset",
                    "format": fmt,
                    "round_duration_seconds": 300,
                    "rest_duration_seconds": 30,
                    "rounds": 1,
                },
                format="json",
            )
            assert r.status_code == status.HTTP_201_CREATED, (
                f"format={fmt!r} rejected: {r.data}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# pair_athletes — validation on athlete list and format
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPairAthletesValidation:

    def test_single_athlete_returns_400(self):
        """pair_athletes requires at least 2 athletes."""
        academy, prof, client = _professor_setup()
        athlete = AthleteProfileFactory(academy=academy)
        r = client.post(
            f"/api/v1/tatami/matchups/pair_athletes/?academy={academy.pk}",
            {
                "athlete_ids": [athlete.pk],
                "match_format": "TOURNAMENT",
            },
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_empty_athlete_list_returns_400(self):
        academy, prof, client = _professor_setup()
        r = client.post(
            f"/api/v1/tatami/matchups/pair_athletes/?academy={academy.pk}",
            {"athlete_ids": [], "match_format": "TOURNAMENT"},
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_match_format_returns_400(self):
        academy, prof, client = _professor_setup()
        athletes = [AthleteProfileFactory(academy=academy) for _ in range(2)]
        r = client.post(
            f"/api/v1/tatami/matchups/pair_athletes/?academy={academy.pk}",
            {
                "athlete_ids": [a.pk for a in athletes],
                "match_format": "ROUND_ROBIN",   # not a valid choice
            },
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_foreign_academy_athletes_returns_400(self):
        """Athletes from a different academy are silently excluded → count mismatch → 400."""
        academy, prof, client = _professor_setup()
        other_academy = AcademyFactory()
        foreign_athlete = AthleteProfileFactory(academy=other_academy)
        local_athlete = AthleteProfileFactory(academy=academy)
        r = client.post(
            f"/api/v1/tatami/matchups/pair_athletes/?academy={academy.pk}",
            {
                "athlete_ids": [local_athlete.pk, foreign_athlete.pk],
                "match_format": "TOURNAMENT",
            },
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST


# ══════════════════════════════════════════════════════════════════════════════
# QR check-in — invalid and expired tokens
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestQRCheckInValidation:

    def test_empty_token_returns_400(self):
        academy = AcademyFactory()
        user = UserFactory()
        AcademyMembershipFactory(user=user, academy=academy, role="STUDENT", is_active=True)
        AthleteProfileFactory(user=user, academy=academy)
        client = _client(user)
        r = client.post("/api/v1/attendance/classes/qr_checkin/", {"token": ""})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_token_returns_400(self):
        academy = AcademyFactory()
        user = UserFactory()
        AthleteProfileFactory(user=user, academy=academy)
        client = _client(user)
        r = client.post("/api/v1/attendance/classes/qr_checkin/", {})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_nonexistent_token_returns_400(self):
        user = UserFactory()
        AthleteProfileFactory(user=user)
        client = _client(user)
        r = client.post(
            "/api/v1/attendance/classes/qr_checkin/",
            {"token": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST
