import random

from django.core.management.base import BaseCommand

from core.models import Client


class Command(BaseCommand):
    help = "Создать несколько тестовых пользователей Client с паролем admin."

    def handle(self, *args, **options):
        count = 100
        created = 0
        for i in range(count):
            email = f"test_client_{i}@example.com"
            defaults = {
                "id_remonline": random.randint(100000, 999999),
                "telegram_id": random.randint(10000000, 99999999),
                "name": f"Имя_{i}",
                "last_name": f"Фамилия_{i}",
                "email": email,
                "phone": f"+7000000{i:03d}",
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            }
            if not Client.objects.filter(email=email).exists():
                Client.objects.create_user(email=email, password="admin", **defaults)
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Создано пользователей: {created}"))
