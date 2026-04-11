"""
Tests for payments API views.

Stripe SDK calls are mocked at the service layer — tests verify HTTP
status codes, response shape, permission enforcement, and DB side-effects.
"""

import json
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import AcademyMembership
from factories import (
    AcademyFactory,
    AthleteProfileFactory,
    MembershipPlanFactory,
    PaymentFactory,
    SeminarFactory,
    SeminarRegistrationFactory,
    StripeAcademyConfigFactory,
    UserFactory,
)
from payments.models import Payment, StripeWebhookEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _owner_client(academy):
    """Return an APIClient authenticated as an owner of the given academy."""
    user = UserFactory()
    AthleteProfileFactory(user=user, academy=academy)
    AcademyMembership.objects.create(
        user=user, academy=academy, role=AcademyMembership.Role.OWNER, is_active=True
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _professor_client(academy):
    user = UserFactory()
    AthleteProfileFactory(user=user, academy=academy)
    AcademyMembership.objects.create(
        user=user, academy=academy, role=AcademyMembership.Role.PROFESSOR, is_active=True
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _athlete_client():
    athlete = AthleteProfileFactory()
    client = APIClient()
    client.force_authenticate(user=athlete.user)
    return client, athlete


# ---------------------------------------------------------------------------
# AcademyOnboardingView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAcademyOnboardingView:
    URL = "/api/v1/payments/academy-onboarding/"

    def test_owner_gets_onboarding_url(self):
        academy = AcademyFactory(country="Spain")
        client = _owner_client(academy)

        with patch(
            "payments.views.StripeConnectExpressService.create_account_and_onboarding_link",
            return_value="https://connect.stripe.com/onboard/test",
        ):
            response = client.post(self.URL, {
                "academy_id": academy.pk,
                "refresh_url": "https://app.example.com/refresh",
                "return_url": "https://app.example.com/return",
            }, format="json")

        assert response.status_code == 200
        assert response.data["onboarding_url"] == "https://connect.stripe.com/onboard/test"

    def test_non_owner_gets_403(self):
        academy = AcademyFactory()
        client = _professor_client(academy)

        response = client.post(self.URL, {
            "academy_id": academy.pk,
            "refresh_url": "https://app.example.com/refresh",
            "return_url": "https://app.example.com/return",
        }, format="json")

        assert response.status_code == 403

    def test_unauthenticated_gets_401(self):
        academy = AcademyFactory()
        client = APIClient()

        response = client.post(self.URL, {
            "academy_id": academy.pk,
            "refresh_url": "https://app.example.com/refresh",
            "return_url": "https://app.example.com/return",
        }, format="json")

        assert response.status_code == 401

    def test_invalid_academy_id_returns_400(self):
        academy = AcademyFactory()
        client = _owner_client(academy)

        response = client.post(self.URL, {
            "academy_id": 99999,
            "refresh_url": "https://app.example.com/refresh",
            "return_url": "https://app.example.com/return",
        }, format="json")

        assert response.status_code == 400

    def test_stripe_error_returns_502(self):
        import stripe
        academy = AcademyFactory(country="Spain")
        client = _owner_client(academy)

        with patch(
            "payments.views.StripeConnectExpressService.create_account_and_onboarding_link",
            side_effect=stripe.StripeError("Stripe error"),
        ):
            response = client.post(self.URL, {
                "academy_id": academy.pk,
                "refresh_url": "https://app.example.com/refresh",
                "return_url": "https://app.example.com/return",
            }, format="json")

        assert response.status_code == 502


# ---------------------------------------------------------------------------
# AcademyConnectStatusView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAcademyConnectStatusView:
    def _url(self, academy_id):
        return f"/api/v1/payments/academy/{academy_id}/connect-status/"

    def test_owner_can_view_status(self):
        academy = AcademyFactory()
        client = _owner_client(academy)

        with patch(
            "payments.views.StripeConnectExpressService.get_account_status",
            return_value={"status": "active", "charges_enabled": True, "payouts_enabled": True},
        ):
            response = client.get(self._url(academy.pk))

        assert response.status_code == 200
        assert response.data["status"] == "active"

    def test_professor_can_view_status(self):
        academy = AcademyFactory()
        client = _professor_client(academy)

        with patch(
            "payments.views.StripeConnectExpressService.get_account_status",
            return_value={"status": "not_connected", "charges_enabled": False, "payouts_enabled": False},
        ):
            response = client.get(self._url(academy.pk))

        assert response.status_code == 200

    def test_athlete_gets_403(self):
        academy = AcademyFactory()
        client, _ = _athlete_client()

        response = client.get(self._url(academy.pk))
        assert response.status_code == 403

    def test_nonexistent_academy_returns_404(self):
        academy = AcademyFactory()
        client = _owner_client(academy)
        response = client.get(self._url(99999))
        assert response.status_code == 404

    def test_unauthenticated_returns_401(self):
        academy = AcademyFactory()
        response = APIClient().get(self._url(academy.pk))
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# AcademyStripeDashboardView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAcademyStripeDashboardView:
    def _url(self, academy_id):
        return f"/api/v1/payments/academy/{academy_id}/dashboard/"

    def test_owner_gets_dashboard_url(self):
        academy = AcademyFactory()
        StripeAcademyConfigFactory(academy=academy, stripe_connect_account_id="acct_dash")
        client = _owner_client(academy)

        with patch(
            "payments.views.StripeConnectExpressService.create_login_link",
            return_value="https://dashboard.stripe.com/acct_dash",
        ):
            response = client.post(self._url(academy.pk))

        assert response.status_code == 200
        assert "dashboard_url" in response.data

    def test_professor_gets_403(self):
        academy = AcademyFactory()
        client = _professor_client(academy)
        response = client.post(self._url(academy.pk))
        assert response.status_code == 403

    def test_not_onboarded_returns_400(self):
        academy = AcademyFactory()
        client = _owner_client(academy)

        with patch(
            "payments.views.StripeConnectExpressService.create_login_link",
            side_effect=ValueError("not completed"),
        ):
            response = client.post(self._url(academy.pk))

        assert response.status_code == 400


# ---------------------------------------------------------------------------
# CheckoutSessionView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCheckoutSessionView:
    URL = "/api/v1/payments/checkout/"

    def test_monthly_plan_returns_checkout_url(self):
        config = StripeAcademyConfigFactory(
            stripe_connect_account_id="acct_checkout",
            charges_enabled=True,
        )
        plan = MembershipPlanFactory(
            academy=config.academy,
            plan_type="MONTHLY",
            stripe_price_id="price_monthly_abc",
        )
        client, athlete = _athlete_client()
        athlete.stripe_customer_id = "cus_test"
        athlete.save(update_fields=["stripe_customer_id"])

        with patch(
            "payments.views.StripeCheckoutService.create_subscription_checkout",
            return_value="https://checkout.stripe.com/sub_session",
        ):
            response = client.post(self.URL, {
                "plan_id": plan.pk,
                "success_url": "https://app.example.com/success",
                "cancel_url": "https://app.example.com/cancel",
            }, format="json")

        assert response.status_code == 200
        assert response.data["checkout_url"] == "https://checkout.stripe.com/sub_session"

    def test_class_pass_plan_uses_one_time_checkout(self):
        config = StripeAcademyConfigFactory(charges_enabled=True)
        plan = MembershipPlanFactory(
            academy=config.academy,
            plan_type="CLASS_PASS",
            price=Decimal("100.00"),
        )
        client, _ = _athlete_client()

        with patch(
            "payments.views.StripeCheckoutService.create_one_time_checkout",
            return_value="https://checkout.stripe.com/onetime",
        ) as mock_onetime:
            response = client.post(self.URL, {
                "plan_id": plan.pk,
                "success_url": "https://app.example.com/success",
                "cancel_url": "https://app.example.com/cancel",
            }, format="json")

        assert response.status_code == 200
        mock_onetime.assert_called_once()

    def test_unauthenticated_returns_401(self):
        plan = MembershipPlanFactory()
        response = APIClient().post(self.URL, {
            "plan_id": plan.pk,
            "success_url": "https://app.example.com/success",
            "cancel_url": "https://app.example.com/cancel",
        }, format="json")
        assert response.status_code == 401

    def test_academy_not_connected_returns_400(self):
        plan = MembershipPlanFactory(plan_type="MONTHLY", stripe_price_id="price_x")
        client, _ = _athlete_client()

        with patch(
            "payments.views.StripeCheckoutService.create_subscription_checkout",
            side_effect=ValueError("has not started Stripe onboarding"),
        ):
            response = client.post(self.URL, {
                "plan_id": plan.pk,
                "success_url": "https://app.example.com/success",
                "cancel_url": "https://app.example.com/cancel",
            }, format="json")

        assert response.status_code == 400
        assert "onboarding" in response.data["detail"].lower()

    def test_stripe_error_returns_502(self):
        import stripe
        config = StripeAcademyConfigFactory(charges_enabled=True)
        plan = MembershipPlanFactory(
            academy=config.academy,
            plan_type="CLASS_PASS",
            price=Decimal("50.00"),
        )
        client, _ = _athlete_client()

        with patch(
            "payments.views.StripeCheckoutService.create_one_time_checkout",
            side_effect=stripe.StripeError("Network error"),
        ):
            response = client.post(self.URL, {
                "plan_id": plan.pk,
                "success_url": "https://app.example.com/success",
                "cancel_url": "https://app.example.com/cancel",
            }, format="json")

        assert response.status_code == 502

    def test_missing_success_url_returns_400(self):
        plan = MembershipPlanFactory()
        client, _ = _athlete_client()
        response = client.post(self.URL, {
            "plan_id": plan.pk,
            "cancel_url": "https://app.example.com/cancel",
        }, format="json")
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# SeminarCheckoutView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSeminarCheckoutView:
    URL = "/api/v1/payments/seminar-checkout/"

    def test_paid_seminar_returns_checkout_url(self):
        config = StripeAcademyConfigFactory(charges_enabled=True)
        seminar = SeminarFactory(academy=config.academy, price=Decimal("50.00"))
        client, athlete = _athlete_client()
        athlete.stripe_customer_id = "cus_seminar"
        athlete.save(update_fields=["stripe_customer_id"])

        with patch(
            "payments.views.StripeCheckoutService.create_seminar_checkout",
            return_value="https://checkout.stripe.com/seminar_session",
        ):
            response = client.post(self.URL, {
                "seminar_id": seminar.pk,
                "success_url": "https://app.example.com/success",
                "cancel_url": "https://app.example.com/cancel",
            }, format="json")

        assert response.status_code == 201
        assert response.data["checkout_url"] == "https://checkout.stripe.com/seminar_session"

    def test_free_seminar_skips_stripe_and_returns_201(self):
        academy = AcademyFactory()
        seminar = SeminarFactory(academy=academy, price=Decimal("0.00"))
        client, _ = _athlete_client()

        with patch("payments.views.StripeCheckoutService.create_seminar_checkout") as mock_checkout:
            response = client.post(self.URL, {
                "seminar_id": seminar.pk,
                "success_url": "https://app.example.com/success",
                "cancel_url": "https://app.example.com/cancel",
            }, format="json")

        assert response.status_code == 201
        assert response.data["checkout_url"] is None
        mock_checkout.assert_not_called()

    def test_duplicate_registration_returns_400(self):
        seminar = SeminarFactory()
        client, athlete = _athlete_client()
        # Register first time
        SeminarRegistrationFactory(seminar=seminar, athlete=athlete)

        response = client.post(self.URL, {
            "seminar_id": seminar.pk,
            "success_url": "https://app.example.com/success",
            "cancel_url": "https://app.example.com/cancel",
        }, format="json")

        assert response.status_code == 400

    def test_unauthenticated_returns_401(self):
        seminar = SeminarFactory()
        response = APIClient().post(self.URL, {
            "seminar_id": seminar.pk,
            "success_url": "https://app.example.com/success",
            "cancel_url": "https://app.example.com/cancel",
        }, format="json")
        assert response.status_code == 401

    def test_registration_status_in_response(self):
        academy = AcademyFactory()
        seminar = SeminarFactory(academy=academy, price=Decimal("0.00"))
        client, _ = _athlete_client()

        response = client.post(self.URL, {
            "seminar_id": seminar.pk,
            "success_url": "https://app.example.com/success",
            "cancel_url": "https://app.example.com/cancel",
        }, format="json")

        assert response.status_code == 201
        assert "registration_status" in response.data


# ---------------------------------------------------------------------------
# CustomerPortalView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCustomerPortalView:
    URL = "/api/v1/payments/portal/"

    def test_returns_portal_url(self):
        client, athlete = _athlete_client()
        athlete.stripe_customer_id = "cus_portal"
        athlete.save(update_fields=["stripe_customer_id"])

        with patch(
            "payments.views.StripeCustomerService.create_portal_session",
            return_value="https://billing.stripe.com/session/test",
        ):
            response = client.post(self.URL, {
                "return_url": "https://app.example.com/settings",
            }, format="json")

        assert response.status_code == 200
        assert response.data["portal_url"] == "https://billing.stripe.com/session/test"

    def test_unauthenticated_returns_401(self):
        response = APIClient().post(self.URL, {
            "return_url": "https://app.example.com",
        }, format="json")
        assert response.status_code == 401

    def test_missing_return_url_returns_400(self):
        client, _ = _athlete_client()
        response = client.post(self.URL, {}, format="json")
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# PaymentListView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPaymentListView:
    URL = "/api/v1/payments/history/"

    def test_athlete_sees_own_payments(self):
        client, athlete = _athlete_client()
        PaymentFactory(athlete=athlete, stripe_payment_intent_id="pi_own_1")
        PaymentFactory(athlete=athlete, stripe_payment_intent_id="pi_own_2")
        # Another athlete's payment — should not appear
        PaymentFactory(stripe_payment_intent_id="pi_other_1")

        response = client.get(self.URL)

        assert response.status_code == 200
        ids = [p["stripe_payment_intent_id"] for p in response.data["results"]]
        assert "pi_own_1" in ids
        assert "pi_own_2" in ids
        assert "pi_other_1" not in ids

    def test_owner_can_filter_by_academy(self):
        academy = AcademyFactory()
        client = _owner_client(academy)
        athlete = AthleteProfileFactory()
        PaymentFactory(academy=academy, athlete=athlete, stripe_payment_intent_id="pi_acad_1")
        PaymentFactory(stripe_payment_intent_id="pi_other_acad")

        response = client.get(self.URL, {"academy": academy.pk})

        assert response.status_code == 200
        ids = [p["stripe_payment_intent_id"] for p in response.data["results"]]
        assert "pi_acad_1" in ids
        assert "pi_other_acad" not in ids

    def test_athlete_cannot_filter_other_academy(self):
        academy = AcademyFactory()
        client, _ = _athlete_client()

        response = client.get(self.URL, {"academy": academy.pk})
        assert response.status_code == 403

    def test_filter_by_payment_type(self):
        client, athlete = _athlete_client()
        PaymentFactory(
            athlete=athlete, payment_type=Payment.PaymentType.SEMINAR,
            stripe_payment_intent_id="pi_seminar_type",
        )
        PaymentFactory(
            athlete=athlete, payment_type=Payment.PaymentType.SUBSCRIPTION,
            stripe_payment_intent_id="pi_sub_type",
        )

        response = client.get(self.URL, {"payment_type": "SEMINAR"})

        ids = [p["stripe_payment_intent_id"] for p in response.data["results"]]
        assert "pi_seminar_type" in ids
        assert "pi_sub_type" not in ids

    def test_filter_by_status(self):
        client, athlete = _athlete_client()
        PaymentFactory(
            athlete=athlete, status=Payment.Status.REFUNDED,
            stripe_payment_intent_id="pi_refunded_status",
        )
        PaymentFactory(
            athlete=athlete, status=Payment.Status.SUCCEEDED,
            stripe_payment_intent_id="pi_succeeded_status",
        )

        response = client.get(self.URL, {"status": "REFUNDED"})

        ids = [p["stripe_payment_intent_id"] for p in response.data["results"]]
        assert "pi_refunded_status" in ids
        assert "pi_succeeded_status" not in ids

    def test_unauthenticated_returns_401(self):
        response = APIClient().get(self.URL)
        assert response.status_code == 401

    def test_response_includes_invoice_url(self):
        client, athlete = _athlete_client()
        PaymentFactory(
            athlete=athlete,
            stripe_invoice_url="https://invoice.stripe.com/pdf/test123",
            stripe_payment_intent_id="pi_invoice_url",
        )
        response = client.get(self.URL)
        payment_data = next(
            p for p in response.data["results"]
            if p["stripe_payment_intent_id"] == "pi_invoice_url"
        )
        assert payment_data["stripe_invoice_url"] == "https://invoice.stripe.com/pdf/test123"

    def test_athlete_with_no_profile_returns_empty(self):
        user = UserFactory()
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(self.URL)
        assert response.status_code == 200
        assert response.data["results"] == []


# ---------------------------------------------------------------------------
# PaymentMethodListView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPaymentMethodListView:
    URL = "/api/v1/payments/payment-methods/"

    def test_returns_masked_card_list(self):
        client, athlete = _athlete_client()
        athlete.stripe_customer_id = "cus_cards"
        athlete.save(update_fields=["stripe_customer_id"])

        mock_customer = {
            "invoice_settings": {"default_payment_method": "pm_123"}
        }
        mock_methods = {
            "data": [{
                "id": "pm_123",
                "card": {"brand": "visa", "last4": "4242", "exp_month": 12, "exp_year": 2030},
            }]
        }
        with patch("stripe.Customer.retrieve", return_value=mock_customer), \
             patch("stripe.PaymentMethod.list", return_value=mock_methods):
            response = client.get(self.URL)

        assert response.status_code == 200
        assert len(response.data["results"]) == 1
        card = response.data["results"][0]
        assert card["last4"] == "4242"
        assert card["brand"] == "visa"
        assert card["is_default"] is True

    def test_no_stripe_customer_returns_empty_list(self):
        client, athlete = _athlete_client()
        athlete.stripe_customer_id = ""
        athlete.save(update_fields=["stripe_customer_id"])
        response = client.get(self.URL)
        assert response.status_code == 200
        assert response.data["results"] == []

    def test_unauthenticated_returns_401(self):
        response = APIClient().get(self.URL)
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# StripeWebhookView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStripeWebhookView:
    URL = "/api/v1/payments/webhooks/stripe/"

    def _post_event(self, event_type, obj, settings_fixture=None):
        """Post a Stripe event to the webhook endpoint (signature bypassed in test)."""
        client = APIClient()
        event = {"id": f"evt_{event_type.replace('.', '_')}_test", "type": event_type, "data": {"object": obj}}
        with patch("stripe.Webhook.construct_event", return_value=event):
            return client.post(
                self.URL,
                data=json.dumps(event),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=1,v1=fakesig",
            )

    def test_valid_event_returns_200(self):
        athlete = AthleteProfileFactory()
        academy = AcademyFactory()
        response = self._post_event("payment_intent.payment_failed", {
            "id": "pi_webhook_fail",
            "last_payment_error": {"message": "card_declined"},
        })
        assert response.status_code == 200

    def test_invalid_signature_returns_400(self, settings):
        import stripe
        settings.STRIPE_WEBHOOK_SECRET = "whsec_test_secret"
        client = APIClient()
        with patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe.error.SignatureVerificationError("bad sig", "sig_header"),
        ):
            response = client.post(
                self.URL,
                data='{"id":"evt_bad","type":"test"}',
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=1,v1=badsig",
            )
        assert response.status_code == 400

    def test_duplicate_event_returns_200_without_reprocessing(self):
        athlete = AthleteProfileFactory()
        academy = AcademyFactory()
        pi_id = "pi_dedup_webhook"
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_dup_test",
            event_type="payment_intent.succeeded",
            payload={},
            processed=True,
        )
        client = APIClient()
        event = {
            "id": "evt_dup_test",
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": pi_id, "metadata": {}}},
        }
        with patch("stripe.Webhook.construct_event", return_value=event):
            response = client.post(
                self.URL,
                data=json.dumps(event),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="t=1,v1=fakesig",
            )

        assert response.status_code == 200
        assert response.data["detail"] == "already processed"
        # No Payment record should have been created
        assert not Payment.objects.filter(stripe_payment_intent_id=pi_id).exists()

    def test_event_is_recorded_in_db(self):
        athlete = AthleteProfileFactory()
        academy = AcademyFactory()
        response = self._post_event("payment_intent.payment_failed", {
            "id": "pi_recorded",
            "last_payment_error": {},
        })
        assert response.status_code == 200
        assert StripeWebhookEvent.objects.filter(
            event_type="payment_intent.payment_failed", processed=True
        ).exists()

    def test_payment_intent_succeeded_creates_payment(self):
        athlete = AthleteProfileFactory()
        academy = AcademyFactory()
        response = self._post_event("payment_intent.succeeded", {
            "id": "pi_webhook_success",
            "amount_received": 5000,
            "currency": "eur",
            "metadata": {
                "purpose": "one_time_plan",
                "athlete_id": str(athlete.pk),
                "academy_id": str(academy.pk),
                "platform_fee_cents": "500",
            },
        })
        assert response.status_code == 200
        assert Payment.objects.filter(stripe_payment_intent_id="pi_webhook_success").exists()

    def test_no_webhook_secret_accepts_json_body(self, settings):
        settings.STRIPE_WEBHOOK_SECRET = ""
        client = APIClient()
        event = {
            "id": "evt_nosecret",
            "type": "payment_intent.payment_failed",
            "data": {"object": {"id": "pi_nosec", "last_payment_error": {}}},
        }
        response = client.post(
            self.URL,
            data=json.dumps(event),
            content_type="application/json",
        )
        assert response.status_code == 200
