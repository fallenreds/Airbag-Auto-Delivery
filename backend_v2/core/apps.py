from django.apps import AppConfig
from core.scheduler import start_scheduler


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        import sys
        if 'runserver' in sys.argv or 'gunicorn' in sys.argv or 'uwsgi' in sys.argv:
            start_scheduler()
