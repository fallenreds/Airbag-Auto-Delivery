"""
Единый формат телефона: `+380XXXXXXXXX`.

Телефон — ключ клиента: по нему заводится контрагент в RemOnline и по нему же
ищется дубль. Пока формат не нормализовался, `0958398519` и `+380958398519`
были для базы двумя разными людьми (клиенты 86 и 208), и вторая запись
блокировала первому оформление заказа — «телефон уже занят».

Нормализация одна на всю систему: сериализаторы, миграция, RemOnline.
"""
import re

PHONE_RE = re.compile(r"^\+380\d{9}$")

INVALID_PHONE_MESSAGE = "Телефон має бути у форматі +380XXXXXXXXX."


def try_normalize_phone(raw):
    """`+380…` для любого узнаваемого украинского номера, иначе None."""
    if raw is None:
        return None
    text = str(raw).strip()
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    if len(digits) == 12 and digits.startswith("380"):
        return "+" + digits
    if text.startswith("+"):
        # Явный международный префикс — значит, номер должен быть полным.
        return None
    if len(digits) == 10 and digits.startswith("0"):
        return "+38" + digits
    if len(digits) == 9 and not digits.startswith("38"):
        # Девять цифр без кода страны: 501234567. Начало на «38» — не оператор,
        # а обрезанный код страны, такое не принимаем.
        return "+380" + digits
    return None


def normalize_phone(raw):
    """Как `try_normalize_phone`, но неузнаваемый номер — это ошибка, а не None."""
    normalized = try_normalize_phone(raw)
    if normalized is None:
        raise ValueError(INVALID_PHONE_MESSAGE)
    return normalized


def is_normalized(value):
    return bool(value) and PHONE_RE.match(value) is not None
