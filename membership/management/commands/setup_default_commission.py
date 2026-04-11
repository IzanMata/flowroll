"""
Django management command to set up default platform commission.
"""

from django.core.management.base import BaseCommand
from decimal import Decimal

from membership.models import PlatformCommission


class Command(BaseCommand):
    help = "Set up default platform commission (10%)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--rate",
            type=str,
            default="0.1000",
            help="Commission rate as decimal (default: 0.1000 for 10%)"
        )
        parser.add_argument(
            "--min-commission",
            type=str,
            default="0.50",
            help="Minimum commission amount (default: 0.50)"
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing default commission"
        )

    def handle(self, *args, **options):
        rate = Decimal(options["rate"])
        min_commission = Decimal(options["min_commission"])
        overwrite = options["overwrite"]

        # Check if default commission already exists
        existing = PlatformCommission.objects.filter(
            academy__isnull=True,
            is_active=True
        ).first()

        if existing and not overwrite:
            self.stdout.write(
                self.style.WARNING(
                    f"Default commission already exists: {existing.percentage_rate * 100:.1f}%. "
                    f"Use --overwrite to replace it."
                )
            )
            return

        if existing and overwrite:
            existing.is_active = False
            existing.save()
            self.stdout.write(
                self.style.WARNING(f"Deactivated existing commission: {existing.percentage_rate * 100:.1f}%")
            )

        # Create new default commission
        commission = PlatformCommission.objects.create(
            academy=None,  # Global default
            commission_type=PlatformCommission.CommissionType.PERCENTAGE,
            percentage_rate=rate,
            min_commission=min_commission,
            is_active=True
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Default platform commission created: {rate * 100:.1f}% "
                f"(min: ${min_commission})"
            )
        )

        # Show commission breakdown example
        test_amounts = [Decimal("10.00"), Decimal("50.00"), Decimal("100.00")]
        self.stdout.write(self.style.SUCCESS("\n📊 Commission breakdown examples:"))

        for amount in test_amounts:
            commission_amount = commission.calculate_commission(amount)
            academy_receives = amount - commission_amount
            stripe_fee = amount * Decimal("0.029") + Decimal("0.30")  # Approximate Stripe fee
            academy_net = academy_receives - stripe_fee

            self.stdout.write(
                f"  ${amount}: Platform ${commission_amount:.2f} | "
                f"Academy ${academy_receives:.2f} | "
                f"Stripe ~${stripe_fee:.2f} | "
                f"Net to Academy ~${academy_net:.2f}"
            )