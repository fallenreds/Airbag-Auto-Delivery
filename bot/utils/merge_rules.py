"""
Какие заказы можно объединять.

Правило то же, что на бэкенде (`OrderViewSet._merge_refusal`): объединять
разрешено только однотипные заказы — две наложки либо две предоплаты, обе
оплаченные. Иначе объединённый заказ пришлось бы создавать «наполовину
оплаченным», а деньги за одну из половин уже приняты.

Бэкенд отвечает на такую пару ошибкой, но админ не должен до неё доходить:
в списке для объединения показываем только подходящие заказы. Дублирование
правила осознанное — интерфейс обязан отсеивать неподходящее заранее, а
последнее слово всё равно за бэкендом.
"""


def payment_kind(order: dict) -> str:
    """Способ оплаты одним значением — для сравнения двух заказов."""
    if order.get("bank_transfer"):
        return "bank_transfer"
    if order.get("prepayment"):
        return "online"
    return "postpaid"


def is_prepaid_flow(order: dict) -> bool:
    """Клиент платит до отгрузки — картой или по реквизитам."""
    return bool(order.get("prepayment") or order.get("bank_transfer"))


def can_merge(one: dict, other: dict) -> bool:
    """Можно ли объединить эти два заказа."""
    if not one or not other:
        return False
    if one.get("id") == other.get("id"):
        return False
    if payment_kind(one) != payment_kind(other):
        return False
    if is_prepaid_flow(one) and not (one.get("is_paid") and other.get("is_paid")):
        return False
    return True
