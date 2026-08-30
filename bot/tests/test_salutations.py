"""
Обращение в каждом сообщении о событии.

Один и тот же человек бывает и админом, и клиентом: заказ, оформленный на
аккаунт админа, приносит ему обе половины уведомлений. Без обращения они
сливаются в один непонятный поток — именно так выглядела жалоба, с которой
началась эта правка.

Правило: админское сообщение начинается с «Шановний адміністратор»,
клиентское — с «Шановний клієнт». Карточка заказа исключение: она приходит и
по событию, и по кнопке «Статус замовлень», и обращение в ответ на собственное
нажатие выглядело бы странно.
"""
from unittest.mock import AsyncMock, patch

import pytest

from tests.helpers import ADMIN_ID

ADMIN_MARK = "Шановний адміністратор"
CLIENT_MARK = "Шановний клієнт"


def texts_to(calls, chat_id):
    out = []
    for call in calls:
        if call.args and call.args[0] == chat_id:
            out.append(call.args[1] if len(call.args) > 1 else call.kwargs.get("text", ""))
        elif not call.args and call.kwargs.get("chat_id") == chat_id:
            out.append(call.kwargs.get("text", ""))
    return out


# (имя, есть ли параметр details, шлёт ли админам, шлёт ли клиенту)
EVENT_NOTIFICATIONS = [
    ("new_order_notification", False, True, False),
    ("remonline_created_notification", False, True, False),
    ("payment_confirmed_notification", False, True, True),
    ("payment_type_changed_notification", False, True, True),
    ("cancel_rejected_notification", True, True, True),
    ("canceled_notifications", True, True, True),
    ("cancel_requested_notifications", False, True, True),
    ("refunded_notifications", False, True, True),
    ("deactivated_notifications", False, True, True),
    ("deleted_notifications", True, True, True),
]


async def _run(name, has_details, sample_order, sample_client):
    """Зовёт уведомление, возвращает (тексты админам, тексты клиенту)."""
    import notifications
    fn = getattr(notifications, name)
    fake_bot = AsyncMock()
    order = dict(sample_order, cancel_state="requested")

    with patch.object(notifications, "send_messages_to_admins", AsyncMock()) as to_admins, \
         patch.object(notifications, "get_client_by_id", AsyncMock(return_value=sample_client)):
        if has_details:
            await fn(fake_bot, order, "деталі", [ADMIN_ID])
        else:
            await fn(fake_bot, order, [ADMIN_ID])

    admin_texts = [c.args[2] for c in to_admins.await_args_list if len(c.args) > 2]
    # cancel_requested_notifications шлёт админам напрямую, а не пачкой
    admin_texts += texts_to(fake_bot.send_message.await_args_list, ADMIN_ID)
    client_texts = texts_to(fake_bot.send_message.await_args_list, order["telegram_id"])
    return admin_texts, client_texts


@pytest.mark.parametrize("name,has_details,to_admin,to_client", EVENT_NOTIFICATIONS)
class TestSalutations:
    async def test_admin_half_is_addressed(self, sample_order, sample_client,
                                           name, has_details, to_admin, to_client):
        admin_texts, _ = await _run(name, has_details, sample_order, sample_client)
        if not to_admin:
            return
        assert admin_texts, f"{name}: админам ничего не ушло"
        for text in admin_texts:
            assert text.startswith(f"<b>{ADMIN_MARK}!</b>"), f"{name}: {text[:60]!r}"

    async def test_client_half_is_addressed(self, sample_order, sample_client,
                                            name, has_details, to_admin, to_client):
        _, client_texts = await _run(name, has_details, sample_order, sample_client)
        if not to_client:
            return
        assert client_texts, f"{name}: клиенту ничего не ушло"
        for text in client_texts:
            assert text.startswith(f"<b>{CLIENT_MARK}!</b>"), f"{name}: {text[:60]!r}"

    async def test_one_message_per_side(self, sample_order, sample_client,
                                        name, has_details, to_admin, to_client):
        """Одно событие — не больше одного сообщения каждой стороне."""
        admin_texts, client_texts = await _run(name, has_details, sample_order, sample_client)
        assert len(admin_texts) <= 1, f"{name}: админам {len(admin_texts)} сообщений"
        assert len(client_texts) <= 1, f"{name}: клиенту {len(client_texts)} сообщений"

    async def test_admin_and_client_halves_are_distinguishable(
        self, sample_order, sample_client, name, has_details, to_admin, to_client
    ):
        """Ради этого всё и затевалось: две половины нельзя перепутать."""
        admin_texts, client_texts = await _run(name, has_details, sample_order, sample_client)
        for text in admin_texts:
            assert CLIENT_MARK not in text, f"{name}: в админском тексте клиентское обращение"
        for text in client_texts:
            assert ADMIN_MARK not in text, f"{name}: в клиентском тексте админское обращение"


class TestSingleSidedNotifications:
    """Уведомления, у которых сторона одна — обращение всё равно обязательно."""

    async def test_ttn_update_addresses_the_client(self, sample_order):
        import notifications
        fake_bot = AsyncMock()
        order = dict(sample_order, ttn="59001259868043")

        await notifications.ttn_update_notification(fake_bot, order)

        assert fake_bot.send_message.await_args.args[1].startswith(f"<b>{CLIENT_MARK}!</b>")

    async def test_in_branch_addresses_the_client(self, sample_order):
        import notifications
        fake_bot = AsyncMock()
        order = dict(sample_order, ttn="59001259868043")

        with patch.object(notifications, "update_branch_remember_count", AsyncMock()):
            await notifications.order_in_branch_notifications(fake_bot, order)

        assert fake_bot.send_message.await_args.args[1].startswith(f"<b>{CLIENT_MARK}!</b>")

    async def test_merged_addresses_the_client(self, sample_order):
        import notifications
        fake_bot = AsyncMock()

        await notifications.merge_order_notification(fake_bot, sample_order)

        assert fake_bot.send_message.await_args.args[1].startswith(f"<b>{CLIENT_MARK}!</b>")

    async def test_new_client_addresses_the_admin(self, sample_client):
        import updates
        fake_bot = AsyncMock()

        with patch.object(updates, "send_messages_to_admins", AsyncMock()) as to_admins:
            await updates.CLIENT_EVENT_HANDLERS["CREATED"](
                fake_bot, sample_client, {"type": "CREATED"}, [ADMIN_ID]
            )

        assert to_admins.await_args.kwargs["text"].startswith(f"<b>{ADMIN_MARK}!</b>")


class TestOrderCardStaysPlain:
    async def test_client_order_card_has_no_salutation(self, sample_order, sample_client):
        """
        Карточка приходит и по событию, и по кнопке «Статус замовлень» — по
        решению владельца обращение в неё не добавляем.
        """
        import notifications
        fake_bot = AsyncMock()

        with patch.object(notifications, "get_client_by_id", AsyncMock(return_value=sample_client)), \
             patch.object(notifications, "make_order", AsyncMock()) as card:
            await notifications.new_order_client_notification(fake_bot, sample_order)

        card.assert_awaited_once()
        fake_bot.send_message.assert_not_awaited()
