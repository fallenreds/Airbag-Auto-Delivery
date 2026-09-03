"""
Способ оплаты заказа — одинаково для всех мест, где он влияет на интерфейс.

Флаг «предоплата» означает «клиент платит до отгрузки» и стоит в том числе у
оплаты по реквизитам. Поэтому голая проверка `order["prepayment"]` больше не
отличает оплату картой от оплаты по реквизитам, и порядок условий начинает
значить: реквизиты проверяются первыми.
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


def is_bank_transfer(order: dict) -> bool:
    """Оплата по реквизитам: платит до отгрузки, но мимо monobank."""
    return bool(order.get("bank_transfer"))
