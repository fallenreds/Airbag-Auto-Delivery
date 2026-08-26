# Переключение на новую систему: runbook

Хосты: `airbag` (новая, 178.79.149.193), `airbag_old` (старая, 139.162.205.246).
Рабочий каталог на обоих — `/root/Airbag-Auto-Delivery`.
Боевая база старой системы — `/root/Airbag-Auto-Delivery/info.db`.

Три фазы. Фаза A обратима и не требует простоя. Простой начинается в фазе B.

---

## Фаза A — выкатить код (простоя нет)

### A1. Обновить репозиторий

```sh
ssh airbag
cd /root/Airbag-Auto-Delivery
git pull origin v2
git submodule update --init --recursive
git log --oneline -1          # ждём b1ab793 или новее
```

### A2. Выключить DEBUG

```sh
sed -i 's/^DJANGO_DEBUG=True$/DJANGO_DEBUG=False/' backend/.env
grep '^DJANGO_DEBUG=' backend/.env
```

Домены `airbagad.com` и `www.airbagad.com` теперь всегда в `CORS_ALLOWED_ORIGINS`,
поэтому выключение DEBUG фронт не ломает.

### A3. Пересобрать и поднять

```sh
docker compose up -d --build
```

Пересборка обязательна для всех сервисов: `entrypoint.sh` backend лежит в образе
(вне маунта `/app`), код бота — тоже в образе, фронтенд собирается на этапе build.
Миграции (`0013_accountclaimcode`) накатятся сами из entrypoint.

### A4. Проверить

```sh
docker compose ps                                   # все up
docker compose logs backend --tail 20 | grep entrypoint
curl -s -o /dev/null -w '%{http_code}\n' https://airbagad.com/uk/           # 200
curl -s -o /dev/null -w '%{http_code}\n' https://api.airbagad.com/api/v2/goods/   # 200
curl -s https://api.airbagad.com/api/v2/no-such/ | grep -c 'DEBUG = True'   # 0
curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://178.79.149.193:8000/admin/login/  # 000
```

Последние две строки — то, ради чего фаза A: наружу больше не уходят ни
трейсбеки, ни форма входа в админку по открытому HTTP.

**Откат фазы A:** `git checkout 4a2ea82 && docker compose up -d --build`,
`DJANGO_DEBUG=True` вернуть.

---

## Фаза B — переключение (простой ~15 минут)

### B1. Резервная копия новой системы

```sh
ssh airbag 'cd /root/Airbag-Auto-Delivery && scripts/backup.sh'
```

### B2. Остановить старую систему

Обязательно до переноса токена: два процесса на одном токене дают
`TerminatedByOtherGetUpdates`.

```sh
ssh airbag_old 'cd /root/Airbag-Auto-Delivery && docker compose down'
ssh airbag_old 'docker compose ps'      # пусто
```

### B3. Снять свежий дамп старой базы

Снимать **после** остановки: дамп обязан быть финальным, иначе часть заказов
приедет в устаревшем состоянии.

```sh
ssh airbag_old 'sqlite3 /root/Airbag-Auto-Delivery/info.db ".backup /tmp/legacy.db"'
scp airbag_old:/tmp/legacy.db /tmp/legacy.db
scp /tmp/legacy.db airbag:/root/legacy.db
ssh airbag_old 'rm -f /tmp/legacy.db'
```

### B4. Перенести токен

Взять `BOT_TOKEN` из `airbag_old:/root/Airbag-Auto-Delivery/bot/.env` и записать
на `airbag` в **два** файла:

```sh
# airbag:/root/Airbag-Auto-Delivery/bot/.env
BOT_TOKEN=<токен @AirBagAD_bot>

# airbag:/root/Airbag-Auto-Delivery/backend/.env
TELEGRAM_BOT_TOKEN=<тот же токен>
TELEGRAM_BOT_USERNAME=@AirBagAD_bot
```

Расхождение между этими двумя переменными ломает HMAC подписи `initData` —
вход через Mini App отваливается у всех.

