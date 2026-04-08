"""
Tests for dashboard selectors.

Each section is independent. All date arithmetic is controlled via the
`ref` parameter so tests never rely on the real clock.

ref = date(2025, 6, 11)  →  Wednesday, June 11 2025
  this week  : June 9–15 2025
  last week  : June 2–8  2025
  this month : June 1–30 2025
  prev month : May  1–31 2025
"""

import datetime
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from factories import (
    AcademyFactory,
    AcademyMembershipFactory,
    AthleteProfileFactory,
    SubscriptionFactory,
    TrainingClassFactory,
    UserFactory,
)


# ─── shared fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def academy(db):
    return AcademyFactory()


@pytest.fixture
def ref():
    """Fixed reference date: Wednesday June 11, 2025."""
    return date(2025, 6, 11)


# ─── helpers ──────────────────────────────────────────────────────────────────


def _make_payment(academy, amount, payment_type="SUBSCRIPTION", target_date=None, currency="eur"):
    """Create a SUCCEEDED Payment with created_at set to target_date (a date object)."""
    from payments.models import Payment
    athlete = AthleteProfileFactory(academy=academy)
    target = target_date or date.today()
    paid_at = timezone.make_aware(datetime.datetime.combine(target, datetime.time(12, 0)))
    p = Payment.objects.create(
        academy=academy,
        athlete=athlete,
        payment_type=payment_type,
        amount_paid=Decimal(str(amount)),
        platform_fee=Decimal("0.00"),
        academy_net=Decimal(str(amount)),
        currency=currency,
        status="SUCCEEDED",
        stripe_payment_intent_id=f"pi_{amount}_{payment_type}_{id(athlete)}",
        extra_metadata={},
    )
    Payment.objects.filter(pk=p.pk).update(created_at=paid_at)
    p.refresh_from_db()
    return p


def _make_checkin(academy, target_date):
    """Create a CheckIn with checked_in_at set to target_date."""
    from attendance.models import CheckIn
    athlete = AthleteProfileFactory(academy=academy)
    tc = TrainingClassFactory(academy=academy, duration_minutes=60)
    ci = CheckIn.objects.create(athlete=athlete, training_class=tc, method="MANUAL")
    ts = timezone.make_aware(datetime.datetime.combine(target_date, datetime.time(10, 0)))
    CheckIn.objects.filter(pk=ci.pk).update(checked_in_at=ts)
    return ci


# ─── Revenue ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestRevenueSummary:
    def test_current_month_sums_succeeded_payments(self, academy, ref):
        from dashboard.selectors import get_revenue_summary
        _make_payment(academy, 100, target_date=date(2025, 6, 5))
        _make_payment(academy, 200, target_date=date(2025, 6, 10))
        data = get_revenue_summary(academy.pk, ref)
        assert Decimal(data["current_month"]) == Decimal("300.00")

    def test_excludes_failed_payments(self, academy, ref):
        from payments.models import Payment
        from dashboard.selectors import get_revenue_summary
        athlete = AthleteProfileFactory(academy=academy)
        p = Payment.objects.create(
            academy=academy, athlete=athlete,
            payment_type="SUBSCRIPTION", amount_paid=Decimal("100.00"),
            platform_fee=Decimal("0"), academy_net=Decimal("100"),
            currency="eur", status="FAILED",
            stripe_payment_intent_id="pi_fail_test_1", extra_metadata={},
        )
        paid_at = timezone.make_aware(datetime.datetime.combine(date(2025, 6, 5), datetime.time(12)))
        Payment.objects.filter(pk=p.pk).update(created_at=paid_at)
        data = get_revenue_summary(academy.pk, ref)
        assert Decimal(data["current_month"]) == Decimal("0.00")

    def test_previous_month_sums_may_payments(self, academy, ref):
        from dashboard.selectors import get_revenue_summary
        _make_payment(academy, 500, target_date=date(2025, 5, 15))
        data = get_revenue_summary(academy.pk, ref)
        assert Decimal(data["previous_month"]) == Decimal("500.00")

    def test_change_percent_positive(self, academy, ref):
        from dashboard.selectors import get_revenue_summary
        _make_payment(academy, 200, target_date=date(2025, 6, 5))   # current
        _make_payment(academy, 100, target_date=date(2025, 5, 15))  # previous
        data = get_revenue_summary(academy.pk, ref)
        assert data["change_percent"] == 100.0

    def test_change_percent_none_when_no_previous(self, academy, ref):
        from dashboard.selectors import get_revenue_summary
        _make_payment(academy, 200, target_date=date(2025, 6, 5))
        data = get_revenue_summary(academy.pk, ref)
        assert data["change_percent"] is None

    def test_by_type_breakdown(self, academy, ref):
        from dashboard.selectors import get_revenue_summary
        _make_payment(academy, 100, payment_type="SUBSCRIPTION", target_date=date(2025, 6, 5))
        _make_payment(academy, 50, payment_type="SEMINAR", target_date=date(2025, 6, 5))
        data = get_revenue_summary(academy.pk, ref)
        assert Decimal(data["by_type"]["SUBSCRIPTION"]) == Decimal("100.00")
        assert Decimal(data["by_type"]["SEMINAR"]) == Decimal("50.00")

    def test_currency_detected_from_payments(self, academy, ref):
        from dashboard.selectors import get_revenue_summary
        _make_payment(academy, 100, target_date=date(2025, 6, 5), currency="usd")
        data = get_revenue_summary(academy.pk, ref)
        assert data["currency"] == "usd"

    def test_zero_when_no_payments(self, academy, ref):
        from dashboard.selectors import get_revenue_summary
        data = get_revenue_summary(academy.pk, ref)
        assert Decimal(data["current_month"]) == Decimal("0.00")
        assert Decimal(data["previous_month"]) == Decimal("0.00")

    def test_excludes_other_academy_payments(self, academy, ref):
        from dashboard.selectors import get_revenue_summary
        other = AcademyFactory()
        _make_payment(other, 500, target_date=date(2025, 6, 5))
        data = get_revenue_summary(academy.pk, ref)
        assert Decimal(data["current_month"]) == Decimal("0.00")


