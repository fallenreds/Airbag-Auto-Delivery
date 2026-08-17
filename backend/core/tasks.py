"""
Celery-таски застосунку core.

Підхоплюються автоматично через `app.autodiscover_tasks()` у config/celery.py.
"""
from celery import shared_task

from core.services.email_confirmation import send_confirmation_email
from core.services.password_reset import send_password_reset_email


@shared_task(
    name="core.send_password_reset_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    acks_late=True,
)
def send_password_reset_email_task(user_id, reset_url, locale):
    send_password_reset_email(user_id, reset_url, locale)


@shared_task(
    name="core.send_email_confirmation",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    acks_late=True,
)
def send_email_confirmation_task(user_id, confirmation_url, locale):
    send_confirmation_email(user_id, confirmation_url, locale)
