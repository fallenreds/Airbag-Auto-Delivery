"""
Один формат телефона на всю систему: `+380XXXXXXXXX`.

До нормализации `0958398519` и `+380958398519` были двумя разными клиентами
(записи 86 и 208 на бою), и вторая блокировала первому оформление заказа.
"""
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import Client
from core.phone import is_normalized, normalize_phone, try_normalize_phone


class NormalizeTests(TestCase):
    def test_every_common_spelling_becomes_one_value(self):
        for raw in (
            "+380501234567", "380501234567", "0501234567", "501234567",
            "050 123-45-67", "+38 (050) 123 45 67", " 0501234567 ",
        ):
            self.assertEqual(try_normalize_phone(raw), "+380501234567", raw)

    def test_unrecognizable_numbers_are_rejected(self):
        # Шесть таких лежат в старых заказах на бою — опечатки с пропущенной цифрой.
        for raw in ("", None, "+30978493653", "80932936677", "12345", "+380501234"):
            self.assertIsNone(try_normalize_phone(raw), raw)

    def test_strict_variant_raises(self):
        with self.assertRaises(ValueError):
            normalize_phone("80932936677")

    def test_is_normalized(self):
        self.assertTrue(is_normalized("+380501234567"))
        self.assertFalse(is_normalized("0501234567"))
        self.assertFalse(is_normalized(""))


class ConstraintTests(TestCase):
    """База не примет ничего, кроме NULL или `+380…` — нормализация не может быть забыта."""

    def test_raw_format_does_not_reach_the_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Client.objects.create(phone="0501234567")

    def test_empty_string_is_not_a_phone(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Client.objects.create(phone="")

    def test_null_and_normalized_are_fine(self):
        Client.objects.create(phone=None)
        Client.objects.create(phone="+380501234567")
