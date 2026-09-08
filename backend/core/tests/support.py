"""Общее для тестов: Telegram теперь в привязках, а не в поле клиента."""
from core.models import ClientTelegram


def link_telegram(client, telegram_id, **snapshot):
    return ClientTelegram.objects.create(client=client, telegram_id=telegram_id, **snapshot)


def telegram_of(client):
    """Первый привязанный Telegram или None — то, что раньше лежало в `Client.telegram_id`."""
    ids = client.telegram_ids
    return ids[0] if ids else None
