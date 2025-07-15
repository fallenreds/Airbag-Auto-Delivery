from django.core.management.base import BaseCommand
from core.models import Client
import random

class Command(BaseCommand):
    help = 'Создать несколько тестовых пользователей Client с паролем admin.'

    def handle(self, *args, **options):
        count = 100
        created = 0
        for i in range(count):
            login = f'test_client_{i}'
            defaults = {
                'id_remonline': random.randint(100000, 999999),
                'telegram_id': random.randint(10000000, 99999999),
                'name': f'Имя_{i}',
                'last_name': f'Фамилия_{i}',
                'email': f'test_client_{i}@example.com',
                'phone': f'+7000000{i:03d}',
                'is_active': True,
                'is_staff': False,
                'is_superuser': False,
            }
            if not Client.objects.filter(login=login).exists():
                Client.objects.create_user(login=login, password='admin', **defaults)
                created += 1
        self.stdout.write(self.style.SUCCESS(f'Создано пользователей: {created}'))
