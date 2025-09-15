from django.apps import AppConfig

from core.scheduler import start_scheduler


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        import sys

        # Previously we only checked the last CLI argument, which fails under Gunicorn
        # because the last arg is typically the bind address (e.g., "0.0.0.0:8000").
        # Scan all arguments instead to detect the runner reliably.
        argv = " ".join(sys.argv)
        if any(name in argv for name in ("runserver", "gunicorn", "uwsgi")):
            start_scheduler()
