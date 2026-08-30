# Вывод старой системы из эксплуатации: runbook

**Сайт никуда не переезжает.** `airbagad.com` уже боевой и работает: это та самая
новая система. Происходит другое — старый сервер выключается, а его данные и его
Telegram-бот переезжают в уже работающую систему.

Поэтому здесь нет «переключения сайта» и нет окна, в котором магазин недоступен.
Есть три вещи:

1. выкатить на работающий сайт исправления, без которых импорт ломает бота;
2. выключить старый сервер, забрать его базу и его токен;
3. позвать людей.

| | |
|---|---|
| Новая система (остаётся) | `airbag` — 178.79.149.193, `/root/Airbag-Auto-Delivery` |
| Старая система (выключается) | `airbag_old` — 139.162.205.246, база `/root/Airbag-Auto-Delivery/info.db` |
| Бот, который переезжает | `@AirBagAD_bot` |
| Бот, под которым сейчас работает новая система | `@airbag_preprod_bot` — после переезда не нужен |

Что чем прерывается:

| Фаза | Сайт | Бот |
|---|---|---|
| A — деплой | 1–2 мин на пересборку контейнеров | не затронут |
| B — вывод старой системы | **не затронут** | не отвечает, пока идёт импорт (~5 мин) |
| C — после | не затронут | не затронут |

---

## Фаза A — выкатить исправления на работающий сайт

Делается заранее, отдельно от всего остального. Обычный деплой: сайт недоступен
только на время пересборки контейнеров. Лучше в тихий час.

### A1. Обновить репозиторий

```sh
ssh airbag
cd /root/Airbag-Auto-Delivery
git pull origin v2
git submodule update --init --recursive
git log --oneline -1
```

### A2. Выключить DEBUG

```sh
sed -i 's/^DJANGO_DEBUG=True$/DJANGO_DEBUG=False/' backend/.env
```

Домены `airbagad.com` и `www.airbagad.com` теперь всегда в `CORS_ALLOWED_ORIGINS`,
поэтому фронт от этого не ломается.

### A3. Прописать токен `@AirBagAD_bot` в backend/.env — уже сейчас

Это можно и нужно сделать **до** выключения старой системы. Бэкенд Telegram не
опрашивает: токен нужен ему только для проверки подписи `initData` из Mini App и
для разовой рассылки. Конфликта `getUpdates` со всё ещё живым старым ботом не
возникает — конфликт бывает только между двумя опрашивающими процессами.

Токен взять из `airbag_old:/root/Airbag-Auto-Delivery/bot/.env`:

```sh
# airbag:/root/Airbag-Auto-Delivery/backend/.env
TELEGRAM_BOT_TOKEN=<токен @AirBagAD_bot>
TELEGRAM_BOT_USERNAME=@AirBagAD_bot
```

Ради чего: в фазе B тогда останется перезапустить только контейнер бота, а
бэкенд и сайт вообще не тронуты.

Цена: вход в Mini App из `@airbag_preprod_bot` перестанет работать сразу. Сейчас
в новой базе `telegram_id` есть у двух аккаунтов, оба администраторские, — то
есть задеть некого.

### A4. Пересобрать и поднять

```sh
docker compose up -d --build
```

Пересборка обязательна: `entrypoint.sh` бэкенда лежит в образе вне маунта `/app`,
код бота — тоже в образе, фронтенд собирается на этапе build. Миграция
`0013_accountclaimcode` накатится сама из entrypoint.

### A5. Проверить

```sh
docker compose ps
docker compose logs backend --tail 20 | grep entrypoint
curl -s -o /dev/null -w '%{http_code}\n' https://airbagad.com/uk/                  # 200
curl -s -o /dev/null -w '%{http_code}\n' https://api.airbagad.com/api/v2/goods/    # 200
curl -s https://api.airbagad.com/api/v2/no-such/ | grep -c 'DEBUG = True'          # 0
curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 \
     http://178.79.149.193:8000/admin/login/                                       # 000
```

Последние две строки — то, ради чего фаза A нужна и сама по себе: наружу больше
не уходят ни трейсбеки, ни форма входа в админку по открытому HTTP.

**Откат:** `git checkout 49e2e77~1 && docker compose up -d --build`, вернуть
`DJANGO_DEBUG=True` и прежний `TELEGRAM_BOT_TOKEN`.

---

## Фаза B — выключить старую систему и забрать её данные

Сайт в этой фазе не трогается вообще. Не отвечает только бот — от момента
остановки старого до запуска нового под тем же токеном.

### B1. Бэкап

```sh
ssh airbag 'cd /root/Airbag-Auto-Delivery && scripts/backup.sh'
```

### B2. Выключить старую систему

```sh
ssh airbag_old 'cd /root/Airbag-Auto-Delivery && docker compose down && docker compose ps'
```

С этой секунды бот молчит. Всё, что люди напишут до запуска нового,
отбрасывается: `start_polling(skip_updates=True)` в `bot/main.py`. Поэтому дальше
без пауз.

### B3. Финальный дамп

