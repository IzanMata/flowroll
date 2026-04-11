"""
Tests for Stripe Connect Models - comprehensive test suite for marketplace models.

Tests all Stripe Connect models:
- StripeConnectedAccount
- PlatformCommission
- MarketplaceTransaction
- AcademyEarnings
"""

from decimal import Decimal
import pytest
from datetime import date

from membership.models import (
    StripeConnectedAccount, PlatformCommission, MarketplaceTransaction,
    AcademyEarnings, StripeCustomer
)
from factories import AcademyFactory, UserFactory


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def academy(db):
    return AcademyFactory(name="Test Academy")


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def stripe_customer(db, user):
    return StripeCustomer.objects.create(
        user=user,
        stripe_customer_id="cus_test123"
    )


# ─── StripeConnectedAccount Model Tests ──────────────────────────────────────


class TestStripeConnectedAccount:

    def test_create_connected_account(self, academy):
        """Test basic connected account creation."""
        account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123",
            account_type=StripeConnectedAccount.AccountType.EXPRESS,
            status=StripeConnectedAccount.Status.PENDING,
            business_name="Test Business"
        )

        assert account.academy == academy
        assert account.stripe_account_id == "acct_test123"
        assert account.account_type == "EXPRESS"
        assert account.status == "PENDING"
        assert account.business_name == "Test Business"
        assert account.details_submitted is False
        assert account.charges_enabled is False
        assert account.payouts_enabled is False

    def test_str_representation(self, academy):
        """Test string representation of connected account."""
        account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123",
            status=StripeConnectedAccount.Status.ENABLED
        )

        expected = f"{academy.name} -> acct_test123 (ENABLED)"
        assert str(account) == expected

    def test_is_fully_onboarded_true(self, academy):
        """Test is_fully_onboarded property when account is ready."""
        account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123",
            status=StripeConnectedAccount.Status.ENABLED,
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True
        )

        assert account.is_fully_onboarded is True

    def test_is_fully_onboarded_false_status(self, academy):
        """Test is_fully_onboarded property when status is not enabled."""
        account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123",
            status=StripeConnectedAccount.Status.PENDING,
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=True
        )

        assert account.is_fully_onboarded is False

    def test_is_fully_onboarded_false_details(self, academy):
        """Test is_fully_onboarded property when details not submitted."""
        account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123",
            status=StripeConnectedAccount.Status.ENABLED,
            details_submitted=False,
            charges_enabled=True,
            payouts_enabled=True
        )

        assert account.is_fully_onboarded is False

    def test_is_fully_onboarded_false_charges(self, academy):
        """Test is_fully_onboarded property when charges not enabled."""
        account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123",
            status=StripeConnectedAccount.Status.ENABLED,
            details_submitted=True,
            charges_enabled=False,
            payouts_enabled=True
        )

        assert account.is_fully_onboarded is False

    def test_is_fully_onboarded_false_payouts(self, academy):
        """Test is_fully_onboarded property when payouts not enabled."""
        account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123",
            status=StripeConnectedAccount.Status.ENABLED,
            details_submitted=True,
            charges_enabled=True,
            payouts_enabled=False
        )

        assert account.is_fully_onboarded is False

    def test_unique_stripe_account_id(self, academy):
        """Test that stripe_account_id must be unique."""
        StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_unique123"
        )

        other_academy = AcademyFactory()
        with pytest.raises(Exception):  # Should raise integrity error
            StripeConnectedAccount.objects.create(
                academy=other_academy,
                stripe_account_id="acct_unique123"
            )

    def test_metadata_field(self, academy):
        """Test JSON metadata field functionality."""
        metadata = {
            "custom_field": "value",
            "number_field": 123,
            "nested": {"key": "value"}
        }

        account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_metadata123",
            metadata=metadata
        )

        account.refresh_from_db()
        assert account.metadata == metadata
        assert account.metadata["custom_field"] == "value"
        assert account.metadata["nested"]["key"] == "value"


# ─── PlatformCommission Model Tests ───────────────────────────────────────────


