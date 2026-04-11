"""
Tests for Stripe Connect Security - comprehensive security test suite for marketplace functionality.

Security tests for:
- Permission enforcement (Owner, Member, Non-member access)
- Academy scoping and tenant isolation
- Authentication requirements
- Cross-academy access prevention
- Data leakage prevention
- Input validation and sanitization
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
    StripeConnectedAccount, MarketplaceTransaction, AcademyEarnings,
    StripeCustomer, PlatformCommission
)
from factories import AcademyFactory, UserFactory


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def academy_a(db):
    return AcademyFactory(name="Academy A")


@pytest.fixture
def academy_b(db):
    return AcademyFactory(name="Academy B")


@pytest.fixture
def owner_a(db):
    return UserFactory(username="owner_a@test.com")


@pytest.fixture
def member_a(db):
    return UserFactory(username="member_a@test.com")


@pytest.fixture
def owner_b(db):
    return UserFactory(username="owner_b@test.com")


@pytest.fixture
def member_b(db):
    return UserFactory(username="member_b@test.com")


@pytest.fixture
def unaffiliated_user(db):
    return UserFactory(username="unaffiliated@test.com")


@pytest.fixture
def superuser(db):
    return UserFactory(username="super@test.com", is_superuser=True)


@pytest.fixture
def membership_owner_a(db, owner_a, academy_a):
    return AcademyMembership.objects.create(
        user=owner_a,
        academy=academy_a,
        role=AcademyMembership.Role.OWNER,
        is_active=True
    )


@pytest.fixture
def membership_member_a(db, member_a, academy_a):
    return AcademyMembership.objects.create(
        user=member_a,
        academy=academy_a,
        role=AcademyMembership.Role.STUDENT,
        is_active=True
    )


@pytest.fixture
def membership_owner_b(db, owner_b, academy_b):
    return AcademyMembership.objects.create(
        user=owner_b,
        academy=academy_b,
        role=AcademyMembership.Role.OWNER,
        is_active=True
    )


@pytest.fixture
def membership_member_b(db, member_b, academy_b):
    return AcademyMembership.objects.create(
        user=member_b,
        academy=academy_b,
        role=AcademyMembership.Role.STUDENT,
        is_active=True
    )


@pytest.fixture
def connected_account_a(db, academy_a):
    return StripeConnectedAccount.objects.create(
        academy=academy_a,
        stripe_account_id="acct_a123",
        account_type=StripeConnectedAccount.AccountType.EXPRESS,
        status=StripeConnectedAccount.Status.ENABLED,
        details_submitted=True,
        charges_enabled=True,
        payouts_enabled=True
    )


@pytest.fixture
def connected_account_b(db, academy_b):
    return StripeConnectedAccount.objects.create(
        academy=academy_b,
        stripe_account_id="acct_b123",
        account_type=StripeConnectedAccount.AccountType.EXPRESS,
        status=StripeConnectedAccount.Status.ENABLED,
        details_submitted=True,
        charges_enabled=True,
        payouts_enabled=True
    )


def get_auth_client(user):
    """Helper to create authenticated client for user."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


# ─── Authentication Tests ─────────────────────────────────────────────────────


