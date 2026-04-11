"""
Tests for Stripe Connect Service Layer - comprehensive test suite for marketplace services.

Tests all Stripe Connect services:
- StripeConnectService
- PlatformCommissionService
- MarketplacePaymentService
- MarketplaceAnalyticsService
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock
import pytest
from datetime import date
from django.utils import timezone
from django.contrib.auth.models import User

from membership.models import (
    StripeConnectedAccount, PlatformCommission, MarketplaceTransaction,
    AcademyEarnings, StripeCustomer, SeminarRegistration, Subscription
)
from membership.services import (
    StripeConnectService, PlatformCommissionService,
    MarketplacePaymentService, MarketplaceAnalyticsService
)
from factories import AcademyFactory, UserFactory, SeminarFactory


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def academy(db):
    return AcademyFactory(name="Test Academy", email="test@academy.com")


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def stripe_customer(db, user):
    return StripeCustomer.objects.create(
        user=user,
        stripe_customer_id="cus_test123"
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
        business_name=academy.name
    )


@pytest.fixture
def platform_commission(db):
    return PlatformCommission.objects.create(
        academy=None,  # Global default
        commission_type=PlatformCommission.CommissionType.PERCENTAGE,
        percentage_rate=Decimal("0.10"),  # 10%
        min_commission=Decimal("0.50")
    )


# ─── StripeConnectService Tests ───────────────────────────────────────────────


class TestStripeConnectService:

    @patch('membership.services.stripe.Account.create')
    def test_create_connected_account_success(self, mock_stripe_create, academy):
        """Test successful creation of connected account."""
        mock_stripe_create.return_value = MagicMock(id="acct_new123")

        result = StripeConnectService.create_connected_account(
            academy=academy,
            country="US"
        )

        assert result.stripe_account_id == "acct_new123"
        assert result.academy == academy
        assert result.account_type == StripeConnectedAccount.AccountType.EXPRESS
        assert result.status == StripeConnectedAccount.Status.PENDING
        assert result.business_name == academy.name
        assert result.support_email == academy.email

        # Verify Stripe API call
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

    def test_create_connected_account_already_exists(self, academy, connected_account):
        """Test that existing account is returned without creating new one."""
        with patch('membership.services.stripe.Account.create') as mock_create:
            result = StripeConnectService.create_connected_account(academy=academy)

            assert result == connected_account
            mock_create.assert_not_called()

    @patch('membership.services.stripe.AccountLink.create')
    def test_create_onboarding_link_success(self, mock_stripe_create, connected_account):
        """Test successful onboarding link creation."""
        mock_stripe_create.return_value = MagicMock(
            url="https://connect.stripe.com/onboard/123"
        )

        result = StripeConnectService.create_onboarding_link(
            connected_account=connected_account,
            return_url="https://example.com/return",
            refresh_url="https://example.com/refresh"
        )

        assert result == "https://connect.stripe.com/onboard/123"

        # Verify URL was saved to account
        connected_account.refresh_from_db()
        assert connected_account.onboarding_url == "https://connect.stripe.com/onboard/123"

        mock_stripe_create.assert_called_once_with(
            account="acct_test123",
            refresh_url="https://example.com/refresh",
            return_url="https://example.com/return",
            type="account_onboarding"
        )

    @patch('membership.services.stripe.Account.create_login_link')
    def test_create_dashboard_link_success(self, mock_stripe_create, connected_account):
        """Test successful dashboard link creation."""
        mock_stripe_create.return_value = MagicMock(
            url="https://connect.stripe.com/dashboard/123"
        )

        result = StripeConnectService.create_dashboard_link(connected_account)

        assert result == "https://connect.stripe.com/dashboard/123"

        # Verify URL was saved to account
        connected_account.refresh_from_db()
        assert connected_account.dashboard_url == "https://connect.stripe.com/dashboard/123"

        mock_stripe_create.assert_called_once_with("acct_test123")

    def test_create_dashboard_link_not_onboarded(self, academy):
        """Test dashboard link creation fails for non-onboarded account."""
        account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_pending123",
            status=StripeConnectedAccount.Status.PENDING,
            details_submitted=False,
            charges_enabled=False,
            payouts_enabled=False
        )

        with pytest.raises(ValueError, match="complete onboarding"):
            StripeConnectService.create_dashboard_link(account)

    @patch('membership.services.stripe.Account.retrieve')
    def test_sync_account_status_success(self, mock_stripe_retrieve, connected_account):
        """Test successful account status sync."""
        mock_stripe_retrieve.return_value = MagicMock(
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True,
            business_profile={
                "name": "Updated Academy Name",
                "url": "https://updated.com",
                "support_email": "support@updated.com"
            },
            requirements={}
        )

        result = StripeConnectService.sync_account_status(connected_account)

        assert result.details_submitted is True
        assert result.charges_enabled is True
        assert result.payouts_enabled is True
        assert result.business_name == "Updated Academy Name"
        assert result.business_url == "https://updated.com"
        assert result.support_email == "support@updated.com"
        assert result.status == StripeConnectedAccount.Status.ENABLED

    def test_get_connected_account_for_academy_exists(self, academy, connected_account):
        """Test getting existing connected account."""
        result = StripeConnectService.get_connected_account_for_academy(academy)
        assert result == connected_account

    def test_get_connected_account_for_academy_not_exists(self, academy):
        """Test getting connected account when none exists."""
        result = StripeConnectService.get_connected_account_for_academy(academy)
        assert result is None


# ─── PlatformCommissionService Tests ──────────────────────────────────────────


class TestPlatformCommissionService:

    def test_get_commission_config_academy_specific(self, academy):
        """Test getting academy-specific commission config."""
        academy_config = PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.PERCENTAGE,
            percentage_rate=Decimal("0.15"),  # 15%
            is_active=True
        )

        result = PlatformCommissionService.get_commission_config(academy)
        assert result == academy_config
        assert result.percentage_rate == Decimal("0.15")

    def test_get_commission_config_default_fallback(self, academy, platform_commission):
        """Test falling back to default commission config."""
        result = PlatformCommissionService.get_commission_config(academy)
        assert result == platform_commission
        assert result.percentage_rate == Decimal("0.10")

    def test_get_commission_config_creates_default(self, academy):
        """Test creating default commission when none exists."""
        result = PlatformCommissionService.get_commission_config(academy)

        assert result.academy is None
        assert result.commission_type == PlatformCommission.CommissionType.PERCENTAGE
        assert result.percentage_rate == Decimal("0.10")
        assert result.min_commission == Decimal("0.50")
        assert result.is_active is True

    def test_calculate_commission_percentage(self, academy, platform_commission):
        """Test percentage-based commission calculation."""
        result = PlatformCommissionService.calculate_commission(
            academy=academy,
            amount=Decimal("100.00")
        )

        assert result == Decimal("10.00")  # 10% of 100

    def test_calculate_commission_min_threshold(self, academy):
        """Test commission with minimum threshold."""
        PlatformCommission.objects.create(
            academy=None,
            commission_type=PlatformCommission.CommissionType.PERCENTAGE,
            percentage_rate=Decimal("0.10"),
            min_commission=Decimal("2.00"),
            is_active=True
        )

        result = PlatformCommissionService.calculate_commission(
            academy=academy,
            amount=Decimal("5.00")  # Would be 0.50, but min is 2.00
        )

        assert result == Decimal("2.00")

    def test_calculate_commission_fixed_amount(self, academy):
        """Test fixed amount commission calculation."""
        PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.FIXED_AMOUNT,
            fixed_amount=Decimal("3.00"),
            is_active=True
        )

        result = PlatformCommissionService.calculate_commission(
            academy=academy,
            amount=Decimal("100.00")
        )

        assert result == Decimal("3.00")

    def test_calculate_commission_hybrid(self, academy):
        """Test hybrid commission calculation."""
        PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.HYBRID,
            percentage_rate=Decimal("0.05"),  # 5%
            fixed_amount=Decimal("2.00"),
            is_active=True
        )

        result = PlatformCommissionService.calculate_commission(
            academy=academy,
            amount=Decimal("100.00")
        )

        assert result == Decimal("7.00")  # 5.00 + 2.00

    def test_create_academy_commission(self, academy):
        """Test creating academy-specific commission."""
        result = PlatformCommissionService.create_academy_commission(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.PERCENTAGE,
            percentage_rate=Decimal("0.15"),
            effective_from=date(2024, 1, 1)
        )

        assert result.academy == academy
        assert result.commission_type == PlatformCommission.CommissionType.PERCENTAGE
        assert result.percentage_rate == Decimal("0.15")
        assert result.effective_from == date(2024, 1, 1)
        assert result.is_active is True

    def test_create_default_commission(self):
        """Test creating default commission configuration."""
        result = PlatformCommissionService.create_default_commission()

        assert result.academy is None
        assert result.commission_type == PlatformCommission.CommissionType.PERCENTAGE
        assert result.percentage_rate == Decimal("0.10")
        assert result.min_commission == Decimal("0.50")


# ─── MarketplacePaymentService Tests ──────────────────────────────────────────


class TestMarketplacePaymentService:

    @patch('membership.services.StripeCustomerService.get_or_create_customer')
    @patch('membership.services.stripe.PaymentIntent.create')
    def test_create_marketplace_payment_intent_success(
        self, mock_payment_intent, mock_customer, user, academy,
        connected_account, platform_commission, stripe_customer
    ):
        """Test successful marketplace payment intent creation."""
        mock_customer.return_value = stripe_customer
        mock_payment_intent.return_value = MagicMock(
            id="pi_test123",
            client_secret="pi_test123_secret_123"
        )

        result = MarketplacePaymentService.create_marketplace_payment_intent(
            user=user,
            academy=academy,
            amount=Decimal("100.00"),
            transaction_type=MarketplaceTransaction.TransactionType.ONE_TIME,
            description="Test payment",
            metadata={"test_key": "test_value"}
        )

        # Verify payment intent was created correctly
        mock_payment_intent.assert_called_once()
        call_kwargs = mock_payment_intent.call_args[1]
        assert call_kwargs["amount"] == 10000  # $100 in cents
        assert call_kwargs["currency"] == "usd"
        assert call_kwargs["customer"] == "cus_test123"
        assert call_kwargs["description"] == "Test payment"
        assert call_kwargs["transfer_data"]["destination"] == "acct_test123"
        assert call_kwargs["application_fee_amount"] == 1000  # $10 in cents (10% of $100)

        # Verify marketplace transaction was created
        assert "marketplace_transaction" in result
        transaction = result["marketplace_transaction"]
        assert transaction.stripe_payment_intent_id == "pi_test123"
        assert transaction.academy == academy
        assert transaction.gross_amount == Decimal("100.00")
        assert transaction.platform_fee == Decimal("10.00")
        assert transaction.net_amount == Decimal("90.00")
        assert transaction.status == MarketplaceTransaction.Status.PENDING

        # Verify response structure
        assert result["client_secret"] == "pi_test123_secret_123"
        assert result["platform_fee"] == Decimal("10.00")
        assert result["academy_receives"] == Decimal("90.00")

    def test_create_marketplace_payment_intent_no_connected_account(
        self, user, academy, platform_commission
    ):
        """Test payment intent creation when no connected account exists."""
        with pytest.raises(ValueError, match="complete Stripe setup"):
            MarketplacePaymentService.create_marketplace_payment_intent(
                user=user,
                academy=academy,
                amount=Decimal("100.00"),
                transaction_type=MarketplaceTransaction.TransactionType.ONE_TIME,
                description="Test payment"
            )

    def test_create_marketplace_payment_intent_not_onboarded(
        self, user, academy, platform_commission
    ):
        """Test payment intent creation with non-onboarded account."""
        StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_pending123",
            status=StripeConnectedAccount.Status.PENDING,
            details_submitted=False,
            charges_enabled=False,
            payouts_enabled=False
        )

        with pytest.raises(ValueError, match="complete Stripe setup"):
            MarketplacePaymentService.create_marketplace_payment_intent(
                user=user,
                academy=academy,
                amount=Decimal("100.00"),
                transaction_type=MarketplaceTransaction.TransactionType.ONE_TIME,
                description="Test payment"
            )

    @patch('membership.services.stripe.PaymentIntent.retrieve')
    @patch('membership.services.stripe.Charge.retrieve')
    def test_process_successful_marketplace_payment(
        self, mock_charge_retrieve, mock_payment_intent_retrieve,
        academy, connected_account, stripe_customer
    ):
        """Test processing successful marketplace payment."""
        # Create marketplace transaction
        transaction = MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_test123",
            stripe_customer=stripe_customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=MarketplaceTransaction.TransactionType.ONE_TIME,
            status=MarketplaceTransaction.Status.PENDING,
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),
            net_amount=Decimal("90.00")
        )

        # Mock Stripe responses
        mock_payment_intent_retrieve.return_value = MagicMock(
            latest_charge="ch_test123",
            invoice=None
        )

        mock_charge_retrieve.return_value = MagicMock(
            balance_transaction="txn_test123",
            transfer="tr_test123",
            application_fee="fee_test123"
        )

        with patch('membership.services.stripe.BalanceTransaction.retrieve') as mock_balance:
            mock_balance.return_value = MagicMock(fee=290)  # $2.90 in cents

            result = MarketplacePaymentService.process_successful_marketplace_payment("pi_test123")

        assert result is not None
        assert result.status == MarketplaceTransaction.Status.COMPLETED
        assert result.stripe_fee == Decimal("2.90")
        assert result.stripe_transfer_id == "tr_test123"
        assert result.stripe_application_fee_id == "fee_test123"

    def test_process_successful_marketplace_payment_not_found(self):
        """Test processing payment when transaction doesn't exist."""
        result = MarketplacePaymentService.process_successful_marketplace_payment("pi_nonexistent")
        assert result is None

    def test_process_seminar_marketplace_payment(self, academy, connected_account, stripe_customer):
        """Test processing successful seminar marketplace payment."""
        # Create seminar and registration
        seminar = SeminarFactory(academy=academy)
        registration = SeminarRegistration.objects.create(
            seminar=seminar,
            athlete_id=1,  # Mock athlete ID
            status=SeminarRegistration.RegistrationStatus.CONFIRMED,
            payment_status=SeminarRegistration.PaymentStatus.PENDING
        )

        # Create marketplace transaction
        transaction = MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_seminar123",
            stripe_customer=stripe_customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=MarketplaceTransaction.TransactionType.SEMINAR,
            status=MarketplaceTransaction.Status.COMPLETED,
            seminar_registration=registration,
            gross_amount=Decimal("50.00"),
            platform_fee=Decimal("5.00"),
            net_amount=Decimal("45.00")
        )

        MarketplacePaymentService._process_seminar_marketplace_payment(transaction)

        # Verify registration payment status was updated
        registration.refresh_from_db()
        assert registration.payment_status == SeminarRegistration.PaymentStatus.PAID


