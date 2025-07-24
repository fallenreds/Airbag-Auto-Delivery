from django.apps import AppConfig
from core.scheduler import start_scheduler


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        import sys

        runner: str = sys.argv[0]
        if 'runserver' in runner or 'gunicorn' in runner or 'uwsgi' in runner:
            start_scheduler()