# ─── Attendance ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAttendanceSummary:
    def test_this_week_count(self, academy, ref):
        from dashboard.selectors import get_attendance_summary
        # This week = June 9-15; last week = June 2-8
        _make_checkin(academy, date(2025, 6, 10))  # this week
        _make_checkin(academy, date(2025, 6, 4))   # last week (excluded)
        data = get_attendance_summary(academy.pk, ref)
        assert data["this_week"] == 1

    def test_last_week_count(self, academy, ref):
        from dashboard.selectors import get_attendance_summary
        _make_checkin(academy, date(2025, 6, 3))  # last week
        _make_checkin(academy, date(2025, 6, 5))  # last week
        data = get_attendance_summary(academy.pk, ref)
        assert data["last_week"] == 2

    def test_change_percent_with_equal_weeks(self, academy, ref):
        from dashboard.selectors import get_attendance_summary
        _make_checkin(academy, date(2025, 6, 10))  # this week: 1
        _make_checkin(academy, date(2025, 6, 4))   # last week: 1
        data = get_attendance_summary(academy.pk, ref)
        assert data["change_percent"] == 0.0

    def test_change_percent_none_when_last_week_zero(self, academy, ref):
        from dashboard.selectors import get_attendance_summary
        _make_checkin(academy, date(2025, 6, 10))
        data = get_attendance_summary(academy.pk, ref)
        assert data["change_percent"] is None

    def test_most_popular_class_type(self, academy, ref):
        from attendance.models import CheckIn
        from dashboard.selectors import get_attendance_summary
        gi_tc = TrainingClassFactory(academy=academy, class_type="GI")
        nogi_tc = TrainingClassFactory(academy=academy, class_type="NOGI")
        a1 = AthleteProfileFactory(academy=academy)
        a2 = AthleteProfileFactory(academy=academy)
        a3 = AthleteProfileFactory(academy=academy)
        ts = timezone.make_aware(datetime.datetime.combine(date(2025, 6, 5), datetime.time(10)))
        for athlete in [a1, a2]:
            ci = CheckIn.objects.create(athlete=athlete, training_class=gi_tc, method="MANUAL")
            CheckIn.objects.filter(pk=ci.pk).update(checked_in_at=ts)
        ci3 = CheckIn.objects.create(athlete=a3, training_class=nogi_tc, method="MANUAL")
        CheckIn.objects.filter(pk=ci3.pk).update(checked_in_at=ts)
        data = get_attendance_summary(academy.pk, ref)
        assert data["most_popular_class_type"] == "GI"

    def test_zero_when_no_checkins(self, academy, ref):
        from dashboard.selectors import get_attendance_summary
        data = get_attendance_summary(academy.pk, ref)
        assert data["this_week"] == 0
        assert data["last_week"] == 0
        assert data["most_popular_class_type"] is None


# ─── Members ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestMemberSummary:
    def test_total_active_members(self, academy):
        from dashboard.selectors import get_member_summary
        AcademyMembershipFactory(academy=academy, is_active=True)
        AcademyMembershipFactory(academy=academy, is_active=True)
        AcademyMembershipFactory(academy=academy, is_active=False)
        data = get_member_summary(academy.pk)
        assert data["total_active"] == 2

    def test_ready_for_promotion_count(self, academy):
        from dashboard.selectors import get_member_summary
        AthleteProfileFactory(academy=academy, stripes=4, belt="white")
        AthleteProfileFactory(academy=academy, stripes=4, belt="blue")
        AthleteProfileFactory(academy=academy, stripes=2, belt="white")
        data = get_member_summary(academy.pk)
        assert data["ready_for_promotion"] == 2

    def test_belt_distribution(self, academy):
        from dashboard.selectors import get_member_summary
        AthleteProfileFactory(academy=academy, belt="white")
        AthleteProfileFactory(academy=academy, belt="white")
        AthleteProfileFactory(academy=academy, belt="blue")
        data = get_member_summary(academy.pk)
        assert data["belt_distribution"]["white"] == 2
        assert data["belt_distribution"]["blue"] == 1

    def test_excludes_other_academy_members(self, academy):
        from dashboard.selectors import get_member_summary
        other = AcademyFactory()
        AcademyMembershipFactory(academy=other, is_active=True)
        data = get_member_summary(academy.pk)
        assert data["total_active"] == 0

    def test_empty_academy(self, academy):
        from dashboard.selectors import get_member_summary
        data = get_member_summary(academy.pk)
        assert data["total_active"] == 0
        assert data["ready_for_promotion"] == 0
        assert data["belt_distribution"] == {}