# ─── MarketplaceAnalyticsService Tests ────────────────────────────────────────


class TestMarketplaceAnalyticsService:

    def test_update_earnings_for_transaction_new_record(
        self, academy, connected_account, stripe_customer
    ):
        """Test updating earnings for new monthly record."""
        transaction = MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_test123",
            stripe_customer=stripe_customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=MarketplaceTransaction.TransactionType.ONE_TIME,
            status=MarketplaceTransaction.Status.COMPLETED,
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),
            stripe_fee=Decimal("3.20"),
            net_amount=Decimal("86.80")
        )

        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = timezone.datetime(2024, 3, 15)
            MarketplaceAnalyticsService.update_earnings_for_transaction(transaction)

        # Verify earnings record was created
        earnings = AcademyEarnings.objects.get(
            academy=academy,
            connected_account=connected_account,
            year=2024,
            month=3
        )

        assert earnings.total_gross == Decimal("100.00")
        assert earnings.total_platform_fees == Decimal("10.00")
        assert earnings.total_stripe_fees == Decimal("3.20")
        assert earnings.total_net == Decimal("86.80")
        assert earnings.one_time_count == 1
        assert earnings.subscription_count == 0
        assert earnings.seminar_count == 0

    def test_update_earnings_for_transaction_existing_record(
        self, academy, connected_account, stripe_customer
    ):
        """Test updating earnings for existing monthly record."""
        # Create existing earnings record
        earnings = AcademyEarnings.objects.create(
            academy=academy,
            connected_account=connected_account,
            year=2024,
            month=3,
            total_gross=Decimal("50.00"),
            total_platform_fees=Decimal("5.00"),
            total_stripe_fees=Decimal("1.50"),
            total_net=Decimal("43.50"),
            one_time_count=1
        )

        transaction = MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_test456",
            stripe_customer=stripe_customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=MarketplaceTransaction.TransactionType.SUBSCRIPTION,
            status=MarketplaceTransaction.Status.COMPLETED,
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),
            stripe_fee=Decimal("3.20"),
            net_amount=Decimal("86.80")
        )

        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = timezone.datetime(2024, 3, 20)
            MarketplaceAnalyticsService.update_earnings_for_transaction(transaction)

        # Verify earnings were updated
        earnings.refresh_from_db()
        assert earnings.total_gross == Decimal("150.00")  # 50 + 100
        assert earnings.total_platform_fees == Decimal("15.00")  # 5 + 10
        assert earnings.total_stripe_fees == Decimal("4.70")  # 1.50 + 3.20
        assert earnings.total_net == Decimal("130.30")  # 43.50 + 86.80
        assert earnings.one_time_count == 1  # Unchanged
        assert earnings.subscription_count == 1  # New

    def test_update_earnings_for_transaction_seminar(
        self, academy, connected_account, stripe_customer
    ):
        """Test updating earnings for seminar transaction."""
        transaction = MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_seminar123",
            stripe_customer=stripe_customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=MarketplaceTransaction.TransactionType.SEMINAR,
            status=MarketplaceTransaction.Status.COMPLETED,
            gross_amount=Decimal("50.00"),
            platform_fee=Decimal("5.00"),
            stripe_fee=Decimal("1.75"),
            net_amount=Decimal("43.25")
        )

        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = timezone.datetime(2024, 3, 15)
            MarketplaceAnalyticsService.update_earnings_for_transaction(transaction)

        earnings = AcademyEarnings.objects.get(
            academy=academy,
            year=2024,
            month=3
        )

        assert earnings.seminar_count == 1
        assert earnings.one_time_count == 0
        assert earnings.subscription_count == 0

    def test_update_earnings_for_transaction_not_completed(
        self, academy, connected_account, stripe_customer
    ):
        """Test that non-completed transactions don't update earnings."""
        transaction = MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_pending123",
            stripe_customer=stripe_customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=MarketplaceTransaction.TransactionType.ONE_TIME,
            status=MarketplaceTransaction.Status.PENDING,
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),
            net_amount=Decimal("90.00")
        )

        MarketplaceAnalyticsService.update_earnings_for_transaction(transaction)

        # Verify no earnings record was created
        assert not AcademyEarnings.objects.filter(academy=academy).exists()

    def test_get_academy_earnings_summary_exists(self, academy, connected_account):
        """Test getting earnings summary when data exists."""
        earnings = AcademyEarnings.objects.create(
            academy=academy,
            connected_account=connected_account,
            year=2024,
            month=3,
            total_gross=Decimal("1000.00"),
            total_platform_fees=Decimal("100.00"),
            total_stripe_fees=Decimal("30.00"),
            total_net=Decimal("870.00"),
            subscription_count=5,
            seminar_count=2,
            one_time_count=3
        )

        result = MarketplaceAnalyticsService.get_academy_earnings_summary(
            academy=academy,
            year=2024,
            month=3
        )

        assert result["total_gross"] == Decimal("1000.00")
        assert result["total_platform_fees"] == Decimal("100.00")
        assert result["total_stripe_fees"] == Decimal("30.00")
        assert result["total_net"] == Decimal("870.00")
        assert result["total_transactions"] == 10  # 5 + 2 + 3
        assert result["platform_fee_rate"] == Decimal("0.10")  # 100/1000
        assert result["subscription_count"] == 5
        assert result["year"] == 2024
        assert result["month"] == 3

    def test_get_academy_earnings_summary_not_exists(self, academy):
        """Test getting earnings summary when no data exists."""
        result = MarketplaceAnalyticsService.get_academy_earnings_summary(
            academy=academy,
            year=2024,
            month=3
        )

        assert result["total_gross"] == Decimal("0.00")
        assert result["total_platform_fees"] == Decimal("0.00")
        assert result["total_net"] == Decimal("0.00")
        assert result["total_transactions"] == 0
        assert result["platform_fee_rate"] == Decimal("0.00")

    def test_get_academy_yearly_summary(self, academy, connected_account):
        """Test getting yearly earnings summary."""
        # Create multiple monthly records
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

        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = timezone.datetime(2024, 6, 15)
            result = MarketplaceAnalyticsService.get_academy_yearly_summary(
                academy=academy,
                year=2024
            )

        # The method should aggregate multiple months
        # (Implementation details would depend on the actual service method)
        assert "total_gross" in result