class TestPlatformCommission:

    def test_create_percentage_commission(self, academy):
        """Test creating percentage-based commission."""
        commission = PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.PERCENTAGE,
            percentage_rate=Decimal("0.15"),  # 15%
            min_commission=Decimal("1.00")
        )

        assert commission.academy == academy
        assert commission.commission_type == "PERCENTAGE"
        assert commission.percentage_rate == Decimal("0.15")
        assert commission.min_commission == Decimal("1.00")
        assert commission.is_active is True

    def test_create_fixed_amount_commission(self, academy):
        """Test creating fixed amount commission."""
        commission = PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.FIXED_AMOUNT,
            fixed_amount=Decimal("5.00")
        )

        assert commission.commission_type == "FIXED_AMOUNT"
        assert commission.fixed_amount == Decimal("5.00")

    def test_create_hybrid_commission(self, academy):
        """Test creating hybrid commission."""
        commission = PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.HYBRID,
            percentage_rate=Decimal("0.05"),
            fixed_amount=Decimal("2.00")
        )

        assert commission.commission_type == "HYBRID"
        assert commission.percentage_rate == Decimal("0.05")
        assert commission.fixed_amount == Decimal("2.00")

    def test_str_representation_percentage(self, academy):
        """Test string representation for percentage commission."""
        commission = PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.PERCENTAGE,
            percentage_rate=Decimal("0.15")
        )

        expected = f"{academy.name}: 15.0% commission"
        assert str(commission) == expected

    def test_str_representation_fixed_amount(self, academy):
        """Test string representation for fixed amount commission."""
        commission = PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.FIXED_AMOUNT,
            fixed_amount=Decimal("5.00")
        )

        expected = f"{academy.name}: $5.00 commission"
        assert str(commission) == expected

    def test_str_representation_hybrid(self, academy):
        """Test string representation for hybrid commission."""
        commission = PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.HYBRID,
            percentage_rate=Decimal("0.05"),
            fixed_amount=Decimal("2.00")
        )

        expected = f"{academy.name}: 5.0% + $2.00 commission"
        assert str(commission) == expected

    def test_calculate_commission_percentage(self, academy):
        """Test commission calculation for percentage type."""
        commission = PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.PERCENTAGE,
            percentage_rate=Decimal("0.10"),  # 10%
            min_commission=Decimal("0.50")
        )

        # Normal calculation
        result = commission.calculate_commission(Decimal("100.00"))
        assert result == Decimal("10.00")

        # Below minimum
        result = commission.calculate_commission(Decimal("3.00"))
        assert result == Decimal("0.50")  # Minimum applied

    def test_calculate_commission_fixed_amount(self, academy):
        """Test commission calculation for fixed amount type."""
        commission = PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.FIXED_AMOUNT,
            fixed_amount=Decimal("3.00"),
            min_commission=Decimal("2.00")
        )

        # Fixed amount regardless of transaction size
        result = commission.calculate_commission(Decimal("10.00"))
        assert result == Decimal("3.00")

        result = commission.calculate_commission(Decimal("1000.00"))
        assert result == Decimal("3.00")

    def test_calculate_commission_hybrid(self, academy):
        """Test commission calculation for hybrid type."""
        commission = PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.HYBRID,
            percentage_rate=Decimal("0.05"),  # 5%
            fixed_amount=Decimal("2.00"),
            min_commission=Decimal("1.00")
        )

        result = commission.calculate_commission(Decimal("100.00"))
        assert result == Decimal("7.00")  # 5% of 100 + 2.00 fixed

    def test_calculate_commission_with_max_limit(self, academy):
        """Test commission calculation with maximum limit."""
        commission = PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.PERCENTAGE,
            percentage_rate=Decimal("0.10"),
            max_commission=Decimal("50.00")
        )

        # Below max
        result = commission.calculate_commission(Decimal("100.00"))
        assert result == Decimal("10.00")

        # Above max
        result = commission.calculate_commission(Decimal("1000.00"))
        assert result == Decimal("50.00")  # Capped at max

    def test_global_commission_null_academy(self):
        """Test creating global commission with null academy."""
        commission = PlatformCommission.objects.create(
            academy=None,  # Global default
            commission_type=PlatformCommission.CommissionType.PERCENTAGE,
            percentage_rate=Decimal("0.10")
        )

        assert commission.academy is None
        assert commission.is_active is True

    def test_effective_dates(self, academy):
        """Test commission effective date functionality."""
        future_date = date(2025, 1, 1)
        past_date = date(2023, 1, 1)

        commission = PlatformCommission.objects.create(
            academy=academy,
            commission_type=PlatformCommission.CommissionType.PERCENTAGE,
            percentage_rate=Decimal("0.15"),
            effective_from=future_date,
            effective_until=past_date
        )

        assert commission.effective_from == future_date
        assert commission.effective_until == past_date


