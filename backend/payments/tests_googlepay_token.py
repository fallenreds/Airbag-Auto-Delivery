"""Структурная валидация токена Google Pay.

Это первый барьер перед отправкой в Monobank: если сюда просочится мусор,
ошибка вернётся уже от эквайера, без внятного текста для пользователя.
"""
import json

from django.test import SimpleTestCase

from payments.googlepay import (
    GooglePayTokenValidationError,
    extract_g_token_from_payment_data,
    validate_google_pay_g_token,
)
from payments.tests_factories import build_gtoken


class ValidateGooglePayTokenTests(SimpleTestCase):
    def test_valid_token_is_parsed(self):
        parsed = validate_google_pay_g_token(build_gtoken())

        self.assertEqual(parsed["protocolVersion"], "ECv2")

    def test_non_string_is_rejected(self):
        with self.assertRaises(GooglePayTokenValidationError):
            validate_google_pay_g_token({"protocolVersion": "ECv2"})

    def test_empty_string_is_rejected(self):
        with self.assertRaises(GooglePayTokenValidationError):
            validate_google_pay_g_token("   ")

    def test_non_json_is_rejected(self):
        with self.assertRaises(GooglePayTokenValidationError):
            validate_google_pay_g_token("not-json-at-all")

    def test_json_array_is_rejected(self):
        with self.assertRaises(GooglePayTokenValidationError):
            validate_google_pay_g_token("[1, 2, 3]")

    def test_wrong_protocol_version_is_rejected(self):
        with self.assertRaises(GooglePayTokenValidationError):
            validate_google_pay_g_token(build_gtoken(protocolVersion="ECv1"))

    def test_missing_signature_is_rejected(self):
        with self.assertRaises(GooglePayTokenValidationError):
            validate_google_pay_g_token(build_gtoken(signature=""))

    def test_missing_intermediate_signing_key_is_rejected(self):
        with self.assertRaises(GooglePayTokenValidationError):
            validate_google_pay_g_token(build_gtoken(intermediateSigningKey="nope"))

    def test_missing_signed_key_is_rejected(self):
        with self.assertRaises(GooglePayTokenValidationError):
            validate_google_pay_g_token(
                build_gtoken(
                    intermediateSigningKey={"signedKey": "", "signatures": ["s"]}
                )
            )

    def test_empty_signatures_list_is_rejected(self):
        with self.assertRaises(GooglePayTokenValidationError):
            validate_google_pay_g_token(
                build_gtoken(
                    intermediateSigningKey={"signedKey": "{}", "signatures": []}
                )
            )

    def test_signed_message_must_be_json(self):
        with self.assertRaises(GooglePayTokenValidationError):
            validate_google_pay_g_token(build_gtoken(signedMessage="not-json"))

    def test_signed_message_missing_tag_is_rejected(self):
        broken = json.dumps(
            {"encryptedMessage": "e", "ephemeralPublicKey": "k"}  # нет tag
        )
        with self.assertRaises(GooglePayTokenValidationError):
            validate_google_pay_g_token(build_gtoken(signedMessage=broken))


class ExtractGTokenTests(SimpleTestCase):
    def test_extracts_token_from_payment_data(self):
        token = extract_g_token_from_payment_data(
            {"paymentMethodData": {"tokenizationData": {"token": "abc"}}}
        )

        self.assertEqual(token, "abc")

    def test_missing_path_is_rejected(self):
        with self.assertRaises(GooglePayTokenValidationError):
            extract_g_token_from_payment_data({"paymentMethodData": {}})

    def test_non_string_token_is_rejected(self):
        with self.assertRaises(GooglePayTokenValidationError):
            extract_g_token_from_payment_data(
                {"paymentMethodData": {"tokenizationData": {"token": 123}}}
            )
