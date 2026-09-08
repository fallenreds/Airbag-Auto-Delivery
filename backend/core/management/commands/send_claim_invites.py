"""
Рассылка персональных приглашений клиентам старой системы.

Команда, а не функция бота: у бота нет эндпоинта для отправки произвольных
сообщений, а токен есть и у бэкенда. Плюс рассылка одноразовая и её удобно
прогонять из shell на сервере, глядя в отчёт.

    python manage.py send_claim_invites            # превью
    python manage.py send_claim_invites --apply    # отправка

Идемпотентна: у кого уже проставлен `sent_at`, тому повторно не уходит, а код
переиспользуется. Прогонять **после** переноса токена @AirBagAD_bot — иначе
сообщения просто не дойдут: до первого /start бот не имеет права писать
человеку, а у нового бота этого /start ни у кого не было.
"""
import time
from collections import Counter

import requests
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.services.account_claim import (
    build_claim_url,
    claimable_clients,
    issue_code,
)
from core.services.telegram import _get_bot_token

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Telegram отбивает примерно на 30 сообщениях в секунду. Держимся ниже: 173
# сообщения при такой паузе уходят за девять секунд, спешить некуда.
SEND_INTERVAL_SECONDS = 0.05

MESSAGE = (
    "<b>Магазин переїхав на нову систему 🚚</b>\n\n"
    "Тепер, окрім бота, у нас є повноцінний сайт з каталогом, кошиком і "
    "особистим кабінетом.\n\n"
    "Щоб <b>не втратити історію замовлень і накопичену знижку</b>, "
    "створіть вхід на сайт за своїм персональним посиланням:\n"
    "{url}\n\n"
    "Посилання лише для вас — не передавайте його нікому."
)


class Command(BaseCommand):
    help = "Разослать клиентам старой системы персональные ссылки на забор аккаунта"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="действительно отправлять сообщения"
        )
        parser.add_argument(
            "--limit", type=int, help="взять только N получателей (пробный прогон)"
        )
        parser.add_argument(
            "--locale", default="uk", help="локаль ссылки на сайт (uk, ru, en)"
        )
        parser.add_argument(
            "--resend",
            action="store_true",
            help="отправить и тем, кому уже отправляли",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        recipients = list(claimable_clients())
        if options["limit"]:
            recipients = recipients[: options["limit"]]

        if not recipients:
            self.stdout.write("Некому отправлять: все аккаунты уже с подтверждённой почтой.")
            return

        token = _get_bot_token() if apply else None
        stats = Counter()

        for client in recipients:
            claim_code = issue_code(client)
            if claim_code.sent_at and not options["resend"]:
                stats["уже отправляли"] += 1
                continue

            url = build_claim_url(claim_code, options["locale"])
            if not apply:
                stats["будет отправлено"] += 1
                continue

            # У аккаунта может быть несколько Telegram — ссылка уходит в каждый,
            # достаточно одного доставленного.
            outcomes = [
                self._send(token, telegram_id, MESSAGE.format(url=url))
                for telegram_id in client.telegram_ids
            ]
            outcome = "отправлено" if "отправлено" in outcomes else (outcomes[0] if outcomes else "нет Telegram")
            stats[outcome] += 1
            if outcome == "отправлено":
                claim_code.sent_at = timezone.now()
                claim_code.save(update_fields=["sent_at"])
            time.sleep(SEND_INTERVAL_SECONDS)

        self._report(stats, len(recipients), apply)

    def _send(self, token, telegram_id, text):
        try:
            response = requests.post(
                TELEGRAM_API.format(token=token),
                json={
                    "chat_id": telegram_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
        except requests.RequestException as exc:
            self.stderr.write(f"  {telegram_id}: сеть — {exc}")
            return "ошибка сети"

        if response.status_code == 200:
            return "отправлено"

        description = ""
        try:
            description = response.json().get("description", "")
        except ValueError:
            description = response.text[:120]

        # Человек не начинал диалог или заблокировал бота. Это не сбой рассылки
        # и не повод повторять — до него просто нечем достучаться.
        if response.status_code == 403:
            return "бот заблокирован или диалог не начат"
        self.stderr.write(f"  {telegram_id}: {response.status_code} {description}")
        return f"отказ Telegram ({response.status_code})"

    def _report(self, stats, total, apply):
        self.stdout.write(self.style.MIGRATE_HEADING("\nРассылка приглашений"))
        self.stdout.write(f"  получателей: {total}")
        for key, count in stats.most_common():
            self.stdout.write(f"  {key:<40}{count:>6}")
        self.stdout.write("")
        if apply:
            self.stdout.write(self.style.SUCCESS("Отправлено."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Это превью — ничего не отправлено. Повторите с --apply "
                    "(и только после переноса токена @AirBagAD_bot)."
                )
            )