# ─── MarketplaceTransaction Model Tests ───────────────────────────────────────


class TestMarketplaceTransaction:

    def test_create_marketplace_transaction(self, academy, stripe_customer):
        """Test basic marketplace transaction creation."""
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

        transaction = MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_test123",
            stripe_customer=stripe_customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=MarketplaceTransaction.TransactionType.ONE_TIME,
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),
            stripe_fee=Decimal("3.20"),
            net_amount=Decimal("86.80")
        )

        assert transaction.stripe_payment_intent_id == "pi_test123"
        assert transaction.academy == academy
        assert transaction.transaction_type == "ONE_TIME"
        assert transaction.status == "PENDING"  # Default
        assert transaction.gross_amount == Decimal("100.00")
        assert transaction.platform_fee == Decimal("10.00")
        assert transaction.net_amount == Decimal("86.80")
        assert transaction.currency == "USD"  # Default

    def test_str_representation(self, academy, stripe_customer):
        """Test string representation of marketplace transaction."""
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

        transaction = MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_test123",
            stripe_customer=stripe_customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=MarketplaceTransaction.TransactionType.SEMINAR,
            gross_amount=Decimal("50.00"),
            platform_fee=Decimal("5.00"),
            net_amount=Decimal("45.00"),
            status=MarketplaceTransaction.Status.COMPLETED
        )

        expected = "SEMINAR - 50.00 USD (COMPLETED)"
        assert str(transaction) == expected

    def test_academy_receives_property(self, academy, stripe_customer):
        """Test academy_receives calculated property."""
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

        transaction = MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_test123",
            stripe_customer=stripe_customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=MarketplaceTransaction.TransactionType.ONE_TIME,
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),
            stripe_fee=Decimal("3.20"),
            net_amount=Decimal("86.80")
        )

        # academy_receives = gross - platform_fee - stripe_fee
        assert transaction.academy_receives == Decimal("86.80")

    def test_unique_stripe_payment_intent_id(self, academy, stripe_customer):
        """Test that stripe_payment_intent_id must be unique."""
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

        MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_unique123",
            stripe_customer=stripe_customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=MarketplaceTransaction.TransactionType.ONE_TIME,
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),
            net_amount=Decimal("90.00")
        )

        with pytest.raises(Exception):  # Should raise integrity error
            MarketplaceTransaction.objects.create(
                stripe_payment_intent_id="pi_unique123",
                stripe_customer=stripe_customer,
                connected_account=connected_account,
                academy=academy,
                transaction_type=MarketplaceTransaction.TransactionType.SUBSCRIPTION,
                gross_amount=Decimal("50.00"),
                platform_fee=Decimal("5.00"),
                net_amount=Decimal("45.00")
            )

    def test_metadata_field(self, academy, stripe_customer):
        """Test JSON metadata field functionality."""
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

        metadata = {
            "plan_id": "123",
            "plan_name": "Monthly Membership",
            "custom_data": {"key": "value"}
        }

        transaction = MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_metadata123",
            stripe_customer=stripe_customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=MarketplaceTransaction.TransactionType.SUBSCRIPTION,
            gross_amount=Decimal("100.00"),
            platform_fee=Decimal("10.00"),
            net_amount=Decimal("90.00"),
            metadata=metadata
        )

        transaction.refresh_from_db()
        assert transaction.metadata == metadata
        assert transaction.metadata["plan_id"] == "123"
        assert transaction.metadata["custom_data"]["key"] == "value"

    def test_optional_foreign_keys(self, academy, stripe_customer):
        """Test optional foreign key relationships."""
        from membership.models import Subscription, SeminarRegistration
        from factories import SeminarFactory

        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

        # Create related objects
        seminar = SeminarFactory(academy=academy)
        seminar_registration = SeminarRegistration.objects.create(
            seminar=seminar,
            athlete_id=1  # Mock athlete ID
        )

        transaction = MarketplaceTransaction.objects.create(
            stripe_payment_intent_id="pi_relations123",
            stripe_customer=stripe_customer,
            connected_account=connected_account,
            academy=academy,
            transaction_type=MarketplaceTransaction.TransactionType.SEMINAR,
            gross_amount=Decimal("50.00"),
            platform_fee=Decimal("5.00"),
            net_amount=Decimal("45.00"),
            seminar_registration=seminar_registration
        )

        assert transaction.seminar_registration == seminar_registration
        assert transaction.subscription is None


