"""
Регрессы на дефекты, найденные ручной проверкой (см. «Знайдені дефекти»
в docs/BOT_FUNCTIONS.md).

Каждый тест описывает ПРАВИЛЬНОЕ поведение и помечен xfail(strict=True):
пока баг жив — тест ожидаемо падает и не красит прогон; как только его
починят, xfail превратится в XPASS и прогон упадёт, требуя снять маркер.
Так дефект не забывается и не «чинится обратно».
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.helpers import ADMIN_ID, CLIENT_ID, make_message


@pytest.mark.xfail(
    strict=True,
    reason="B7: is_discount делает split('@') с распаковкой в две переменные, "
           "поэтому текст с двумя и более '@' роняет хендлер ValueError",
)
@pytest.mark.parametrize("text", ["a@b@c", "1000@2@", "пошта@gmail.com@"])
async def test_discount_validation_survives_multiple_at_signs(bot_module, text):
    assert await bot_module.is_discount(text) is False


@pytest.mark.xfail(
    strict=True,
    reason="B7: из-за того же ValueError админ не получает подсказку про формат",
)
async def test_admin_gets_format_hint_on_broken_input(bot_module, fake_bot):
    msg = make_message("пошта@gmail.com@", chat_id=ADMIN_ID)

    with patch.object(bot_module, "post_discount", AsyncMock()):
        await bot_module.add_new_discount(msg)

    assert fake_bot.send_message.await_count >= 1, "бот не должен молчать"


@pytest.mark.xfail(
    strict=True,
    reason="B7-bis: хендлер Text(contains='@') ловит сообщения всех пользователей, "
           "но для не-админа обе ветки if/elif ложны — клиент, приславший email, "
           "не получает никакого ответа",
)
async def test_client_email_does_not_fall_into_silence(bot_module, fake_bot):
    msg = make_message("myemail@gmail.com", chat_id=CLIENT_ID)

    with patch.object(bot_module, "post_discount", AsyncMock()):
        await bot_module.add_new_discount(msg)

    assert fake_bot.send_message.await_count >= 1, "клиент остался без ответа"


@pytest.mark.xfail(
    strict=True,
    reason="B6: мёртвый хвост в конце _show_discount_page обращается к "
           "несуществующей переменной telegram_id (main.py:587)",
)
async def test_discount_page_does_not_raise(bot_module):
    bot_module._discount_cache[ADMIN_ID] = [
        {"id": 7, "month_payment": 1000, "percentage": "2.00"},
    ]
    fake = AsyncMock()

    await bot_module._show_discount_page(fake, ADMIN_ID, ADMIN_ID, 0)


@pytest.mark.xfail(
    strict=True,
    reason="Дубль уведомления: при отмене через бота клиент получает сообщение "
           "и от хендлера cancel_reason/, и от поллера CANCELED "
           "(canceled_notifications). При отмене с сайта — только одно",
)
async def test_client_is_not_notified_twice_on_cancel(bot_module, fake_bot, order_factory):
    """
    Сценарий: клиент отменил неоплаченный заказ кнопкой в боте.
    Хендлер уже отчитался клиенту — значит пришедшее следом событие CANCELED
    не должно слать клиенту второе сообщение.
    """
    import updates
    order = order_factory(id=5, telegram_id=CLIENT_ID, is_paid=False)

    # 1. клиент нажал причину — хендлер отвечает сам
    state = AsyncMock()
    from tests.helpers import make_callback
    cb = make_callback("cancel_reason/5/changed_mind", user_id=CLIENT_ID)
    cb.answer = AsyncMock()
    with patch.object(bot_module, "get_all_goods", AsyncMock(return_value=[])), \
         patch.object(bot_module, "get_order_by_id", AsyncMock(return_value=order)), \
         patch.object(bot_module, "cancel_order_request", AsyncMock(return_value=(True, {}))):
        await bot_module.callback_admin_panel(cb, state)

    from_handler = [c for c in fake_bot.send_message.await_args_list if c.args[0] == CLIENT_ID]

    # 2. следом поллер разбирает событие CANCELED по тому же заказу
    poller_bot = AsyncMock()
    canceled = dict(order, cancel_state="canceled")
    await updates.canceled_notifications(poller_bot, canceled, None, [ADMIN_ID])
    from_poller = [c for c in poller_bot.send_message.await_args_list if c.args[0] == CLIENT_ID]

    assert len(from_handler) + len(from_poller) == 1, (
        f"клиент получил {len(from_handler) + len(from_poller)} сообщений об отмене"
    )
