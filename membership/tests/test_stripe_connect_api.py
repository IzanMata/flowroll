"""
Tests for Stripe Connect API endpoints - comprehensive test suite for marketplace functionality.

Tests all Stripe Connect endpoints:
- Create Connected Account
- Create Onboarding Link
- Connected Account Status
- Create Dashboard Link
- Marketplace Enrollment
- Marketplace Seminar Payments
- Academy Earnings
- Marketplace Transactions
- Configure Commission
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock
import pytest
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import AcademyMembership
from membership.models import (
    MembershipPlan, StripeConnectedAccount, PlatformCommission,
    MarketplaceTransaction, AcademyEarnings, Seminar
)
from factories import (
    AcademyFactory, MembershipPlanFactory, AthleteProfileFactory,
    SeminarFactory, UserFactory
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def owner_user(db):
    return UserFactory(username="owner@test.com", email="owner@test.com")


@pytest.fixture
def member_user(db):
    return UserFactory(username="member@test.com", email="member@test.com")


@pytest.fixture
def other_user(db):
    return UserFactory(username="other@test.com", email="other@test.com")


@pytest.fixture
def academy(db):
    return AcademyFactory(name="Test BJJ Academy", email="academy@test.com")


@pytest.fixture
def other_academy(db):
    return AcademyFactory(name="Other Academy", email="other@test.com")


@pytest.fixture
def owner_membership(db, owner_user, academy):
    return AcademyMembership.objects.create(
        user=owner_user,
        academy=academy,
        role=AcademyMembership.Role.OWNER,
        is_active=True
    )


@pytest.fixture
def member_membership(db, member_user, academy):
    return AcademyMembership.objects.create(
        user=member_user,
        academy=academy,
        role=AcademyMembership.Role.STUDENT,
        is_active=True
    )


@pytest.fixture
def membership_plan(db, academy):
    return MembershipPlanFactory(
        academy=academy,
        name="Monthly Membership",
        plan_type=MembershipPlan.PlanType.MONTHLY,
        price=Decimal("100.00"),
        is_active=True
    )


@pytest.fixture
def connected_account(db, academy):
    return StripeConnectedAccount.objects.create(
        academy=academy,
        stripe_account_id="acct_test123",
        account_type=StripeConnectedAccount.AccountType.EXPRESS,
        status=StripeConnectedAccount.Status.ENABLED,
        details_submitted=True,
        charges_enabled=True,
        payouts_enabled=True,
        business_name="Test Academy"
    )


@pytest.fixture
def pending_connected_account(db, academy):
    return StripeConnectedAccount.objects.create(
        academy=academy,
        stripe_account_id="acct_pending123",
        account_type=StripeConnectedAccount.AccountType.EXPRESS,
        status=StripeConnectedAccount.Status.PENDING,
        details_submitted=False,
        charges_enabled=False,
        payouts_enabled=False
    )


@pytest.fixture
def platform_commission(db):
    return PlatformCommission.objects.create(
        academy=None,  # Global default
        commission_type=PlatformCommission.CommissionType.PERCENTAGE,
        percentage_rate=Decimal("0.10"),  # 10%
        min_commission=Decimal("0.50")
    )


@pytest.fixture
def owner_client(owner_user):
    client = APIClient()
    refresh = RefreshToken.for_user(owner_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


@pytest.fixture
def member_client(member_user):
    client = APIClient()
    refresh = RefreshToken.for_user(member_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


@pytest.fixture
def other_client(other_user):
    client = APIClient()
    refresh = RefreshToken.for_user(other_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


# ─── Create Connected Account Tests ──────────────────────────────────────────


class TestCreateConnectedAccount:
    url = "/api/v1/membership/connect/create-account/"

    @patch('membership.services.stripe.Account.create')
    def test_create_connected_account_success(
        self, mock_stripe_create, owner_client, academy, owner_membership
    ):
        """Test successful creation of Stripe connected account."""
        # Mock Stripe response
        mock_stripe_create.return_value = MagicMock(id="acct_new123")

        response = owner_client.post(self.url, {
            "academy": academy.id,
            "country": "US"
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["stripe_account_id"] == "acct_new123"
        assert response.data["academy"] == academy.id
        assert response.data["account_type"] == "EXPRESS"
        assert response.data["status"] == "PENDING"

        # Verify account was created in database
        account = StripeConnectedAccount.objects.get(academy=academy)
        assert account.stripe_account_id == "acct_new123"

        # Verify Stripe API was called correctly
        mock_stripe_create.assert_called_once_with(
            type="express",
            country="US",
            email=academy.email,
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
            business_type="company",
            company={"name": academy.name},
            metadata={
                "academy_id": str(academy.id),
                "academy_name": academy.name,
                "source": "flowroll"
            }
        )

    def test_create_connected_account_not_owner(
        self, member_client, academy, member_membership
    ):
        """Test that non-owners cannot create connected accounts."""
        response = member_client.post(self.url, {
            "academy": academy.id,
            "country": "US"
        })

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only academy owners" in response.data["detail"]

    def test_create_connected_account_unauthenticated(self, academy):
        """Test unauthenticated access is rejected."""
        client = APIClient()
        response = client.post(self.url, {
            "academy": academy.id,
            "country": "US"
        })

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_connected_account_invalid_academy(self, owner_client):
        """Test handling of invalid academy ID."""
        response = owner_client.post(self.url, {
            "academy": 99999,
            "country": "US"
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch('membership.services.stripe.Account.create')
    def test_create_connected_account_already_exists(
        self, mock_stripe_create, owner_client, academy, owner_membership, connected_account
    ):
        """Test that existing connected account is returned without creating new one."""
        response = owner_client.post(self.url, {
            "academy": academy.id,
            "country": "US"
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["stripe_account_id"] == connected_account.stripe_account_id

        # Stripe should not be called if account already exists
        mock_stripe_create.assert_not_called()

    @patch('membership.services.stripe.Account.create')
    def test_create_connected_account_stripe_error(
        self, mock_stripe_create, owner_client, academy, owner_membership
    ):
        """Test handling of Stripe API errors."""
        import stripe
        mock_stripe_create.side_effect = stripe.error.StripeError("API Error")

        response = owner_client.post(self.url, {
            "academy": academy.id,
            "country": "US"
        })

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Failed to create Stripe account" in response.data["detail"]


# ─── Create Onboarding Link Tests ────────────────────────────────────────────


class TestCreateOnboardingLink:
    url = "/api/v1/membership/connect/onboarding-link/"

    @patch('membership.services.stripe.AccountLink.create')
    def test_create_onboarding_link_success(
        self, mock_stripe_create, owner_client, academy, owner_membership, pending_connected_account
    ):
        """Test successful creation of onboarding link."""
        mock_stripe_create.return_value = MagicMock(url="https://connect.stripe.com/onboard/123")

        response = owner_client.post(
            f"{self.url}?academy={academy.id}",
            {
                "return_url": "https://example.com/return",
                "refresh_url": "https://example.com/refresh"
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert "https://connect.stripe.com/onboard/123" in response.data["onboarding_url"]

        # Verify Stripe API was called correctly
        mock_stripe_create.assert_called_once_with(
            account="acct_pending123",
            refresh_url="https://example.com/refresh",
            return_url="https://example.com/return",
            type="account_onboarding"
        )

    def test_create_onboarding_link_no_academy_param(self, owner_client):
        """Test that academy parameter is required."""
        response = owner_client.post(self.url, {
            "return_url": "https://example.com/return",
            "refresh_url": "https://example.com/refresh"
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Academy ID required" in response.data["detail"]

    def test_create_onboarding_link_no_connected_account(
        self, owner_client, academy, owner_membership
    ):
        """Test handling when no connected account exists."""
        response = owner_client.post(
            f"{self.url}?academy={academy.id}",
            {
                "return_url": "https://example.com/return",
                "refresh_url": "https://example.com/refresh"
            }
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "No Stripe Connect account found" in response.data["detail"]

    def test_create_onboarding_link_not_owner(
        self, member_client, academy, member_membership, pending_connected_account
    ):
        """Test that non-owners cannot create onboarding links."""
        response = member_client.post(
            f"{self.url}?academy={academy.id}",
            {
                "return_url": "https://example.com/return",
                "refresh_url": "https://example.com/refresh"
            }
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only academy owners" in response.data["detail"]


# ─── Connected Account Status Tests ───────────────────────────────────────────


class TestConnectedAccountStatus:
    url = "/api/v1/membership/connect/status/"

    @patch('membership.services.StripeConnectService.sync_account_status')
    def test_get_status_success(
        self, mock_sync, member_client, academy, member_membership, connected_account
    ):
        """Test successful status retrieval."""
        mock_sync.return_value = connected_account

        response = member_client.get(f"{self.url}?academy={academy.id}")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["stripe_account_id"] == "acct_test123"
        assert response.data["status"] == "ENABLED"
        assert response.data["charges_enabled"] is True
        assert response.data["payouts_enabled"] is True

    def test_get_status_no_connected_account(
        self, member_client, academy, member_membership
    ):
        """Test status when no connected account exists."""
        response = member_client.get(f"{self.url}?academy={academy.id}")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["connected"] is False

    def test_get_status_not_member(
        self, other_client, academy, connected_account
    ):
        """Test that non-members cannot view status."""
        response = other_client.get(f"{self.url}?academy={academy.id}")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Access denied" in response.data["detail"]

    def test_get_status_no_academy_param(self, member_client):
        """Test that academy parameter is required."""
        response = member_client.get(self.url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Academy ID required" in response.data["detail"]


# ─── Create Dashboard Link Tests ──────────────────────────────────────────────


class TestCreateDashboardLink:
    url = "/api/v1/membership/connect/dashboard-link/"

    @patch('membership.services.stripe.Account.create_login_link')
    def test_create_dashboard_link_success(
        self, mock_stripe_create, owner_client, academy, owner_membership, connected_account
    ):
        """Test successful creation of dashboard link."""
        mock_stripe_create.return_value = MagicMock(url="https://connect.stripe.com/dashboard/123")

        response = owner_client.post(f"{self.url}?academy={academy.id}")

        assert response.status_code == status.HTTP_200_OK
        assert "https://connect.stripe.com/dashboard/123" in response.data["dashboard_url"]

        mock_stripe_create.assert_called_once_with("acct_test123")

    def test_create_dashboard_link_not_onboarded(
        self, owner_client, academy, owner_membership, pending_connected_account
    ):
        """Test dashboard link creation for non-onboarded account."""
        response = owner_client.post(f"{self.url}?academy={academy.id}")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "complete onboarding" in response.data["detail"]

    def test_create_dashboard_link_not_owner(
        self, member_client, academy, member_membership, connected_account
    ):
        """Test that non-owners cannot access dashboard."""
        response = member_client.post(f"{self.url}?academy={academy.id}")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only academy owners" in response.data["detail"]


# ─── Marketplace Enrollment Tests ────────────────────────────────────────────


class TestMarketplaceEnrollment:
    url = "/api/v1/membership/marketplace-enroll/"

    @patch('membership.services.stripe.PaymentIntent.create')
    @patch('membership.services.StripeCustomerService.get_or_create_customer')
    def test_marketplace_enroll_success(
        self, mock_customer, mock_payment_intent, member_client, academy,
        membership_plan, connected_account, platform_commission
    ):
        """Test successful marketplace enrollment."""
        # Mock customer service
        mock_customer.return_value = MagicMock(stripe_customer_id="cus_test123")

        # Mock payment intent
        mock_payment_intent.return_value = MagicMock(
            id="pi_test123",
            client_secret="pi_test123_secret_123"
        )

        response = member_client.post(self.url, {
            "academy": academy.id,
            "plan": membership_plan.id,
            "payment_method_id": "pm_test123"
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["academy_id"] == academy.id
        assert "subscription" in response.data
        assert "marketplace_transaction" in response.data
        assert "client_secret" in response.data
        assert "platform_fee" in response.data
        assert "academy_receives" in response.data

        # Verify marketplace transaction was created
        transaction = MarketplaceTransaction.objects.get(
            stripe_payment_intent_id="pi_test123"
        )
        assert transaction.academy == academy
        assert transaction.gross_amount == Decimal("100.00")
        assert transaction.platform_fee == Decimal("10.00")  # 10% of 100
        assert transaction.net_amount == Decimal("90.00")

    def test_marketplace_enroll_no_connected_account(
        self, member_client, academy, membership_plan
    ):
        """Test enrollment when academy has no connected account."""
        response = member_client.post(self.url, {
            "academy": academy.id,
            "plan": membership_plan.id
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Stripe setup" in response.data["detail"]

    def test_marketplace_enroll_plan_wrong_academy(
        self, member_client, academy, other_academy, connected_account
    ):
        """Test enrollment with plan from different academy."""
        other_plan = MembershipPlanFactory(academy=other_academy)

        response = member_client.post(self.url, {
            "academy": academy.id,
            "plan": other_plan.id
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "does not belong" in response.data["detail"]

    def test_marketplace_enroll_unauthenticated(self, academy, membership_plan):
        """Test unauthenticated enrollment."""
        client = APIClient()
        response = client.post(self.url, {
            "academy": academy.id,
            "plan": membership_plan.id
        })

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── Marketplace Seminar Payment Tests ───────────────────────────────────────


class TestMarketplaceSeminarPayment:
    url = "/api/v1/membership/marketplace-seminars/register/"

    @patch('membership.services.SeminarService.register_with_stripe_payment')
    def test_seminar_marketplace_payment_success(
        self, mock_register, member_client, member_user, academy
    ):
        """Test successful marketplace seminar payment."""
        # Create athlete profile
        athlete = AthleteProfileFactory(user=member_user)

        # Create seminar
        seminar = SeminarFactory(academy=academy)

        # Mock service response
        mock_register.return_value = {
            "registration": MagicMock(id=1, status="CONFIRMED", payment_status="PAID"),
            "marketplace_transaction": MagicMock(),
            "client_secret": "pi_test_secret",
            "platform_fee": Decimal("5.00"),
            "academy_receives": Decimal("45.00")
        }

        response = member_client.post(self.url, {"seminar": seminar.id})

        assert response.status_code == status.HTTP_201_CREATED
        assert "registration" in response.data
        assert "marketplace_transaction" in response.data
        assert "client_secret" in response.data

    def test_seminar_marketplace_payment_no_athlete_profile(
        self, member_client, academy
    ):
        """Test seminar payment when user has no athlete profile."""
        seminar = SeminarFactory(academy=academy)

        response = member_client.post(self.url, {"seminar": seminar.id})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "athlete profile" in response.data["detail"]


# ─── Academy Earnings Tests ───────────────────────────────────────────────────


class TestAcademyEarnings:
    url = "/api/v1/membership/earnings/"

    def test_get_earnings_monthly_success(
        self, member_client, academy, member_membership, connected_account
    ):
        """Test successful monthly earnings retrieval."""
        # Create earnings record
        earnings = AcademyEarnings.objects.create(
            academy=academy,
            connected_account=connected_account,
            year=2024,
            month=3,
            total_gross=Decimal("1000.00"),
            total_platform_fees=Decimal("100.00"),
            total_stripe_fees=Decimal("30.00"),
            total_net=Decimal("870.00")
        )

        response = member_client.get(
            f"{self.url}?academy={academy.id}&year=2024&month=3"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_gross"] == "1000.00"
        assert response.data["total_platform_fees"] == "100.00"
        assert response.data["total_net"] == "870.00"

    def test_get_earnings_yearly_success(
        self, member_client, academy, member_membership, connected_account
    ):
        """Test successful yearly earnings retrieval."""
        # Create multiple earnings records
        for month in range(1, 4):
            AcademyEarnings.objects.create(
                academy=academy,
                connected_account=connected_account,
                year=2024,
                month=month,
                total_gross=Decimal("1000.00"),
                total_platform_fees=Decimal("100.00"),
                total_net=Decimal("900.00")
            )

        response = member_client.get(f"{self.url}?academy={academy.id}&year=2024")

        assert response.status_code == status.HTTP_200_OK
        assert "total_gross" in response.data

    def test_get_earnings_no_data(
        self, member_client, academy, member_membership
    ):
        """Test earnings retrieval when no data exists."""
        response = member_client.get(
            f"{self.url}?academy={academy.id}&year=2024&month=3"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_gross"] == "0.00"
        assert response.data["total_transactions"] == 0

    def test_get_earnings_not_member(
        self, other_client, academy, connected_account
    ):
        """Test that non-members cannot view earnings."""
        response = other_client.get(f"{self.url}?academy={academy.id}")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_earnings_invalid_params(
        self, member_client, academy, member_membership
    ):
        """Test earnings with invalid year/month parameters."""
        response = member_client.get(
            f"{self.url}?academy={academy.id}&year=invalid&month=invalid"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid year or month" in response.data["detail"]


# ─── Marketplace Transactions List Tests ─────────────────────────────────────


class TestMarketplaceTransactionsList:
    url = "/api/v1/membership/marketplace-transactions/"

    def test_list_transactions_success(
        self, member_client, academy, member_membership, connected_account
    ):
        """Test successful transaction list retrieval."""
        # Create test transactions
        from membership.models import StripeCustomer
        customer = StripeCustomer.objects.create(
            user=member_user, stripe_customer_id="cus_test123"
        )

        transaction = MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_test123",
            stripe_customer=customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=MarketplaceTransaction.TransactionType.ONE_TIME,
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),
            net_amount=Decimal("90.00")
        )

        response = member_client.get(f"{self.url}?academy={academy.id}")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["stripe_payment_intent_id"] == "pi_test123"

    def test_list_transactions_not_member(
        self, other_client, academy, connected_account
    ):
        """Test that non-members cannot view transactions."""
        response = other_client.get(f"{self.url}?academy={academy.id}")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_transactions_no_academy_param(self, member_client):
        """Test that academy parameter is required."""
        response = member_client.get(self.url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Academy ID required" in response.data["detail"]


# ─── Configure Commission Tests ───────────────────────────────────────────────


class TestConfigureCommission:
    url = "/api/v1/membership/configure-commission/"

    def test_configure_academy_commission_success(
        self, owner_client, academy, owner_membership
    ):
        """Test successful academy commission configuration."""
        response = owner_client.post(self.url, {
            "academy": academy.id,
            "commission_type": "PERCENTAGE",
            "percentage_rate": "0.15",  # 15%
            "min_commission": "1.00"
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["commission_type"] == "PERCENTAGE"
        assert response.data["percentage_rate"] == "0.1500"
        assert response.data["academy"] == academy.id

    def test_configure_global_commission_superuser(
        self, owner_user, academy
    ):
        """Test global commission configuration by superuser."""
        owner_user.is_superuser = True
        owner_user.save()

        client = APIClient()
        refresh = RefreshToken.for_user(owner_user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = client.post(self.url, {
            "commission_type": "PERCENTAGE",
            "percentage_rate": "0.12"
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["academy"] is None

    def test_configure_commission_not_owner(
        self, member_client, academy, member_membership
    ):
        """Test that non-owners cannot configure commission."""
        response = member_client.post(self.url, {
            "academy": academy.id,
            "commission_type": "PERCENTAGE",
            "percentage_rate": "0.15"
        })

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only academy owners" in response.data["detail"]

    def test_configure_global_commission_not_superuser(
        self, owner_client
    ):
        """Test that non-superusers cannot configure global commission."""
        response = owner_client.post(self.url, {
            "commission_type": "PERCENTAGE",
            "percentage_rate": "0.12"
        })

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only superusers" in response.data["detail"]

    def test_configure_commission_fixed_amount(
        self, owner_client, academy, owner_membership
    ):
        """Test fixed amount commission configuration."""
        response = owner_client.post(self.url, {
            "academy": academy.id,
            "commission_type": "FIXED_AMOUNT",
            "fixed_amount": "5.00"
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["commission_type"] == "FIXED_AMOUNT"
        assert response.data["fixed_amount"] == "5.00"

    def test_configure_commission_hybrid(
        self, owner_client, academy, owner_membership
    ):
        """Test hybrid commission configuration."""
        response = owner_client.post(self.url, {
            "academy": academy.id,
            "commission_type": "HYBRID",
            "percentage_rate": "0.05",
            "fixed_amount": "2.00"
        })

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["commission_type"] == "HYBRID"
        assert response.data["percentage_rate"] == "0.0500"
        assert response.data["fixed_amount"] == "2.00"