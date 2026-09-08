"""
Скидання пароля через email.

Токен — stateless (`django.contrib.auth.tokens`): у HMAC входить хеш пароля і
`last_login`, тож посилання «згорає» саме по собі після зміни пароля або після
успішного входу. Окрема таблиця і прибирання протухлих рядків не потрібні,
одноразовість виходить безкоштовно.

Термін життя задає `settings.PASSWORD_RESET_TIMEOUT`.
"""
import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from core.models import Client

logger = logging.getLogger(__name__)

# Одне повідомлення на всі випадки: акаунт існує, не існує, гість, деактивований,
# лист не відправився. Інакше форма перетворюється на оракул існування акаунтів.
GENERIC_REQUEST_MESSAGE = (
    "If an account with that email exists, a reset link has been sent."
)
INVALID_TOKEN_MESSAGE = "This password reset link is invalid or has expired."


def _is_resettable(user):
    """Деактивовані і акаунти без email/пароля скидати пароль не можуть."""
    return bool(
        user
        and user.is_active
        and user.email
        and user.has_usable_password()
    )


def find_resettable_client(email):
    """Знайти отримувача листа або None."""
    if not email:
        return None

    user = (
        Client.objects.filter(email__iexact=email.strip())
        .exclude(email__isnull=True)
        .exclude(email="")
        .first()
    )
    return user if _is_resettable(user) else None


def normalize_locale(locale):
    """Локаль з тіла запиту потрапляє в URL — пускаємо лише через білий список."""
    if locale in settings.FRONTEND_LOCALES:
        return locale
    return settings.FRONTEND_DEFAULT_LOCALE


def build_reset_url(user, locale):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return (
        f"{settings.FRONTEND_URL}/{normalize_locale(locale)}"
        f"/forgot/reset?uid={uid}&token={token}"
    )


def resolve_uid(uidb64):
    """uidb64 -> Client. None на будь-яку проблему: биті дані, немає юзера, не той тип."""
    try:
        pk = force_str(urlsafe_base64_decode(uidb64))
        user = Client.objects.get(pk=pk)
    except (TypeError, ValueError, OverflowError, Client.DoesNotExist):
        return None

    # Повторна перевірка: акаунт міг стати гостем/деактивуватись уже після видачі посилання.
    return user if _is_resettable(user) else None


def send_password_reset_email(user_id, reset_url, locale):
    """Синхронна відправка. Викликається напряму або з Celery-таски."""
    user = Client.objects.filter(pk=user_id).first()
    if not user or not user.email:
        return

    context = {
        "name": user.name or user.email,
        "reset_url": reset_url,
        "expires_hours": max(1, settings.PASSWORD_RESET_TIMEOUT // 3600),
        "site_url": settings.FRONTEND_URL,
        "locale": normalize_locale(locale),
    }

    message = EmailMultiAlternatives(
        subject="Відновлення пароля — AirbagAD",
        body=render_to_string("emails/password_reset.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(
        render_to_string("emails/password_reset.html", context), "text/html"
    )
    message.send(fail_silently=False)


def dispatch_reset_email(user, locale):
    """
    Відправити лист, не даючи ендпоінту впасти.

    Будь-яка помилка (недоступний брокер, збій SMTP) лише логується: ендпоінт
    зобов'язаний віддати 200 у всіх випадках, інакше зламається анти-енумерація.
    """
    reset_url = build_reset_url(user, locale)

    if settings.PASSWORD_RESET_EMAIL_ASYNC:
        try:
            from core.tasks import send_password_reset_email_task

            send_password_reset_email_task.delay(user.pk, reset_url, locale)
            return
        except Exception:
            logger.exception(
                "Password reset: Celery dispatch failed, falling back to sync send"
            )

    try:
        send_password_reset_email(user.pk, reset_url, locale)
    except Exception:
        logger.exception("Password reset: email send failed for client=%s", user.pk)
