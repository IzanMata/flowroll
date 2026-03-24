"""
Tests for SubscriptionService.

Run with:  pytest membership/tests/test_subscriptions.py
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from factories import AthleteProfileFactory, MembershipPlanFactory, SubscriptionFactory
from membership.models import MembershipPlan, Subscription
from membership.services import SubscriptionService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def monthly_plan(db, academy):
    return MembershipPlanFactory(
        academy=academy,
        plan_type=MembershipPlan.PlanType.MONTHLY,
        price=Decimal("99.00"),
        duration_days=30,
        class_limit=None,
    )


@pytest.fixture
def annual_plan(db, academy):
    return MembershipPlanFactory(
        academy=academy,
        plan_type=MembershipPlan.PlanType.ANNUAL,
        price=Decimal("900.00"),
        duration_days=365,
        class_limit=None,
    )


@pytest.fixture
def class_pass_plan(db, academy):
    return MembershipPlanFactory(
        academy=academy,
        plan_type=MembershipPlan.PlanType.CLASS_PASS,
        price=Decimal("50.00"),
        duration_days=None,
        class_limit=10,
    )


@pytest.fixture
def open_ended_plan(db, academy):
    """No duration_days — billing-cycle style."""
    return MembershipPlanFactory(
        academy=academy,
        plan_type=MembershipPlan.PlanType.MONTHLY,
        duration_days=None,
        class_limit=None,
    )


@pytest.fixture
def athlete(db, academy):
    return AthleteProfileFactory(academy=academy)


# ---------------------------------------------------------------------------
# subscribe()
# ---------------------------------------------------------------------------


class TestSubscriptionServiceSubscribe:
    def test_creates_active_subscription(self, db, athlete, monthly_plan):
        sub = SubscriptionService.subscribe(athlete, monthly_plan)

        assert sub.pk is not None
        assert sub.athlete == athlete
        assert sub.plan == monthly_plan
        assert sub.status == Subscription.Status.ACTIVE

    def test_sets_end_date_from_duration_days(self, db, athlete, monthly_plan):
        today = date.today()
        sub = SubscriptionService.subscribe(athlete, monthly_plan, start_date=today)

        assert sub.end_date == today + timedelta(days=30)

    def test_annual_plan_sets_correct_end_date(self, db, athlete, annual_plan):
        start = date(2025, 1, 1)
        sub = SubscriptionService.subscribe(athlete, annual_plan, start_date=start)

        assert sub.end_date == date(2026, 1, 1)

    def test_open_ended_plan_has_no_end_date(self, db, athlete, open_ended_plan):
        sub = SubscriptionService.subscribe(athlete, open_ended_plan)

        assert sub.end_date is None

    def test_class_pass_sets_classes_remaining(self, db, athlete, class_pass_plan):
        sub = SubscriptionService.subscribe(athlete, class_pass_plan)

        assert sub.classes_remaining == 10

    def test_unlimited_plan_leaves_classes_remaining_null(self, db, athlete, monthly_plan):
        sub = SubscriptionService.subscribe(athlete, monthly_plan)

        assert sub.classes_remaining is None

    def test_defaults_start_date_to_today(self, db, athlete, monthly_plan):
        sub = SubscriptionService.subscribe(athlete, monthly_plan)

        assert sub.start_date == date.today()

    def test_custom_start_date_is_respected(self, db, athlete, monthly_plan):
        custom_start = date(2024, 6, 15)
        sub = SubscriptionService.subscribe(athlete, monthly_plan, start_date=custom_start)

        assert sub.start_date == custom_start

    def test_subscription_is_persisted_to_db(self, db, athlete, monthly_plan):
        sub = SubscriptionService.subscribe(athlete, monthly_plan)

        assert Subscription.objects.filter(pk=sub.pk).exists()


# ---------------------------------------------------------------------------
# consume_class_pass()
# ---------------------------------------------------------------------------


class TestSubscriptionServiceConsumeClassPass:
    def test_decrements_classes_remaining(self, db, athlete, class_pass_plan):
        sub = SubscriptionService.subscribe(athlete, class_pass_plan)
        initial = sub.classes_remaining

        sub = SubscriptionService.consume_class_pass(sub)

        assert sub.classes_remaining == initial - 1

    def test_status_stays_active_while_classes_remain(self, db, athlete, class_pass_plan):
        sub = SubscriptionService.subscribe(athlete, class_pass_plan)  # 10 classes

        sub = SubscriptionService.consume_class_pass(sub)

        assert sub.status == Subscription.Status.ACTIVE

    def test_marks_expired_when_last_class_consumed(self, db, athlete, academy):
        plan = MembershipPlanFactory(
            academy=academy,
            plan_type=MembershipPlan.PlanType.CLASS_PASS,
            class_limit=1,
        )
        sub = SubscriptionService.subscribe(athlete, plan)

        sub = SubscriptionService.consume_class_pass(sub)

        assert sub.classes_remaining == 0
        assert sub.status == Subscription.Status.EXPIRED

    def test_persists_changes_to_db(self, db, athlete, class_pass_plan):
        sub = SubscriptionService.subscribe(athlete, class_pass_plan)
        SubscriptionService.consume_class_pass(sub)

        sub.refresh_from_db()
        assert sub.classes_remaining == 9

    def test_raises_for_non_class_pass_plan(self, db, athlete, monthly_plan):
        sub = SubscriptionService.subscribe(athlete, monthly_plan)

        with pytest.raises(ValueError, match="CLASS_PASS"):
            SubscriptionService.consume_class_pass(sub)

    def test_raises_for_unlimited_class_pass(self, db, athlete, academy):
        plan = MembershipPlanFactory(
            academy=academy,
            plan_type=MembershipPlan.PlanType.CLASS_PASS,
            class_limit=None,
        )
        sub = SubscriptionService.subscribe(athlete, plan)

        with pytest.raises(ValueError, match="unlimited"):
            SubscriptionService.consume_class_pass(sub)

    def test_raises_when_no_classes_remaining(self, db, athlete, academy):
        plan = MembershipPlanFactory(
            academy=academy,
            plan_type=MembershipPlan.PlanType.CLASS_PASS,
            class_limit=1,
        )
        sub = SubscriptionService.subscribe(athlete, plan)
        SubscriptionService.consume_class_pass(sub)  # exhaust it
        sub.refresh_from_db()

        with pytest.raises(ValueError, match="No classes remaining"):
            SubscriptionService.consume_class_pass(sub)


# ---------------------------------------------------------------------------
# expire_stale_subscriptions()
# ---------------------------------------------------------------------------


class TestSubscriptionServiceExpireStale:
    def test_expires_active_subscriptions_past_end_date(self, db, athlete, monthly_plan):
        sub = SubscriptionFactory(
            athlete=athlete,
            plan=monthly_plan,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            status=Subscription.Status.ACTIVE,
        )

        count = SubscriptionService.expire_stale_subscriptions()

        sub.refresh_from_db()
        assert count >= 1
        assert sub.status == Subscription.Status.EXPIRED

    def test_does_not_expire_future_subscriptions(self, db, athlete, monthly_plan):
        future_end = date.today() + timedelta(days=30)
        sub = SubscriptionFactory(
            athlete=athlete,
            plan=monthly_plan,
            start_date=date.today(),
            end_date=future_end,
            status=Subscription.Status.ACTIVE,
        )

        SubscriptionService.expire_stale_subscriptions()

        sub.refresh_from_db()
        assert sub.status == Subscription.Status.ACTIVE

    def test_does_not_touch_already_expired_subscriptions(self, db, athlete, monthly_plan):
        sub = SubscriptionFactory(
            athlete=athlete,
            plan=monthly_plan,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            status=Subscription.Status.EXPIRED,
        )

        SubscriptionService.expire_stale_subscriptions()

        sub.refresh_from_db()
        assert sub.status == Subscription.Status.EXPIRED

    def test_does_not_touch_open_ended_subscriptions(self, db, athlete, open_ended_plan):
        sub = SubscriptionFactory(
            athlete=athlete,
            plan=open_ended_plan,
            start_date=date.today(),
            end_date=None,
            status=Subscription.Status.ACTIVE,
        )

        SubscriptionService.expire_stale_subscriptions()

        sub.refresh_from_db()
        assert sub.status == Subscription.Status.ACTIVE

    def test_returns_count_of_expired(self, db, academy):
        plan = MembershipPlanFactory(academy=academy)
        athletes = [AthleteProfileFactory(academy=academy) for _ in range(3)]
        for a in athletes:
            SubscriptionFactory(
                athlete=a,
                plan=plan,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                status=Subscription.Status.ACTIVE,
            )

        count = SubscriptionService.expire_stale_subscriptions()

        assert count == 3