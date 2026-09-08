"""
Привязка Telegram к аккаунту.

Один Telegram — ровно один аккаунт, у аккаунта Telegram может быть несколько.
Занятый номер — это отказ с почтой владельца, а не слияние: слияния убраны
целиком (ADR-0021), потому что склеивали не тех и стирали вход.
"""
import logging

from rest_framework import status
from rest_framework.exceptions import APIException

from core.models import Client, ClientTelegram

logger = logging.getLogger(__name__)


class TelegramTaken(APIException):
    """
    Этот Telegram уже за другим аккаунтом.

    Почта владельца отдаётся как есть: Telegram криптографически принадлежит
    запросившему (подпись `initData`), поэтому чужого адреса он не узнаёт —
    только тот, что привязан к его же Telegram.
    """

    status_code = status.HTTP_409_CONFLICT
    default_code = "telegram_taken"

    def __init__(self, owner: Client):
        detail = {
                "code": self.default_code,
                "email": owner.email or None,
                "detail": (
                    f"Цей Telegram вже зареєстрований за поштою «{owner.email}». "
                    "Увійдіть у старий акаунт або зверніться до адміністратора."
                    if owner.email
                    else "Цей Telegram вже зареєстрований за іншим акаунтом без пошти. "
                    "Відкрийте магазин через Telegram-бота або зверніться до адміністратора."
                ),
            }
        super().__init__(detail)
        # DRF заворачивает значения в ErrorDetail и превращает None в 'None';
        # фронту нужен настоящий null, когда почты у владельца нет.
        self.detail = detail


def find_client_by_telegram(telegram_id) -> Client | None:
    link = (
        ClientTelegram.objects.select_related("client")
        .filter(telegram_id=telegram_id, client__is_active=True)
        .first()
    )
    return link.client if link else None


def _snapshot(tg_user: dict) -> dict:
    return {
        "username": (tg_user.get("username") or "").strip() or None,
        "first_name": (tg_user.get("first_name") or "").strip() or None,
        "last_name": (tg_user.get("last_name") or "").strip() or None,
    }


def link_telegram(client: Client, tg_user: dict) -> ClientTelegram:
    """
    Привязывает Telegram к клиенту. Повторная привязка того же — обновление снимка.

    Бросает `TelegramTaken`, если номер за другим аккаунтом.
    """
    telegram_id = int(tg_user["id"])
    existing = ClientTelegram.objects.select_related("client").filter(telegram_id=telegram_id).first()
    if existing is not None and existing.client_id != client.pk:
        raise TelegramTaken(existing.client)

    snapshot = _snapshot(tg_user)
    if existing is not None:
        for field, value in snapshot.items():
            setattr(existing, field, value)
        existing.save(update_fields=list(snapshot))
        return existing

    link = ClientTelegram.objects.create(client=client, telegram_id=telegram_id, **snapshot)
    logger.info("Linked telegram %s to client %s", telegram_id, client.pk)
    return link


def fill_profile_from_telegram(client: Client, tg_user: dict) -> list[str]:
    """Пустые поля профиля добираем из Telegram; заполненные не трогаем."""
    updated = []
    username = (tg_user.get("username") or "").strip()
    if username and not client.login and not Client.objects.filter(login=username).exists():
        client.login = username
        updated.append("login")
    first_name = (tg_user.get("first_name") or "").strip()
    if first_name and not client.name:
        client.name = first_name
        updated.append("name")
    last_name = (tg_user.get("last_name") or "").strip()
    if last_name and not client.last_name:
        client.last_name = last_name
        updated.append("last_name")
    if updated:
        client.save(update_fields=updated)
    return updated