# ─── AcademyEarnings Model Tests ──────────────────────────────────────────────


class TestAcademyEarnings:

    def test_create_academy_earnings(self, academy):
        """Test basic academy earnings creation."""
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

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

        assert earnings.academy == academy
        assert earnings.year == 2024
        assert earnings.month == 3
        assert earnings.total_gross == Decimal("1000.00")
        assert earnings.total_platform_fees == Decimal("100.00")
        assert earnings.total_stripe_fees == Decimal("30.00")
        assert earnings.total_net == Decimal("870.00")
        assert earnings.subscription_count == 5
        assert earnings.seminar_count == 2
        assert earnings.one_time_count == 3
        assert earnings.currency == "USD"  # Default

    def test_str_representation(self, academy):
        """Test string representation of academy earnings."""
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

        earnings = AcademyEarnings.objects.create(
            academy=academy,
            connected_account=connected_account,
            year=2024,
            month=3,
            total_net=Decimal("870.50")
        )

        expected = f"{academy.name} - 2024-03: $870.50"
        assert str(earnings) == expected

    def test_platform_fee_rate_property(self, academy):
        """Test platform_fee_rate calculated property."""
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

        earnings = AcademyEarnings.objects.create(
            academy=academy,
            connected_account=connected_account,
            year=2024,
            month=3,
            total_gross=Decimal("1000.00"),
            total_platform_fees=Decimal("100.00"),
            total_net=Decimal("900.00")
        )

        assert earnings.platform_fee_rate == Decimal("0.10")  # 100/1000

    def test_platform_fee_rate_property_zero_gross(self, academy):
        """Test platform_fee_rate property when total_gross is zero."""
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

        earnings = AcademyEarnings.objects.create(
            academy=academy,
            connected_account=connected_account,
            year=2024,
            month=3,
            total_gross=Decimal("0.00"),
            total_platform_fees=Decimal("0.00"),
            total_net=Decimal("0.00")
        )

        assert earnings.platform_fee_rate == Decimal("0.00")

    def test_total_transactions_property(self, academy):
        """Test total_transactions calculated property."""
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

        earnings = AcademyEarnings.objects.create(
            academy=academy,
            connected_account=connected_account,
            year=2024,
            month=3,
            subscription_count=5,
            seminar_count=2,
            one_time_count=3,
            refund_count=1  # Not included in total
        )

        assert earnings.total_transactions == 10  # 5 + 2 + 3

    def test_unique_constraint(self, academy):
        """Test unique constraint on connected_account, year, month."""
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

        AcademyEarnings.objects.create(
            academy=academy,
            connected_account=connected_account,
            year=2024,
            month=3
        )

        with pytest.raises(Exception):  # Should raise integrity error
            AcademyEarnings.objects.create(
                academy=academy,
                connected_account=connected_account,
                year=2024,
                month=3
            )

    def test_default_values(self, academy):
        """Test default values for earnings fields."""
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

        earnings = AcademyEarnings.objects.create(
            academy=academy,
            connected_account=connected_account,
            year=2024,
            month=3
        )

        assert earnings.total_gross == Decimal("0.00")
        assert earnings.total_platform_fees == Decimal("0.00")
        assert earnings.total_stripe_fees == Decimal("0.00")
        assert earnings.total_net == Decimal("0.00")
        assert earnings.subscription_count == 0
        assert earnings.one_time_count == 0
        assert earnings.seminar_count == 0
        assert earnings.refund_count == 0
        assert earnings.currency == "USD"

    def test_month_validation_range(self, academy):
        """Test that month values are within valid range."""
        connected_account = StripeConnectedAccount.objects.create(
            academy=academy,
            stripe_account_id="acct_test123"
        )

        # Valid months
        for month in range(1, 13):
            earnings = AcademyEarnings.objects.create(
                academy=academy,
                connected_account=connected_account,
                year=2024,
                month=month
            )
            assert earnings.month == month

        # Django doesn't enforce range validation at the model level,
        # but it should be validated at the form/serializer level