# ─── Retention ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestRetentionSummary:
    def test_active_subscriptions(self, academy, ref):
        from dashboard.selectors import get_retention_summary
        athlete = AthleteProfileFactory(academy=academy)
        SubscriptionFactory(athlete=athlete, status="ACTIVE")
        SubscriptionFactory(athlete=athlete, status="EXPIRED")
        data = get_retention_summary(academy.pk, ref)
        assert data["active_subscriptions"] == 1

    def test_cancelled_this_month(self, academy, ref):
        from membership.models import Subscription
        from dashboard.selectors import get_retention_summary
        athlete = AthleteProfileFactory(academy=academy)
        sub = SubscriptionFactory(athlete=athlete, status="CANCELLED")
        cancelled_at = timezone.make_aware(
            datetime.datetime.combine(date(2025, 6, 5), datetime.time(12))
        )
        Subscription.objects.filter(pk=sub.pk).update(updated_at=cancelled_at)
        data = get_retention_summary(academy.pk, ref)
        assert data["cancelled_this_month"] == 1

    def test_churn_rate_calculation(self, academy, ref):
        from membership.models import Subscription
        from dashboard.selectors import get_retention_summary
        a1 = AthleteProfileFactory(academy=academy)
        a2 = AthleteProfileFactory(academy=academy)
        SubscriptionFactory(athlete=a1, status="ACTIVE")
        sub = SubscriptionFactory(athlete=a2, status="CANCELLED")
        cancelled_at = timezone.make_aware(
            datetime.datetime.combine(date(2025, 6, 5), datetime.time(12))
        )
        Subscription.objects.filter(pk=sub.pk).update(updated_at=cancelled_at)
        data = get_retention_summary(academy.pk, ref)
        # 1 active + 1 cancelled → churn = 1/2 * 100 = 50.0
        assert data["churn_rate"] == 50.0

    def test_zero_churn_no_cancellations(self, academy, ref):
        from dashboard.selectors import get_retention_summary
        athlete = AthleteProfileFactory(academy=academy)
        SubscriptionFactory(athlete=athlete, status="ACTIVE")
        data = get_retention_summary(academy.pk, ref)
        assert data["churn_rate"] == 0.0

    def test_zero_when_no_subscriptions(self, academy, ref):
        from dashboard.selectors import get_retention_summary
        data = get_retention_summary(academy.pk, ref)
        assert data["active_subscriptions"] == 0
        assert data["cancelled_this_month"] == 0
        assert data["churn_rate"] == 0.0


# ─── Top athletes ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTopAthletesSummary:
    def test_returns_top_n_by_mat_hours(self, academy):
        from dashboard.selectors import get_top_athletes_summary
        AthleteProfileFactory(academy=academy, mat_hours=500.0)
        AthleteProfileFactory(academy=academy, mat_hours=100.0)
        AthleteProfileFactory(academy=academy, mat_hours=300.0)
        data = get_top_athletes_summary(academy.pk, limit=2)
        assert len(data) == 2
        assert data[0]["mat_hours"] == 500.0
        assert data[1]["mat_hours"] == 300.0

    def test_response_shape(self, academy):
        from dashboard.selectors import get_top_athletes_summary
        AthleteProfileFactory(academy=academy, mat_hours=100.0)
        data = get_top_athletes_summary(academy.pk)
        assert len(data) == 1
        row = data[0]
        assert "athlete_id" in row
        assert "username" in row
        assert "belt" in row
        assert "stripes" in row
        assert "mat_hours" in row

    def test_empty_when_no_athletes(self, academy):
        from dashboard.selectors import get_top_athletes_summary
        data = get_top_athletes_summary(academy.pk)
        assert data == []

    def test_excludes_other_academy_athletes(self, academy):
        from dashboard.selectors import get_top_athletes_summary
        other = AcademyFactory()
        AthleteProfileFactory(academy=other, mat_hours=999.0)
        data = get_top_athletes_summary(academy.pk)
        assert data == []


# ─── Full dashboard ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestGetAcademyDashboard:
    def test_returns_all_sections(self, academy, ref):
        from dashboard.selectors import get_academy_dashboard
        data = get_academy_dashboard(academy.pk, ref)
        assert data["academy_id"] == academy.pk
        assert "generated_at" in data
        assert "period_ref" in data
        assert "revenue" in data
        assert "attendance" in data
        assert "members" in data
        assert "retention" in data
        assert "top_athletes" in data

    def test_period_ref_matches_input(self, academy, ref):
        from dashboard.selectors import get_academy_dashboard
        data = get_academy_dashboard(academy.pk, ref)
        assert data["period_ref"] == str(ref)
