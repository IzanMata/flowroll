"""
Tests for payments service layer.

All Stripe API calls are mocked — tests assert correct arguments passed to
Stripe and correct DB state changes, without hitting the real API.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from factories import (
    AcademyFactory,
    AthleteProfileFactory,
    MembershipPlanFactory,
    PaymentFactory,
    SeminarFactory,
    SeminarRegistrationFactory,
    StripeAcademyConfigFactory,
    StripeWebhookEventFactory,
    SubscriptionFactory,
)
from membership.models import SeminarRegistration, Subscription
from payments.models import Payment, StripeAcademyConfig
from payments.services import (
    StripeCheckoutService,
    StripeConnectExpressService,
    StripeCustomerService,
    _compute_fee_cents,
    _platform_fee_percent,
    dispatch_webhook_event,
    refund_payment,
)


# ---------------------------------------------------------------------------
# Fee helpers
# ---------------------------------------------------------------------------


class TestFeeHelpers:
    def test_platform_fee_percent_default(self, settings):
        settings.STRIPE_PLATFORM_FEE_PERCENT = 10.0
        assert _platform_fee_percent() == 10.0

    def test_platform_fee_percent_custom(self, settings):
        settings.STRIPE_PLATFORM_FEE_PERCENT = 15.0
        assert _platform_fee_percent() == 15.0

    def test_compute_fee_cents_10_percent(self, settings):
        settings.STRIPE_PLATFORM_FEE_PERCENT = 10.0
        assert _compute_fee_cents(5000) == 500  # 10% of €50

    def test_compute_fee_cents_rounds(self, settings):
        settings.STRIPE_PLATFORM_FEE_PERCENT = 10.0
        # 10% of 333 = 33.3 → rounds to 33
        assert _compute_fee_cents(333) == 33


# ---------------------------------------------------------------------------
# StripeConnectExpressService
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStripeConnectExpressService:
    def test_create_account_and_link_new_academy(self):
        academy = AcademyFactory(country="Spain", email="gym@example.com")

        mock_account = {"id": "acct_new123"}
        mock_link = {"url": "https://connect.stripe.com/onboard/acct_new123"}

        with patch("stripe.Account.create", return_value=mock_account) as mock_create, \
             patch("stripe.AccountLink.create", return_value=mock_link) as mock_link_create:

            url = StripeConnectExpressService.create_account_and_onboarding_link(
                academy=academy,
                refresh_url="https://app.example.com/refresh",
                return_url="https://app.example.com/return",
            )

        assert url == "https://connect.stripe.com/onboard/acct_new123"
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["type"] == "express"
        assert call_kwargs["email"] == "gym@example.com"

        config = StripeAcademyConfig.objects.get(academy=academy)
        assert config.stripe_connect_account_id == "acct_new123"

    def test_create_link_existing_account_skips_account_create(self):
        config = StripeAcademyConfigFactory(stripe_connect_account_id="acct_exist")
        mock_link = {"url": "https://connect.stripe.com/onboard/acct_exist"}

        with patch("stripe.Account.create") as mock_create, \
             patch("stripe.AccountLink.create", return_value=mock_link):

            url = StripeConnectExpressService.create_account_and_onboarding_link(
                academy=config.academy,
                refresh_url="https://app.example.com/refresh",
                return_url="https://app.example.com/return",
            )

        mock_create.assert_not_called()
        assert url == "https://connect.stripe.com/onboard/acct_exist"

    def test_create_account_country_fallback_to_ES(self):
        academy = AcademyFactory(country="")  # no country set
        mock_account = {"id": "acct_fallback"}
        mock_link = {"url": "https://connect.stripe.com/onboard/acct_fallback"}

        with patch("stripe.Account.create", return_value=mock_account) as mock_create, \
             patch("stripe.AccountLink.create", return_value=mock_link):

            StripeConnectExpressService.create_account_and_onboarding_link(
                academy=academy,
                refresh_url="https://app.example.com/refresh",
                return_url="https://app.example.com/return",
            )

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["country"] == "ES"

    def test_create_login_link_returns_url(self):
        config = StripeAcademyConfigFactory(stripe_connect_account_id="acct_login")
        mock_link = {"url": "https://dashboard.stripe.com/login/acct_login"}

        with patch("stripe.Account.create_login_link", return_value=mock_link):
            url = StripeConnectExpressService.create_login_link(config.academy)

        assert url == "https://dashboard.stripe.com/login/acct_login"

    def test_create_login_link_raises_if_not_onboarded(self):
        academy = AcademyFactory()
        # No StripeAcademyConfig created
        with pytest.raises(ValueError, match="not completed"):
            StripeConnectExpressService.create_login_link(academy)

    def test_sync_account_status_updates_config(self):
        config = StripeAcademyConfigFactory(
            stripe_connect_account_id="acct_sync",
            charges_enabled=False,
            payouts_enabled=False,
        )

        stripe_account = {
            "id": "acct_sync",
            "charges_enabled": True,
            "payouts_enabled": True,
            "details_submitted": True,
        }
        StripeConnectExpressService.sync_account_status(stripe_account)

        config.refresh_from_db()
        assert config.charges_enabled is True
        assert config.payouts_enabled is True
        assert config.details_submitted is True
        assert config.onboarding_completed_at is not None

    def test_sync_account_status_clears_onboarding_at_when_disabled(self):
        config = StripeAcademyConfigFactory(
            stripe_connect_account_id="acct_disabled",
            charges_enabled=True,
        )

        stripe_account = {
            "id": "acct_disabled",
            "charges_enabled": False,
            "payouts_enabled": False,
            "details_submitted": True,
        }
        StripeConnectExpressService.sync_account_status(stripe_account)

        config.refresh_from_db()
        assert config.charges_enabled is False
        assert config.onboarding_completed_at is None

    def test_sync_account_status_unknown_account_logs_warning(self, caplog):
        import logging
        stripe_account = {
            "id": "acct_unknown",
            "charges_enabled": True,
            "payouts_enabled": True,
            "details_submitted": True,
        }
        with caplog.at_level(logging.WARNING, logger="payments.services"):
            StripeConnectExpressService.sync_account_status(stripe_account)
        assert "unknown" in caplog.text

    def test_get_account_status_not_connected(self):
        academy = AcademyFactory()
        status = StripeConnectExpressService.get_account_status(academy)
        assert status["status"] == "not_connected"
        assert status["charges_enabled"] is False

    def test_get_account_status_active(self):
        config = StripeAcademyConfigFactory(
            stripe_connect_account_id="acct_active",
            charges_enabled=True,
            payouts_enabled=True,
        )
        status = StripeConnectExpressService.get_account_status(config.academy)
        assert status["status"] == "active"
        assert status["charges_enabled"] is True

    def test_get_account_status_pending(self):
        config = StripeAcademyConfigFactory(
            stripe_connect_account_id="acct_pending",
            charges_enabled=False,
        )
        status = StripeConnectExpressService.get_account_status(config.academy)
        assert status["status"] == "pending_verification"


# ---------------------------------------------------------------------------
# StripeCustomerService
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStripeCustomerService:
    def test_get_or_create_creates_new_customer(self):
        athlete = AthleteProfileFactory()
        athlete.stripe_customer_id = ""
        athlete.save(update_fields=["stripe_customer_id"])

        mock_customer = {"id": "cus_new123"}
        with patch("stripe.Customer.create", return_value=mock_customer) as mock_create:
            cus_id = StripeCustomerService.get_or_create(athlete)

        assert cus_id == "cus_new123"
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["email"] == athlete.user.email

        athlete.refresh_from_db()
        assert athlete.stripe_customer_id == "cus_new123"

    def test_get_or_create_returns_existing(self):
        athlete = AthleteProfileFactory()
        athlete.stripe_customer_id = "cus_existing"
        athlete.save(update_fields=["stripe_customer_id"])

        with patch("stripe.Customer.create") as mock_create:
            cus_id = StripeCustomerService.get_or_create(athlete)

        mock_create.assert_not_called()
        assert cus_id == "cus_existing"

    def test_sync_email_calls_stripe_modify(self):
        athlete = AthleteProfileFactory()
        athlete.stripe_customer_id = "cus_sync"
        athlete.save(update_fields=["stripe_customer_id"])

        with patch("stripe.Customer.modify") as mock_modify:
            StripeCustomerService.sync_email(athlete)

        mock_modify.assert_called_once_with("cus_sync", email=athlete.user.email)

    def test_sync_email_skips_when_no_customer_id(self):
        athlete = AthleteProfileFactory()
        athlete.stripe_customer_id = ""
        athlete.save(update_fields=["stripe_customer_id"])

        with patch("stripe.Customer.modify") as mock_modify:
            StripeCustomerService.sync_email(athlete)

        mock_modify.assert_not_called()

    def test_create_portal_session_returns_url(self):
        athlete = AthleteProfileFactory()
        athlete.stripe_customer_id = "cus_portal"
        athlete.save(update_fields=["stripe_customer_id"])

        mock_session = {"url": "https://billing.stripe.com/session/test"}
        with patch("stripe.billing_portal.Session.create", return_value=mock_session):
            url = StripeCustomerService.create_portal_session(
                athlete, return_url="https://app.example.com"
            )

        assert url == "https://billing.stripe.com/session/test"


# ---------------------------------------------------------------------------
# StripeCheckoutService
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStripeCheckoutService:
    def _setup_connected_academy(self):
        config = StripeAcademyConfigFactory(
            stripe_connect_account_id="acct_checkout",
            charges_enabled=True,
        )
        return config.academy

    def test_require_connect_account_raises_when_no_config(self):
        academy = AcademyFactory()
        with pytest.raises(ValueError, match="not started"):
            StripeCheckoutService._require_connect_account(academy)

    def test_require_connect_account_raises_when_no_account_id(self):
        academy = AcademyFactory()
        StripeAcademyConfig.objects.create(academy=academy)
        with pytest.raises(ValueError, match="not completed"):
            StripeCheckoutService._require_connect_account(academy)

    def test_require_connect_account_raises_when_charges_disabled(self):
        config = StripeAcademyConfigFactory(
            stripe_connect_account_id="acct_disabled",
            charges_enabled=False,
        )
        with pytest.raises(ValueError, match="not yet verified"):
            StripeCheckoutService._require_connect_account(config.academy)

    def test_create_subscription_checkout_returns_url(self, settings):
        settings.STRIPE_PLATFORM_FEE_PERCENT = 10.0
        academy = self._setup_connected_academy()
        plan = MembershipPlanFactory(
            academy=academy,
            plan_type="MONTHLY",
            stripe_price_id="price_monthly_001",
        )
        athlete = AthleteProfileFactory()
        athlete.stripe_customer_id = "cus_sub"
        athlete.save(update_fields=["stripe_customer_id"])

        mock_session = {"url": "https://checkout.stripe.com/sub_session"}
        with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            url = StripeCheckoutService.create_subscription_checkout(
                athlete=athlete,
                plan=plan,
                success_url="https://app.example.com/success",
                cancel_url="https://app.example.com/cancel",
            )

        assert url == "https://checkout.stripe.com/sub_session"
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["mode"] == "subscription"
        assert call_kwargs["subscription_data"]["application_fee_percent"] == 10.0
        assert call_kwargs["subscription_data"]["transfer_data"]["destination"] == "acct_checkout"

    def test_create_subscription_checkout_raises_when_no_price_id(self):
        academy = self._setup_connected_academy()
        plan = MembershipPlanFactory(academy=academy, plan_type="MONTHLY", stripe_price_id="")
        athlete = AthleteProfileFactory()

        with pytest.raises(ValueError, match="no Stripe Price"):
            StripeCheckoutService.create_subscription_checkout(
                athlete=athlete,
                plan=plan,
                success_url="https://app.example.com/success",
                cancel_url="https://app.example.com/cancel",
            )

    def test_create_one_time_checkout_returns_url(self, settings):
        settings.STRIPE_PLATFORM_FEE_PERCENT = 10.0
        academy = self._setup_connected_academy()
        plan = MembershipPlanFactory(
            academy=academy,
            plan_type="CLASS_PASS",
            price=Decimal("100.00"),
        )
        athlete = AthleteProfileFactory()
        athlete.stripe_customer_id = "cus_onetime"
        athlete.save(update_fields=["stripe_customer_id"])

        mock_session = {"url": "https://checkout.stripe.com/onetime_session"}
        with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            url = StripeCheckoutService.create_one_time_checkout(
                athlete=athlete,
                plan=plan,
                success_url="https://app.example.com/success",
                cancel_url="https://app.example.com/cancel",
            )

        assert url == "https://checkout.stripe.com/onetime_session"
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["mode"] == "payment"
        pid_data = call_kwargs["payment_intent_data"]
        assert pid_data["application_fee_amount"] == 1000  # 10% of €100 = €10 = 1000 cents
        assert pid_data["transfer_data"]["destination"] == "acct_checkout"

    def test_create_seminar_checkout_returns_url(self, settings):
        settings.STRIPE_PLATFORM_FEE_PERCENT = 10.0
        academy = self._setup_connected_academy()
        seminar = SeminarFactory(academy=academy, price=Decimal("50.00"))
        athlete = AthleteProfileFactory()
        athlete.stripe_customer_id = "cus_seminar"
        athlete.save(update_fields=["stripe_customer_id"])
        registration = SeminarRegistrationFactory(seminar=seminar, athlete=athlete)

        mock_session = {"url": "https://checkout.stripe.com/seminar_session"}
        with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            url = StripeCheckoutService.create_seminar_checkout(
                athlete=athlete,
                seminar=seminar,
                registration=registration,
                success_url="https://app.example.com/success",
                cancel_url="https://app.example.com/cancel",
            )

        assert url == "https://checkout.stripe.com/seminar_session"
        call_kwargs = mock_create.call_args[1]
        pid_data = call_kwargs["payment_intent_data"]
        assert pid_data["application_fee_amount"] == 500  # 10% of €50 = 500 cents
        assert pid_data["transfer_data"]["destination"] == "acct_checkout"
        # metadata must carry seminar_registration_id
        assert call_kwargs["metadata"]["seminar_registration_id"] == str(registration.pk)
        assert call_kwargs["metadata"]["purpose"] == "seminar"

    def test_create_seminar_checkout_fee_in_metadata(self, settings):
        settings.STRIPE_PLATFORM_FEE_PERCENT = 10.0
        academy = self._setup_connected_academy()
        seminar = SeminarFactory(academy=academy, price=Decimal("50.00"))
        athlete = AthleteProfileFactory()
        athlete.stripe_customer_id = "cus_fee_meta"
        athlete.save(update_fields=["stripe_customer_id"])
        registration = SeminarRegistrationFactory(seminar=seminar, athlete=athlete)

        mock_session = {"url": "https://checkout.stripe.com/fee_session"}
        with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            StripeCheckoutService.create_seminar_checkout(
                athlete=athlete,
                seminar=seminar,
                registration=registration,
                success_url="https://app.example.com/success",
                cancel_url="https://app.example.com/cancel",
            )

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["metadata"]["platform_fee_cents"] == "500"


# ---------------------------------------------------------------------------
# refund_payment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRefundPayment:
    def test_refund_succeeded_payment(self):
        payment = PaymentFactory(
            status=Payment.Status.SUCCEEDED,
            stripe_payment_intent_id="pi_refund_me",
        )
        mock_refund = {"id": "re_test123", "status": "succeeded"}

        with patch("stripe.Refund.create", return_value=mock_refund) as mock_create:
            result = refund_payment(payment)

        mock_create.assert_called_once_with(payment_intent="pi_refund_me")
        payment.refresh_from_db()
        assert payment.status == Payment.Status.REFUNDED

    def test_refund_raises_for_non_succeeded_payment(self):
        payment = PaymentFactory(status=Payment.Status.PENDING)
        with pytest.raises(ValueError, match="Cannot refund"):
            refund_payment(payment)

    def test_refund_raises_for_already_refunded(self):
        payment = PaymentFactory(status=Payment.Status.REFUNDED)
        with pytest.raises(ValueError, match="Cannot refund"):
            refund_payment(payment)


# ---------------------------------------------------------------------------
# Webhook dispatcher — dispatch_webhook_event
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDispatchWebhookEvent:
    def _make_event(self, event_type, obj):
        return {"type": event_type, "data": {"object": obj}}

    def test_unknown_event_type_does_not_raise(self):
        event = self._make_event("completely.unknown.event", {})
        dispatch_webhook_event(event)  # must not raise

    def test_account_updated_syncs_config(self):
        config = StripeAcademyConfigFactory(
            stripe_connect_account_id="acct_dispatch",
            charges_enabled=False,
        )
        event = self._make_event("account.updated", {
            "id": "acct_dispatch",
            "charges_enabled": True,
            "payouts_enabled": True,
            "details_submitted": True,
        })
        dispatch_webhook_event(event)
        config.refresh_from_db()
        assert config.charges_enabled is True

    def test_payment_intent_succeeded_creates_payment_record(self):
        athlete = AthleteProfileFactory()
        academy = AcademyFactory()
        pi = {
            "id": "pi_dispatch_001",
            "amount_received": 5000,
            "currency": "eur",
            "metadata": {
                "purpose": "one_time_plan",
                "athlete_id": str(athlete.pk),
                "academy_id": str(academy.pk),
                "platform_fee_cents": "500",
            },
        }
        event = self._make_event("payment_intent.succeeded", pi)
        dispatch_webhook_event(event)

        payment = Payment.objects.get(stripe_payment_intent_id="pi_dispatch_001")
        assert payment.status == Payment.Status.SUCCEEDED
        assert payment.amount_paid == Decimal("50.00")
        assert payment.platform_fee == Decimal("5.00")
        assert payment.academy_net == Decimal("45.00")

    def test_payment_intent_succeeded_is_idempotent(self):
        athlete = AthleteProfileFactory()
        academy = AcademyFactory()
        pi = {
            "id": "pi_idempotent",
            "amount_received": 5000,
            "currency": "eur",
            "metadata": {
                "purpose": "one_time_plan",
                "athlete_id": str(athlete.pk),
                "academy_id": str(academy.pk),
                "platform_fee_cents": "500",
            },
        }
        event = self._make_event("payment_intent.succeeded", pi)
        dispatch_webhook_event(event)
        dispatch_webhook_event(event)  # second call must not create a duplicate

        assert Payment.objects.filter(stripe_payment_intent_id="pi_idempotent").count() == 1

    def test_payment_intent_succeeded_seminar_marks_registration_paid(self):
        athlete = AthleteProfileFactory()
        academy = AcademyFactory()
        seminar = SeminarFactory(academy=academy)
        registration = SeminarRegistrationFactory(
            seminar=seminar,
            athlete=athlete,
            payment_status="PENDING",
        )
        pi = {
            "id": "pi_seminar_paid",
            "amount_received": 5000,
            "currency": "eur",
            "metadata": {
                "purpose": "seminar",
                "athlete_id": str(athlete.pk),
                "academy_id": str(academy.pk),
                "seminar_registration_id": str(registration.pk),
                "platform_fee_cents": "500",
            },
        }
        event = self._make_event("payment_intent.succeeded", pi)
        dispatch_webhook_event(event)

        registration.refresh_from_db()
        assert registration.payment_status == SeminarRegistration.PaymentStatus.PAID
        assert registration.stripe_payment_intent_id == "pi_seminar_paid"

    def test_payment_intent_succeeded_skips_missing_athlete_or_academy(self):
        pi = {
            "id": "pi_no_ids",
            "amount_received": 5000,
            "currency": "eur",
            "metadata": {"purpose": "one_time_plan"},
        }
        event = self._make_event("payment_intent.succeeded", pi)
        dispatch_webhook_event(event)  # must not raise
        assert not Payment.objects.filter(stripe_payment_intent_id="pi_no_ids").exists()

    def test_invoice_payment_succeeded_activates_subscription(self):
        plan = MembershipPlanFactory()
        athlete = AthleteProfileFactory()
        sub = SubscriptionFactory(
            plan=plan,
            athlete=athlete,
            status=Subscription.Status.PAUSED,
            stripe_subscription_id="sub_activate",
        )
        invoice = {
            "id": "in_test_001",
            "subscription": "sub_activate",
            "amount_paid": 9999,
            "currency": "eur",
            "payment_intent": "pi_invoice_001",
            "hosted_invoice_url": "https://invoice.stripe.com/test",
        }
        event = self._make_event("invoice.payment_succeeded", invoice)
        dispatch_webhook_event(event)

        sub.refresh_from_db()
        assert sub.status == Subscription.Status.ACTIVE

        payment = Payment.objects.get(stripe_payment_intent_id="pi_invoice_001")
        assert payment.payment_type == Payment.PaymentType.SUBSCRIPTION
        assert payment.stripe_invoice_url == "https://invoice.stripe.com/test"

    def test_invoice_payment_succeeded_is_idempotent(self):
        plan = MembershipPlanFactory()
        sub = SubscriptionFactory(
            plan=plan,
            status=Subscription.Status.ACTIVE,
            stripe_subscription_id="sub_idempotent_inv",
        )
        invoice = {
            "id": "in_idem",
            "subscription": "sub_idempotent_inv",
            "amount_paid": 5000,
            "currency": "eur",
            "payment_intent": "pi_idem_inv",
        }
        event = self._make_event("invoice.payment_succeeded", invoice)
        dispatch_webhook_event(event)
        dispatch_webhook_event(event)

        assert Payment.objects.filter(stripe_payment_intent_id="pi_idem_inv").count() == 1

    def test_invoice_payment_succeeded_skips_unknown_subscription(self, caplog):
        import logging
        invoice = {
            "subscription": "sub_unknown_xyz",
            "amount_paid": 5000,
            "currency": "eur",
            "payment_intent": "pi_unknown",
        }
        event = self._make_event("invoice.payment_succeeded", invoice)
        with caplog.at_level(logging.WARNING, logger="payments.services"):
            dispatch_webhook_event(event)
        assert not Payment.objects.filter(stripe_payment_intent_id="pi_unknown").exists()

    def test_invoice_payment_failed_pauses_subscription(self):
        sub = SubscriptionFactory(
            status=Subscription.Status.ACTIVE,
            stripe_subscription_id="sub_fail",
        )
        event = self._make_event("invoice.payment_failed", {"subscription": "sub_fail"})
        dispatch_webhook_event(event)
        sub.refresh_from_db()
        assert sub.status == Subscription.Status.PAUSED

    def test_subscription_deleted_cancels_local_subscription(self):
        sub = SubscriptionFactory(
            status=Subscription.Status.ACTIVE,
            stripe_subscription_id="sub_deleted",
        )
        event = self._make_event("customer.subscription.deleted", {"id": "sub_deleted"})
        dispatch_webhook_event(event)
        sub.refresh_from_db()
        assert sub.status == Subscription.Status.CANCELLED

    def test_subscription_updated_syncs_status(self):
        sub = SubscriptionFactory(
            status=Subscription.Status.ACTIVE,
            stripe_subscription_id="sub_update",
        )
        event = self._make_event("customer.subscription.updated", {
            "id": "sub_update",
            "status": "past_due",
        })
        dispatch_webhook_event(event)
        sub.refresh_from_db()
        assert sub.status == Subscription.Status.PAUSED

    def test_charge_refunded_marks_payment_refunded(self):
        payment = PaymentFactory(
            status=Payment.Status.SUCCEEDED,
            stripe_payment_intent_id="pi_charge_refund",
        )
        event = self._make_event("charge.refunded", {"payment_intent": "pi_charge_refund"})
        dispatch_webhook_event(event)
        payment.refresh_from_db()
        assert payment.status == Payment.Status.REFUNDED

    def test_charge_refunded_marks_seminar_registration_refunded(self):
        athlete = AthleteProfileFactory()
        seminar = SeminarFactory()
        reg = SeminarRegistrationFactory(
            seminar=seminar,
            athlete=athlete,
            payment_status=SeminarRegistration.PaymentStatus.PAID,
            stripe_payment_intent_id="pi_reg_refund",
        )
        event = self._make_event("charge.refunded", {"payment_intent": "pi_reg_refund"})
        dispatch_webhook_event(event)
        reg.refresh_from_db()
        assert reg.payment_status == SeminarRegistration.PaymentStatus.REFUNDED

    def test_charge_refunded_without_pi_id_does_nothing(self):
        # charge with no payment_intent key
        event = self._make_event("charge.refunded", {"payment_intent": None})
        dispatch_webhook_event(event)  # must not raise
