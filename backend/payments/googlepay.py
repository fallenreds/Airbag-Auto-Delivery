import json
from typing import Any, Dict


class GooglePayTokenValidationError(ValueError):
    pass


def validate_google_pay_g_token(g_token: str) -> Dict[str, Any]:
    """Минимальная валидация формата gToken.

    Monobank ожидает gToken как строку, которая выглядит как JSON Google Pay ECv2,
    например: {"signature":..., "protocolVersion":"ECv2", "signedMessage":...}

    Здесь НЕТ криптографической верификации подписи (это делает платёжный шлюз/эквайер).
    Задача — отсеять явно неверные значения и убедиться, что формат пригоден для отправки в Mono.
    """

    if not isinstance(g_token, str):
        raise GooglePayTokenValidationError("gToken must be a string")

    token = g_token.strip()
    if not token:
        raise GooglePayTokenValidationError("gToken is empty")

    # Google Pay gateway token обычно JSON строка
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError as exc:
        raise GooglePayTokenValidationError(
            "gToken must be a JSON string (try to pass paymentMethodData.tokenizationData.token as-is)"
        ) from exc

    if not isinstance(parsed, dict):
        raise GooglePayTokenValidationError("gToken JSON must be an object")

    protocol = parsed.get("protocolVersion")
    if protocol != "ECv2":
        # В реальности могут быть и другие версии, но в доке Google Pay чаще ECv2
        raise GooglePayTokenValidationError(f"Unsupported protocolVersion: {protocol}")

    for key in ("signature", "signedMessage"):
        if key not in parsed or not isinstance(parsed[key], str) or not parsed[key].strip():
            raise GooglePayTokenValidationError(f"Missing or invalid field: {key}")

    isk = parsed.get("intermediateSigningKey")
    if not isinstance(isk, dict):
        raise GooglePayTokenValidationError("Missing or invalid intermediateSigningKey")

    # signedKey — строка с JSON
    signed_key = isk.get("signedKey")
    signatures = isk.get("signatures")
    if not isinstance(signed_key, str) or not signed_key.strip():
        raise GooglePayTokenValidationError("Missing or invalid intermediateSigningKey.signedKey")
    if not isinstance(signatures, list) or not signatures or not all(isinstance(s, str) and s for s in signatures):
        raise GooglePayTokenValidationError("Missing or invalid intermediateSigningKey.signatures")

    # signedMessage — строка с JSON
    try:
        signed_msg = json.loads(parsed["signedMessage"])
    except json.JSONDecodeError as exc:
        raise GooglePayTokenValidationError("signedMessage must be a JSON string") from exc

    if not isinstance(signed_msg, dict):
        raise GooglePayTokenValidationError("signedMessage JSON must be an object")

    for key in ("encryptedMessage", "ephemeralPublicKey", "tag"):
        if key not in signed_msg or not isinstance(signed_msg[key], str) or not signed_msg[key].strip():
            raise GooglePayTokenValidationError(f"Missing or invalid signedMessage.{key}")

    return parsed


def extract_g_token_from_payment_data(payment_data: Dict[str, Any]) -> str:
    """Достаёт gToken из paymentData Google Pay."""
    try:
        token = payment_data["paymentMethodData"]["tokenizationData"]["token"]
    except Exception as exc:
        raise GooglePayTokenValidationError(
            "paymentData must contain paymentMethodData.tokenizationData.token"
        ) from exc

    if not isinstance(token, str):
        raise GooglePayTokenValidationError("paymentData token must be a string")

    return token