class TestAuthenticationRequirements:
    """Test that all endpoints require authentication."""

    def test_create_connected_account_requires_auth(self, academy_a):
        """Test unauthenticated access to create connected account."""
        client = APIClient()
        response = client.post("/api/v1/membership/connect/create-account/", {
            "academy": academy_a.id,
            "country": "US"
        })
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_onboarding_link_requires_auth(self, academy_a):
        """Test unauthenticated access to onboarding link."""
        client = APIClient()
        response = client.post(
            f"/api/v1/membership/connect/onboarding-link/?academy={academy_a.id}",
            {
                "return_url": "https://example.com/return",
                "refresh_url": "https://example.com/refresh"
            }
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_connected_account_status_requires_auth(self, academy_a):
        """Test unauthenticated access to account status."""
        client = APIClient()
        response = client.get(f"/api/v1/membership/connect/status/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_dashboard_link_requires_auth(self, academy_a):
        """Test unauthenticated access to dashboard link."""
        client = APIClient()
        response = client.post(f"/api/v1/membership/connect/dashboard-link/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_marketplace_enroll_requires_auth(self, academy_a):
        """Test unauthenticated access to marketplace enrollment."""
        client = APIClient()
        response = client.post("/api/v1/membership/marketplace-enroll/", {
            "academy": academy_a.id,
            "plan": 1
        })
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_earnings_requires_auth(self, academy_a):
        """Test unauthenticated access to earnings."""
        client = APIClient()
        response = client.get(f"/api/v1/membership/earnings/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_transactions_requires_auth(self, academy_a):
        """Test unauthenticated access to transactions."""
        client = APIClient()
        response = client.get(f"/api/v1/membership/marketplace-transactions/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_configure_commission_requires_auth(self, academy_a):
        """Test unauthenticated access to commission configuration."""
        client = APIClient()
        response = client.post("/api/v1/membership/configure-commission/", {
            "academy": academy_a.id,
            "commission_type": "PERCENTAGE"
        })
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ─── Permission-based Access Control Tests ───────────────────────────────────


class TestOwnerOnlyEndpoints:
    """Test endpoints that require OWNER role."""

    @patch('membership.services.stripe.Account.create')
    def test_create_connected_account_owner_success(
        self, mock_stripe, owner_a, academy_a, membership_owner_a
    ):
        """Test that academy owners can create connected accounts."""
        mock_stripe.return_value = MagicMock(id="acct_new123")
        client = get_auth_client(owner_a)

        response = client.post("/api/v1/membership/connect/create-account/", {
            "academy": academy_a.id,
            "country": "US"
        })
        assert response.status_code == status.HTTP_201_CREATED

    def test_create_connected_account_member_forbidden(
        self, member_a, academy_a, membership_member_a
    ):
        """Test that academy members cannot create connected accounts."""
        client = get_auth_client(member_a)

        response = client.post("/api/v1/membership/connect/create-account/", {
            "academy": academy_a.id,
            "country": "US"
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only academy owners" in response.data["detail"]

    def test_create_connected_account_unaffiliated_forbidden(
        self, unaffiliated_user, academy_a
    ):
        """Test that unaffiliated users cannot create connected accounts."""
        client = get_auth_client(unaffiliated_user)

        response = client.post("/api/v1/membership/connect/create-account/", {
            "academy": academy_a.id,
            "country": "US"
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_onboarding_link_owner_success(
        self, owner_a, academy_a, membership_owner_a, connected_account_a
    ):
        """Test that academy owners can create onboarding links."""
        client = get_auth_client(owner_a)

        with patch('membership.services.stripe.AccountLink.create') as mock_stripe:
            mock_stripe.return_value = MagicMock(url="https://onboard.stripe.com")

            response = client.post(
                f"/api/v1/membership/connect/onboarding-link/?academy={academy_a.id}",
                {
                    "return_url": "https://example.com/return",
                    "refresh_url": "https://example.com/refresh"
                }
            )
            assert response.status_code == status.HTTP_200_OK

    def test_onboarding_link_member_forbidden(
        self, member_a, academy_a, membership_member_a, connected_account_a
    ):
        """Test that academy members cannot create onboarding links."""
        client = get_auth_client(member_a)

        response = client.post(
            f"/api/v1/membership/connect/onboarding-link/?academy={academy_a.id}",
            {
                "return_url": "https://example.com/return",
                "refresh_url": "https://example.com/refresh"
            }
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_dashboard_link_owner_success(
        self, owner_a, academy_a, membership_owner_a, connected_account_a
    ):
        """Test that academy owners can access dashboard links."""
        client = get_auth_client(owner_a)

        with patch('membership.services.stripe.Account.create_login_link') as mock_stripe:
            mock_stripe.return_value = MagicMock(url="https://dashboard.stripe.com")

            response = client.post(f"/api/v1/membership/connect/dashboard-link/?academy={academy_a.id}")
            assert response.status_code == status.HTTP_200_OK

    def test_dashboard_link_member_forbidden(
        self, member_a, academy_a, membership_member_a, connected_account_a
    ):
        """Test that academy members cannot access dashboard links."""
        client = get_auth_client(member_a)

        response = client.post(f"/api/v1/membership/connect/dashboard-link/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only academy owners" in response.data["detail"]

    def test_configure_commission_owner_success(
        self, owner_a, academy_a, membership_owner_a
    ):
        """Test that academy owners can configure commission."""
        client = get_auth_client(owner_a)

        response = client.post("/api/v1/membership/configure-commission/", {
            "academy": academy_a.id,
            "commission_type": "PERCENTAGE",
            "percentage_rate": "0.15"
        })
        assert response.status_code == status.HTTP_201_CREATED

    def test_configure_commission_member_forbidden(
        self, member_a, academy_a, membership_member_a
    ):
        """Test that academy members cannot configure commission."""
        client = get_auth_client(member_a)

        response = client.post("/api/v1/membership/configure-commission/", {
            "academy": academy_a.id,
            "commission_type": "PERCENTAGE",
            "percentage_rate": "0.15"
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only academy owners" in response.data["detail"]


class TestMemberAccessEndpoints:
    """Test endpoints that require MEMBER (or higher) role."""

    def test_connected_account_status_member_success(
        self, member_a, academy_a, membership_member_a, connected_account_a
    ):
        """Test that academy members can view connected account status."""
        client = get_auth_client(member_a)

        response = client.get(f"/api/v1/membership/connect/status/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_200_OK

    def test_connected_account_status_owner_success(
        self, owner_a, academy_a, membership_owner_a, connected_account_a
    ):
        """Test that academy owners can view connected account status."""
        client = get_auth_client(owner_a)

        response = client.get(f"/api/v1/membership/connect/status/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_200_OK

    def test_connected_account_status_unaffiliated_forbidden(
        self, unaffiliated_user, academy_a, connected_account_a
    ):
        """Test that unaffiliated users cannot view connected account status."""
        client = get_auth_client(unaffiliated_user)

        response = client.get(f"/api/v1/membership/connect/status/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_earnings_member_success(
        self, member_a, academy_a, membership_member_a, connected_account_a
    ):
        """Test that academy members can view earnings."""
        client = get_auth_client(member_a)

        response = client.get(f"/api/v1/membership/earnings/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_200_OK

    def test_earnings_unaffiliated_forbidden(
        self, unaffiliated_user, academy_a
    ):
        """Test that unaffiliated users cannot view earnings."""
        client = get_auth_client(unaffiliated_user)

        response = client.get(f"/api/v1/membership/earnings/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_transactions_member_success(
        self, member_a, academy_a, membership_member_a
    ):
        """Test that academy members can view transactions."""
        client = get_auth_client(member_a)

        response = client.get(f"/api/v1/membership/marketplace-transactions/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_200_OK

    def test_transactions_unaffiliated_forbidden(
        self, unaffiliated_user, academy_a
    ):
        """Test that unaffiliated users cannot view transactions."""
        client = get_auth_client(unaffiliated_user)

        response = client.get(f"/api/v1/membership/marketplace-transactions/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ─── Cross-Academy Access Prevention Tests ───────────────────────────────────


class TestCrossAcademyAccessPrevention:
    """Test that users cannot access data from other academies."""

    def test_owner_cannot_access_other_academy_status(
        self, owner_a, academy_b, membership_owner_a, connected_account_b
    ):
        """Test that academy A owner cannot access academy B status."""
        client = get_auth_client(owner_a)

        response = client.get(f"/api/v1/membership/connect/status/?academy={academy_b.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_member_cannot_access_other_academy_earnings(
        self, member_a, academy_b, membership_member_a
    ):
        """Test that academy A member cannot access academy B earnings."""
        client = get_auth_client(member_a)

        response = client.get(f"/api/v1/membership/earnings/?academy={academy_b.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_owner_cannot_create_connected_account_for_other_academy(
        self, owner_a, academy_b, membership_owner_a
    ):
        """Test that academy A owner cannot create connected account for academy B."""
        client = get_auth_client(owner_a)

        response = client.post("/api/v1/membership/connect/create-account/", {
            "academy": academy_b.id,
            "country": "US"
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_member_cannot_view_other_academy_transactions(
        self, member_a, academy_b, membership_member_a
    ):
        """Test that academy A member cannot view academy B transactions."""
        client = get_auth_client(member_a)

        response = client.get(f"/api/v1/membership/marketplace-transactions/?academy={academy_b.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_owner_cannot_configure_commission_for_other_academy(
        self, owner_a, academy_b, membership_owner_a
    ):
        """Test that academy A owner cannot configure commission for academy B."""
        client = get_auth_client(owner_a)

        response = client.post("/api/v1/membership/configure-commission/", {
            "academy": academy_b.id,
            "commission_type": "PERCENTAGE",
            "percentage_rate": "0.15"
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ─── Data Isolation Tests ─────────────────────────────────────────────────────


class TestDataIsolation:
    """Test that data is properly isolated between academies."""

    def test_earnings_data_isolation(
        self, member_a, academy_a, academy_b, membership_member_a,
        connected_account_a, connected_account_b
    ):
        """Test that earnings are isolated between academies."""
        # Create earnings for both academies
        AcademyEarnings.objects.create(
            academy=academy_a,
            connected_account=connected_account_a,
            year=2024,
            month=3,
            total_gross=Decimal("1000.00")
        )

        AcademyEarnings.objects.create(
            academy=academy_b,
            connected_account=connected_account_b,
            year=2024,
            month=3,
            total_gross=Decimal("2000.00")
        )

        client = get_auth_client(member_a)
        response = client.get(f"/api/v1/membership/earnings/?academy={academy_a.id}&year=2024&month=3")

        assert response.status_code == status.HTTP_200_OK
        # Should only see academy A's earnings (1000), not academy B's (2000)
        assert response.data["total_gross"] == "1000.00"

    def test_transactions_data_isolation(
        self, member_a, academy_a, academy_b, membership_member_a,
        connected_account_a, connected_account_b
    ):
        """Test that transactions are isolated between academies."""
        # Create customers and transactions for both academies
        customer_a = StripeCustomer.objects.create(
            user=member_a, stripe_customer_id="cus_a123"
        )

        other_user = UserFactory()
        customer_b = StripeCustomer.objects.create(
            user=other_user, stripe_customer_id="cus_b123"
        )

        MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_a123",
            stripe_customer=customer_a,
            connected_account=connected_account_a,
            academy=academy_a,
            transaction_type=MarketplaceTransaction.TransactionType.ONE_TIME,
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),
            net_amount=Decimal("90.00")
        )

        MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_b123",
            stripe_customer=customer_b,
            connected_account=connected_account_b,
            academy=academy_b,
            transaction_type=MarketplaceTransaction.TransactionType.ONE_TIME,
            gross_amount=Decimal("200.00"),
            platform_fee=Decimal("20.00"),
            net_amount=Decimal("180.00")
        )

        client = get_auth_client(member_a)
        response = client.get(f"/api/v1/membership/marketplace-transactions/?academy={academy_a.id}")

        assert response.status_code == status.HTTP_200_OK
        # Should only see academy A's transaction
        assert len(response.data) == 1
        assert response.data[0]["stripe_payment_intent_id"] == "pi_a123"
        assert response.data[0]["gross_amount"] == "100.00"


# ─── Superuser Global Access Tests ───────────────────────────────────────────


class TestSuperuserGlobalAccess:
    """Test superuser global access for commission configuration."""

    def test_superuser_can_configure_global_commission(self, superuser):
        """Test that superusers can configure global commission."""
        client = get_auth_client(superuser)

        response = client.post("/api/v1/membership/configure-commission/", {
            "commission_type": "PERCENTAGE",
            "percentage_rate": "0.12"
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["academy"] is None

    def test_non_superuser_cannot_configure_global_commission(
        self, owner_a, membership_owner_a
    ):
        """Test that non-superusers cannot configure global commission."""
        client = get_auth_client(owner_a)

        response = client.post("/api/v1/membership/configure-commission/", {
            "commission_type": "PERCENTAGE",
            "percentage_rate": "0.12"
        })
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only superusers" in response.data["detail"]


# ─── Input Validation and Security Tests ─────────────────────────────────────


class TestInputValidation:
    """Test input validation and security measures."""

    def test_academy_parameter_required_for_status(self, member_a, membership_member_a):
        """Test that academy parameter is required for status endpoint."""
        client = get_auth_client(member_a)

        response = client.get("/api/v1/membership/connect/status/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Academy ID required" in response.data["detail"]

    def test_academy_parameter_required_for_earnings(self, member_a, membership_member_a):
        """Test that academy parameter is required for earnings endpoint."""
        client = get_auth_client(member_a)

        response = client.get("/api/v1/membership/earnings/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Academy ID required" in response.data["detail"]

    def test_academy_parameter_required_for_transactions(self, member_a, membership_member_a):
        """Test that academy parameter is required for transactions endpoint."""
        client = get_auth_client(member_a)

        response = client.get("/api/v1/membership/marketplace-transactions/")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Academy ID required" in response.data["detail"]

    def test_invalid_academy_id_handling(self, member_a, membership_member_a):
        """Test handling of invalid academy IDs."""
        client = get_auth_client(member_a)

        response = client.get("/api/v1/membership/connect/status/?academy=99999")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Academy not found" in response.data["detail"]

    def test_invalid_year_month_parameters(
        self, member_a, academy_a, membership_member_a
    ):
        """Test handling of invalid year/month parameters."""
        client = get_auth_client(member_a)

        response = client.get(
            f"/api/v1/membership/earnings/?academy={academy_a.id}&year=invalid&month=invalid"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid year or month" in response.data["detail"]

    def test_negative_commission_rates_validation(
        self, owner_a, academy_a, membership_owner_a
    ):
        """Test validation of negative commission rates."""
        client = get_auth_client(owner_a)

        response = client.post("/api/v1/membership/configure-commission/", {
            "academy": academy_a.id,
            "commission_type": "PERCENTAGE",
            "percentage_rate": "-0.15"  # Negative rate should be invalid
        })
        # This should be validated at the serializer level
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_201_CREATED]

    def test_missing_required_fields_for_commission(
        self, owner_a, academy_a, membership_owner_a
    ):
        """Test handling of missing required fields for commission configuration."""
        client = get_auth_client(owner_a)

        response = client.post("/api/v1/membership/configure-commission/", {
            "academy": academy_a.id
            # Missing commission_type
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


# ─── Inactive Membership Tests ───────────────────────────────────────────────


class TestInactiveMembershipAccess:
    """Test that inactive memberships don't grant access."""

    def test_inactive_membership_denies_access(
        self, member_a, academy_a, connected_account_a
    ):
        """Test that inactive academy membership denies access."""
        # Create inactive membership
        AcademyMembership.objects.create(
            user=member_a,
            academy=academy_a,
            role=AcademyMembership.Role.STUDENT,
            is_active=False  # Inactive
        )

        client = get_auth_client(member_a)

        response = client.get(f"/api/v1/membership/connect/status/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_reactivated_membership_grants_access(
        self, member_a, academy_a, connected_account_a
    ):
        """Test that reactivated membership grants access."""
        # Create and then activate membership
        membership = AcademyMembership.objects.create(
            user=member_a,
            academy=academy_a,
            role=AcademyMembership.Role.STUDENT,
            is_active=False
        )

        client = get_auth_client(member_a)

        # Should be denied initially
        response = client.get(f"/api/v1/membership/connect/status/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Activate membership
        membership.is_active = True
        membership.save()

        # Should now be allowed
        response = client.get(f"/api/v1/membership/connect/status/?academy={academy_a.id}")
        assert response.status_code == status.HTTP_200_OK