"""
Забор аккаунта, приехавшего из старой системы.

Старая версия бота не спрашивала почту — её нет ни в её базе, ни в заказах, ни
в RemOnline. Новая система входом считает почту, поэтому импортированный клиент
не может ни войти, ни сбросить пароль, ни зарегистрироваться (его телефон уже
занят его же записью).

Здесь одноразовая персональная ссылка, которую бот рассылает в личные чаты:
по ней клиент задаёт почту и пароль, и они ложатся в ту же запись — с историей
заказов, скидкой и связью с RemOnline.
"""
import logging

from django.conf import settings
from django.db.models import Q

from core.models import AccountClaimCode, Client
from core.services.discount_service import DiscountService

logger = logging.getLogger(__name__)

INVALID_CODE_MESSAGE = "Це посилання недійсне."
ALREADY_CLAIMED_MESSAGE = (
    "Цей акаунт вже активовано. Увійдіть за своєю поштою та паролем."
)
EMAIL_TAKEN_MESSAGE = "Ця пошта вже використовується іншим акаунтом."


def claimable_clients():
    """
    Кому нужна ссылка: есть Telegram, но нет рабочего входа на сайт.
    """
    return (
        Client.objects.filter(telegram_links__isnull=False, is_active=True)
        .filter(Q(email__isnull=True) | Q(email="") | Q(email_confirmed=False))
        .distinct()
        .order_by("id")
    )


def issue_code(client):
    """Код клиента, создавая его при необходимости. Повторный вызов не плодит коды."""
    existing = AccountClaimCode.objects.filter(client=client).first()
    if existing:
        return existing
    return AccountClaimCode.objects.create(client=client)


def resolve_code(code):
    """Запись по коду или None. Сам код валидным/погашенным не считает."""
    if not code:
        return None
    return (
        AccountClaimCode.objects.select_related("client")
        .filter(code=code.strip())
        .first()
    )


def mask_phone(phone):
    """
    `+380977626200` → `+38 097 ***-**-00`.

    Превью отдаётся без авторизации, поэтому телефон целиком показывать нельзя:
    подобранный код превратился бы в утечку персональных данных. Хвоста хватает,
    чтобы человек узнал свой номер.
    """
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(digits) < 6:
        return ""
    return f"+{digits[:2]} {digits[2:5]} ***-**-{digits[-2:]}"


def build_claim_url(claim, locale=None):
    locale = locale if locale in settings.FRONTEND_LOCALES else settings.FRONTEND_LOCALES[0]
    return f"{settings.FRONTEND_URL}/{locale}/claim/{claim.code}/"


def preview(claim):
    """Что показать на странице: «это вы?» без выдачи персональных данных."""
    client = claim.client
    try:
        percentage = DiscountService.get_client_discount_info(client).get(
            "discount_percentage", 0
        )
    except Exception:  # noqa: BLE001 - витрина не должна падать из-за расчёта
        logger.exception("Не удалось посчитать скидку для клиента %s", client.pk)
        percentage = 0

    return {
        "name": client.name or "",
        "last_name": client.last_name or "",
        "phone_hint": mask_phone(client.phone),
        "orders_count": client.orders.count(),
        "discount_percentage": percentage,
        "already_claimed": claim.is_spent,
    }


def email_is_taken(email, client):
    return (
        Client.objects.filter(email__iexact=email.strip())
        .exclude(pk=client.pk)
        .exists()
    )


def claim(claim_code, email, password):
    """
    Записывает почту и пароль в запись клиента.

    Почта остаётся неподтверждённой: код доказывает, что человек владеет
    Telegram-аккаунтом, но не тем ящиком, который он только что ввёл. Вход
    откроется после письма — как и у всех остальных.
    """
    client = claim_code.client
    client.email = email.strip().lower()
    client.email_confirmed = False
    client.set_password(password)
    client.save(update_fields=["email", "email_confirmed", "password"])
    return client