### B5. Импорт

```sh
ssh airbag
cd /root/Airbag-Auto-Delivery

# превью: считается настоящей записью в транзакции с откатом
docker compose exec -T backend python manage.py import_legacy_db /root/legacy.db

# запись
docker compose exec -T backend python manage.py import_legacy_db /root/legacy.db --apply
```

В отчёте проверить:

- `clients … создать ~171`
- `orders … создать ~3940`, пропущено 6 — «бонусное начисление, а не заказ»
- `закрыто по данным RemOnline` — на свежем дампе должно быть **0**;
  ненулевое значение означает, что дамп успел устареть

### B6. Перезапустить бота с новым токеном

```sh
docker compose up -d --build bot
docker compose logs bot --tail 20        # поллинг, без TerminatedByOtherGetUpdates
```

### B7. Проверить вручную, с НЕ админского аккаунта

В чате `@AirBagAD_bot`:

1. `/start` — приходит меню.
2. «Статус замовлень 📦» — у клиента с активным заказом показывает карточку,
   у остальных «У вас немає замовлень». **Если «У вас немає замовлень» у всех —
   не выкачен фикс скоупа списков, откатывать импорт.**
3. «Знижки 💎» — показывает процент и сумму за месяц.
4. Нажать любую старую кнопку под сообщением трёхлетней давности — должно
   прийти «Ця кнопка застаріла», а не тишина и не действие по чужому заказу.

Со стороны сервера:

```sh
docker compose exec -T backend python manage.py shell -c "
from core.models import Client, Order, OrderEvent
print('клиентов:', Client.objects.count())
print('заказов:', Order.objects.count())
print('очередь событий:', OrderEvent.objects.count())"
```

Очередь событий должна быть близка к нулю. Сотни событий означают, что дамп был
устаревшим — см. B5.

**Откат фазы B:** вернуть базу из копии `scripts/backup.sh`, вернуть
`BOT_TOKEN` старому боту, поднять `airbag_old`.

---

## Фаза C — после переключения

### C1. Рассылка персональных ссылок

Только после B6: до первого `/start` Telegram запрещает боту писать человеку.

```sh
docker compose exec -T backend python manage.py send_claim_invites            # превью
docker compose exec -T backend python manage.py send_claim_invites --apply
```

Ожидаемо ~170 получателей, по одному сообщению. Идемпотентна: повторный запуск
не шлёт дважды. `403` (бот заблокирован или диалог не начат) — отдельная строка
отчёта, не ошибка.

### C2. Перенести бонусные начисления

Шесть штук, суммы — в отчёте импорта строкой «бонусных начислений».

```sh
curl -X POST https://api.airbagad.com/api/v2/clients/<id>/add-bonus/ \
  -H 'X-Api-Key: <ключ staff-аккаунта>' \
  -H 'Content-Type: application/json' -d '{"count": 10000}'
```

### C3. Закрыть висяки

Три заказа июня–июля без ТТН и без номера в RemOnline. В обработчик они не
попадают (тот требует `remonline_order_id`), уведомлений не породят, но и сами
не закроются.

### C4. Поставить бэкап в cron

```sh
crontab -e
0 4 * * * /root/Airbag-Auto-Delivery/scripts/backup.sh >> /var/log/airbag-backup.log 2>&1
```

### C5. Отключить старый хост

Не раньше чем через несколько дней: `airbag_old` — это откат. Когда решите
гасить — снять финальную копию `info.db` в архив.

---

## Что осталось техдолгом

- База и `media/` лежат в рабочей копии репозитория, а не в docker-volume, и оба
  пути в `.gitignore`: `git clean -xdf` на сервере уничтожит данные. Бэкап
  смягчает, переезд в volume требует простоя.
- `MONOBANK_TOKEN_TEST` / `_PROD` не разведены, работает общий `MONOBANK_TOKEN`.
- gunicorn запущен с одним воркером, поэтому APScheduler не задваивается. При
  добавлении воркеров фоновые задачи пойдут параллельно по общей SQLite.
