"""Общие хелперы для платёжных тестов (тестов тут нет)."""
import json
from typing import Any, Dict


def build_gtoken(**overrides: Any) -> str:
    """Структурно валидный ECv2-токен Google Pay.

    Криптография не проверяется ни нашим кодом, ни тестами — расшифровкой
    занимается Monobank, поэтому достаточно правильной формы.
    Через overrides можно сломать любое отдельное поле.
    """
    signed_message = json.dumps(
        {
            "encryptedMessage": "stub-encrypted",
            "ephemeralPublicKey": "stub-ephemeral",
            "tag": "stub-tag",
        }
    )
    token: Dict[str, Any] = {
        "protocolVersion": "ECv2",
        "signature": "stub-signature",
        "signedMessage": signed_message,
        "intermediateSigningKey": {
            "signedKey": json.dumps(
                {"keyValue": "stub-key", "keyExpiration": "1787132764000"}
            ),
            "signatures": ["stub-isk-signature"],
        },
    }
    token.update(overrides)
    return json.dumps(token)
