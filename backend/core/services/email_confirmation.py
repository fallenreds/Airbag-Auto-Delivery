"""
Підтвердження пошти при реєстрації.

Токен — підписаний payload (`django.core.signing`), а не генератор із
`contrib.auth.tokens`: у того термін життя жорстко прив'язаний до
PASSWORD_RESET_TIMEOUT (у нас година), а посилання підтвердження має жити
кілька діб — його відкривають не одразу, а коли дійдуть руки до скриньки.

У payload лежить і email, тож зміна пошти автоматично вбиває старі посилання.
Повторний перехід за вже використаним посиланням нічого не ламає: акаунт уже
підтверджений, відповідь та сама.
"""
import logging

from django.conf import settings
from django.core import signing

from core.models import Client
from core.services.password_reset import normalize_locale

logger = logging.getLogger(__name__)

SALT = "core.email-confirmation"

# Одна відповідь на всі випадки, щоб форма повторної відправки не
# перетворилась на оракул існування акаунтів.
GENERIC_RESEND_MESSAGE = (
    "If an account with that email exists and is not confirmed yet, "
    "a confirmation link has been sent."
)
INVALID_TOKEN_MESSAGE = "This confirmation link is invalid or has expired."


def needs_confirmation(user):
    """Кому взагалі має сенс слати лист підтвердження."""
    return bool(
        user
        and user.is_active
        and not user.is_guest
        and user.email
        and not user.email_confirmed
    )


def make_token(user):
    return signing.dumps({"pk": user.pk, "email": user.email}, salt=SALT)


def build_confirmation_url(user, locale):
    token = make_token(user)
    return (
        f"{settings.FRONTEND_URL}/{normalize_locale(locale)}"
        f"/confirm-email?token={token}"
    )


def resolve_token(token):
    """token -> Client або None на будь-яку проблему (биті дані, протух, немає юзера)."""
    try:
        payload = signing.loads(
            token, salt=SALT, max_age=settings.EMAIL_CONFIRMATION_TIMEOUT
        )
    except signing.BadSignature:
        return None

    user = Client.objects.filter(pk=payload.get("pk")).first()
    if user is None or user.is_guest or not user.is_active:
        return None

    # Пошту змінили після видачі посилання — старе посилання не має спрацювати.
    if (user.email or "").lower() != (payload.get("email") or "").lower():
        return None

    return user


def confirm(user):
    """Ідемпотентно: повторне підтвердження не помилка."""
    if not user.email_confirmed:
        user.email_confirmed = True
        user.save(update_fields=["email_confirmed"])
    return user


def send_confirmation_email(user_id, confirmation_url, locale):
    """Синхронна відправка. Викликається напряму або з Celery-таски."""
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string

    user = Client.objects.filter(pk=user_id).first()
    if not user or not user.email:
        return

    context = {
        "name": user.name or user.email,
        "confirmation_url": confirmation_url,
        "expires_hours": max(1, settings.EMAIL_CONFIRMATION_TIMEOUT // 3600),
        "site_url": settings.FRONTEND_URL,
    }

    message = EmailMultiAlternatives(
        subject="Підтвердження пошти — AirbagAD",
        body=render_to_string("emails/email_confirmation.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(
        render_to_string("emails/email_confirmation.html", context), "text/html"
    )
    message.send(fail_silently=False)


def dispatch_confirmation_email(user, locale):
    """
    Відправити лист, не даючи ендпоінту впасти.

    Реєстрація не повинна зірватись через недоступний брокер чи збій пошти:
    акаунт уже створено, лист можна перевідправити кнопкою «надіслати ще раз».
    """
    url = build_confirmation_url(user, locale)

    if settings.PASSWORD_RESET_EMAIL_ASYNC:
        try:
            from core.tasks import send_email_confirmation_task

            send_email_confirmation_task.delay(user.pk, url, normalize_locale(locale))
            return
        except Exception:
            logger.exception(
                "Email confirmation: Celery dispatch failed, falling back to sync send"
            )

    try:
        send_confirmation_email(user.pk, url, normalize_locale(locale))
    except Exception:
        logger.exception(
            "Email confirmation: send failed for client=%s", user.pk
        )
