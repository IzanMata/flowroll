"""Tests for payments models: Payment, StripeAcademyConfig, StripeWebhookEvent."""

from decimal import Decimal

import pytest

from factories import (
    AcademyFactory,
    AthleteProfileFactory,
    PaymentFactory,
    StripeAcademyConfigFactory,
    StripeWebhookEventFactory,
)
from payments.models import Payment, StripeAcademyConfig, StripeWebhookEvent


@pytest.mark.django_db
class TestStripeWebhookEvent:
    def test_str_unprocessed(self):
        evt = StripeWebhookEventFactory(
            stripe_event_id="evt_abc123", event_type="payment_intent.succeeded", processed=False
        )
        assert "✗" in str(evt)
        assert "payment_intent.succeeded" in str(evt)
        assert "evt_abc123" in str(evt)

    def test_str_processed(self):
        evt = StripeWebhookEventFactory(processed=True)
        assert "✓" in str(evt)

    def test_stripe_event_id_is_unique(self):
        from django.db import IntegrityError
        StripeWebhookEventFactory(stripe_event_id="evt_unique")
        with pytest.raises(IntegrityError):
            StripeWebhookEventFactory(stripe_event_id="evt_unique")

    def test_default_processed_is_false(self):
        evt = StripeWebhookEventFactory()
        assert evt.processed is False

    def test_ordering_newest_first(self):
        evt1 = StripeWebhookEventFactory()
        evt2 = StripeWebhookEventFactory()
        ids = list(StripeWebhookEvent.objects.values_list("id", flat=True))
        assert ids[0] == evt2.pk  # newest first

    def test_payload_stored_as_json(self):
        payload = {"type": "test.event", "data": {"object": {"id": "obj_123"}}}
        evt = StripeWebhookEventFactory(payload=payload)
        evt.refresh_from_db()
        assert evt.payload["data"]["object"]["id"] == "obj_123"


@pytest.mark.django_db
class TestStripeAcademyConfig:
    def test_str_not_connected(self):
        academy = AcademyFactory(name="Gracie Barra")
        config = StripeAcademyConfig.objects.create(academy=academy)
        assert "not connected" in str(config)
        assert "Gracie Barra" in str(config)

    def test_str_connected_charges_enabled(self):
        config = StripeAcademyConfigFactory(
            stripe_connect_account_id="acct_123",
            charges_enabled=True,
        )
        assert "✓" in str(config)

    def test_str_connected_charges_disabled(self):
        config = StripeAcademyConfigFactory(
            stripe_connect_account_id="acct_123",
            charges_enabled=False,
        )
        assert "⏳" in str(config)

    def test_is_ready_true_when_connected_and_charges_enabled(self):
        config = StripeAcademyConfigFactory(
            stripe_connect_account_id="acct_abc",
            charges_enabled=True,
        )
        assert config.is_ready is True

    def test_is_ready_false_when_no_account_id(self):
        academy = AcademyFactory()
        config = StripeAcademyConfig.objects.create(academy=academy)
        assert config.is_ready is False

    def test_is_ready_false_when_charges_disabled(self):
        config = StripeAcademyConfigFactory(
            stripe_connect_account_id="acct_abc",
            charges_enabled=False,
        )
        assert config.is_ready is False

    def test_unique_per_academy(self):
        from django.db import IntegrityError
        academy = AcademyFactory()
        StripeAcademyConfig.objects.create(academy=academy)
        with pytest.raises(IntegrityError):
            StripeAcademyConfig.objects.create(academy=academy)

    def test_default_currency_is_usd(self):
        academy = AcademyFactory()
        config = StripeAcademyConfig.objects.create(academy=academy)
        assert config.default_currency == "usd"


@pytest.mark.django_db
class TestPaymentModel:
    def test_str_representation(self):
        payment = PaymentFactory(
            payment_type=Payment.PaymentType.SEMINAR,
            amount_paid=Decimal("50.00"),
            currency="eur",
            status=Payment.Status.SUCCEEDED,
        )
        s = str(payment)
        assert "Seminar" in s
        assert "50.00" in s
        assert "eur" in s.lower() or "EUR" in s

    def test_default_status_is_pending(self):
        athlete = AthleteProfileFactory()
        academy = AcademyFactory()
        payment = Payment.objects.create(
            athlete=athlete,
            academy=academy,
            payment_type=Payment.PaymentType.SEMINAR,
            amount_paid=Decimal("50.00"),
            platform_fee=Decimal("5.00"),
            academy_net=Decimal("45.00"),
            stripe_payment_intent_id="pi_test_default_status",
        )
        assert payment.status == Payment.Status.PENDING

    def test_stripe_payment_intent_id_is_unique(self):
        from django.db import IntegrityError
        PaymentFactory(stripe_payment_intent_id="pi_unique_001")
        with pytest.raises(IntegrityError):
            PaymentFactory(stripe_payment_intent_id="pi_unique_001")

    def test_ordering_newest_first(self):
        academy = AcademyFactory()
        athlete = AthleteProfileFactory()
        p1 = PaymentFactory(
            academy=academy, athlete=athlete,
            stripe_payment_intent_id="pi_order_1",
        )
        p2 = PaymentFactory(
            academy=academy, athlete=athlete,
            stripe_payment_intent_id="pi_order_2",
        )
        ids = list(Payment.objects.filter(academy=academy).values_list("id", flat=True))
        assert ids[0] == p2.pk  # newest first

    def test_platform_fee_and_net_stored_correctly(self):
        payment = PaymentFactory(
            amount_paid=Decimal("100.00"),
            platform_fee=Decimal("10.00"),
            academy_net=Decimal("90.00"),
        )
        payment.refresh_from_db()
        assert payment.platform_fee == Decimal("10.00")
        assert payment.academy_net == Decimal("90.00")

    def test_payment_type_choices(self):
        for pt in (
            Payment.PaymentType.SUBSCRIPTION,
            Payment.PaymentType.SEMINAR,
            Payment.PaymentType.ONE_TIME_PLAN,
        ):
            p = PaymentFactory(payment_type=pt)
            assert p.payment_type == pt

    def test_status_choices(self):
        for status in (
            Payment.Status.PENDING,
            Payment.Status.SUCCEEDED,
            Payment.Status.FAILED,
            Payment.Status.REFUNDED,
        ):
            p = PaymentFactory(status=status)
            assert p.status == status

    def test_extra_metadata_defaults_to_empty_dict(self):
        athlete = AthleteProfileFactory()
        academy = AcademyFactory()
        payment = Payment.objects.create(
            athlete=athlete,
            academy=academy,
            payment_type=Payment.PaymentType.SEMINAR,
            amount_paid=Decimal("50.00"),
            platform_fee=Decimal("5.00"),
            academy_net=Decimal("45.00"),
            stripe_payment_intent_id="pi_meta_default",
        )
        assert payment.extra_metadata == {}

    def test_stripe_invoice_url_stored(self):
        payment = PaymentFactory(stripe_invoice_url="https://invoice.stripe.com/test123")
        payment.refresh_from_db()
        assert payment.stripe_invoice_url == "https://invoice.stripe.com/test123"