Снимать **после** остановки — дамп обязан быть последним состоянием.

```sh
ssh airbag_old 'sqlite3 /root/Airbag-Auto-Delivery/info.db ".backup /tmp/legacy.db"'
scp airbag_old:/tmp/legacy.db /tmp/legacy.db
scp /tmp/legacy.db airbag:/root/legacy.db
ssh airbag_old 'rm -f /tmp/legacy.db'
```

### B4. Импорт

```sh
ssh airbag
cd /root/Airbag-Auto-Delivery
docker compose exec -T backend python manage.py import_legacy_db /root/legacy.db
docker compose exec -T backend python manage.py import_legacy_db /root/legacy.db --apply
```

Превью считается настоящей записью внутри транзакции с откатом, поэтому цифры
совпадут с боевым прогоном. В отчёте проверить:

- `clients … создать ~171`
- `orders … создать ~3940`, пропущено 6 — «бонусное начисление, а не заказ»
- `закрыто по данным RemOnline` — **0**. Ненулевое значит, что между B3 и B4
  прошло заметное время и часть заказов успела закрыться. Это не ошибка, сверка
  для того и есть, но лучше не тянуть.

Импорт не мешает уже накопленным данным сайта: номера импортированных заказов
сдвинуты на 100 000 и с диапазоном новой системы не пересекаются.

### B5. Отдать боту старый токен

```sh
# airbag:/root/Airbag-Auto-Delivery/bot/.env
BOT_TOKEN=<токен @AirBagAD_bot>
```

```sh
docker compose up -d --force-recreate bot
docker compose logs bot --tail 20
```

`--force-recreate` — чтобы контейнер гарантированно подхватил новый `.env`.
Пересборка не нужна, образ собран в фазе A. В логах не должно быть
`TerminatedByOtherGetUpdates`: если оно есть — старая система не остановлена.

Бэкенд и фронтенд не перезапускаются: их токен прописан ещё в A3.

### B6. Проверить

В чате `@AirBagAD_bot`, **не с администраторского аккаунта**:

1. `/start` — приходит меню.
2. «Статус замовлень 📦» — у клиента с активным заказом карточка, у остальных
   «У вас немає замовлень». **Если «немає замовлень» у всех — не выкачена фаза A,
   импорт откатывать.**
3. «Знижки 💎» — процент и сумма за месяц.
4. Нажать любую кнопку под сообщением многолетней давности — «Ця кнопка застаріла»,
   а не тишина и не действие по чужому заказу.

Со стороны сервера:

```sh
docker compose exec -T backend python manage.py shell -c "
from core.models import Client, Order, OrderEvent
print('клиентов:', Client.objects.count())
print('заказов:', Order.objects.count())
print('очередь событий:', OrderEvent.objects.count())"
```

Очередь событий должна быть около нуля. Сотни означают, что дамп был не финальным.

**Откат:** восстановить базу из копии `scripts/backup.sh`, вернуть `BOT_TOKEN`
старому боту, поднять `airbag_old`. Сайт откатывать не нужно — он не менялся.

---

## Фаза C — после

### C1. Рассылка персональных ссылок

Только после B5: до первого `/start` Telegram запрещает боту писать человеку, и
с `@airbag_preprod_bot` эти сообщения не дошли бы никому.

```sh
docker compose exec -T backend python manage.py send_claim_invites
docker compose exec -T backend python manage.py send_claim_invites --apply
```

~170 получателей, по одному сообщению. Идемпотентна. `403` (бот заблокирован или
диалог не начат) — строка отчёта, не ошибка.

### C2. Бонусные начисления

Шесть штук, суммы — в отчёте импорта.

```sh
curl -X POST https://api.airbagad.com/api/v2/clients/<id>/add-bonus/ \
  -H 'X-Api-Key: <ключ staff-аккаунта>' \
  -H 'Content-Type: application/json' -d '{"count": 10000}'
```

### C3. Три висяка

Заказы июня–июля без ТТН и без номера в RemOnline. В обработчик не попадают,
уведомлений не породят, но сами не закроются — закрыть руками.

### C4. Бэкап в cron

```sh
0 4 * * * /root/Airbag-Auto-Delivery/scripts/backup.sh >> /var/log/airbag-backup.log 2>&1
```

### C5. Старый сервер

Не гасить окончательно несколько дней: `airbag_old` — это откат. Когда решите
избавляться, снять финальную копию `info.db` в архив.

`@airbag_preprod_bot` после переезда не нужен — можно удалить в BotFather или
оставить под разработку.

---

## Техдолг, который остаётся

- База и `media/` лежат в рабочей копии репозитория, а не в docker-volume, и оба
  пути в `.gitignore`: `git clean -xdf` на сервере уничтожит данные. Бэкап
  смягчает, переезд в volume требует простоя.
- `MONOBANK_TOKEN_TEST` / `_PROD` не разведены, работает общий `MONOBANK_TOKEN`.
- gunicorn запущен с одним воркером, поэтому APScheduler не задваивается. При
  добавлении воркеров фоновые задачи пойдут параллельно по общей SQLite.
