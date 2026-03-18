from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        """Wire up post_migrate signal for auto-seeding."""
        from core import signals  # noqa
