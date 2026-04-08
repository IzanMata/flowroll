from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    name = "payments"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        import stripe
        from django.conf import settings

        stripe.api_key = settings.STRIPE_SECRET_KEY
        stripe.api_version = settings.STRIPE_API_VERSION
