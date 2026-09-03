"""
FSM ввода ТТН админом.

Обработчик когда-то сам слал клиенту уведомление о ТТН. Потом бэкенд научился
создавать на изменение поля событие `TTN_UPDATED`, и клиент стал получать
сообщение дважды — второе от поллера. Прямой вызов убрали; тесты закрывают
именно это: обработчик обновляет ТТН, отвечает админу и больше никому ничего
не шлёт.

Сам FSM до этого не был покрыт вовсе — потому дубль и не поймали.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from tests.helpers import ADMIN_ID, make_message

ORDER_ID = "113254"
TTN = "59000123456789"


def _fsm_state(order_id=ORDER_ID, ttn=TTN):
    """FSMContext-заглушка: `async with state.proxy()` плюс `get_data`."""
    state = MagicMock()
    proxy = AsyncMock()
    proxy.__aenter__.return_value = {}
    state.proxy.return_value = proxy
    state.get_data = AsyncMock(return_value={"order_id": order_id, "ttn_state": ttn})
    state.finish = AsyncMock()
    return state


class TestTtnEntry:
    async def test_updates_ttn_and_answers_admin_only(self, bot_module, fake_bot):
        state = _fsm_state()
        message = make_message(TTN, chat_id=ADMIN_ID)

        with patch.object(type(message), "reply", AsyncMock()) as reply, \
             patch.object(bot_module, "update_ttn",
                          AsyncMock(return_value={"id": int(ORDER_ID)})) as update, \
             patch.object(bot_module, "get_order_by_id", AsyncMock()) as get_order, \
             patch.object(bot_module, "send_error_log", AsyncMock()) as error_log:
            await bot_module.ttn_state(message, state)

        update.assert_awaited_once_with(ORDER_ID, TTN)
        reply.assert_awaited_once()
        error_log.assert_not_awaited()

        # Клиенту отсюда не пишем: об этом скажет поллер по событию TTN_UPDATED.
        get_order.assert_not_awaited()
        fake_bot.send_message.assert_not_awaited()

    async def test_missing_order_reports_error_to_admin(self, bot_module, fake_bot):
        state = _fsm_state()
        message = make_message(TTN, chat_id=ADMIN_ID)

        with patch.object(type(message), "reply", AsyncMock()) as reply, \
             patch.object(bot_module, "update_ttn", AsyncMock(return_value=None)), \
             patch.object(bot_module, "send_error_log", AsyncMock()) as error_log:
            await bot_module.ttn_state(message, state)

        assert "не знайдено" in reply.await_args.args[0]
        error_log.assert_not_awaited()
        fake_bot.send_message.assert_not_awaited()
