# Telegram Integration — Документация изменений

## Оглавление
1. [Обзор](#обзор)
2. [Архитектура](#архитектура)
3. [Backend — новые файлы](#backend--новые-файлы)
4. [Backend — изменённые файлы](#backend--изменённые-файлы)
5. [Bot — изменённые файлы](#bot--изменённые-файлы)
6. [Frontend — изменённые файлы](#frontend--изменённые-файлы)
7. [Флоу авторизации](#флоу-авторизации)
8. [Переменные окружения](#переменные-окружения)
9. [Защитные механизмы](#защитные-механизмы)

---

## Обзор

Реализована полная интеграция Telegram с сайтом, охватывающая четыре сценария:

| # | Сценарий | Как работает |
|---|----------|-------------|
| 1 | **Авто-авторизация через WebApp** | Пользователь открывает сайт в Telegram WebApp → сайт получает `initData` → бэкенд валидирует подпись → пользователь логинится автоматически |
| 2 | **Ручная привязка Telegram** | Пользователь нажимает кнопку на странице профиля → получает ссылку `t.me/bot?start=link_...` → в боте ссылка активируется → Telegram привязывается к аккаунту |
| 3 | **Смена привязанного аккаунта** | Те же инструменты что и привязка. Старый `telegram_id` заменяется новым. Также автоматически при открытии профиля через другой WebApp |
| 4 | **Авто-привязка при входе по паролю** | Пользователь в Telegram WebApp вводит email/пароль → после успешного входа, если у аккаунта ещё нет Telegram → автоматически привязывается |

---

## Архитектура

```
Telegram WebApp                    Сайт (Next.js)                    Бэкенд (Django)
─────────────────    ──────────────────────────────    ─────────────────────────────────
initData (HMAC)  →   useAuthCheck                  →   POST /api/v2/telegram/auth
                     useTelegramWebApp                  (валидация подписи, авто-логин)

                     profile page                   →   GET  /api/v2/telegram/link
                     (кнопка "Привязать")               (генерация одноразового кода)

Telegram Bot         ─────────────────────────────  →   POST /api/v2/telegram/link/consume/
(/start link_CODE)                                       (активация кода, сохранение telegram_id)

                     login-area.jsx                 →   POST /api/v2/telegram/auto-link
                     (после входа по паролю)             (привязка initData к залогиненному юзеру)
```

---

## Backend — новые файлы

### `backend/core/services/telegram.py`

**Назначение:** Бизнес-логика Telegram — валидация подписи, генерация кодов привязки.

#### `validate_telegram_init_data(init_data, max_age_seconds=None)`
Валидирует строку `initData` от Telegram WebApp по алгоритму HMAC-SHA256:
1. Парсит URL-encoded строку в словарь
2. Извлекает поле `hash`
3. Вычисляет `secret_key = HMAC-SHA256("WebAppData", bot_token)`
4. Вычисляет `HMAC-SHA256(secret_key, data_check_string)` и сравнивает с полученным `hash`
5. Проверяет свежесть: `auth_date` не старше `TELEGRAM_AUTH_MAX_AGE_SECONDS` (по умолчанию 24 часа)
6. Возвращает распарсенный словарь с `telegram_user`

#### `generate_telegram_link_code_for_user(user_id, ttl_seconds=None)`
Генерирует одноразовый код для привязки через бота:
- Создаёт `secrets.token_urlsafe(18)` — криптографически безопасный код
- Сохраняет `{telegram_link:<code>: user_id}` в Redis с TTL 10 минут
- Возвращает `{code, expires_in}`

#### `build_telegram_bot_link(code)`
Строит ссылку `https://t.me/<BOT_USERNAME>?start=link_<code>`.
Обрезает `@` из `TELEGRAM_BOT_USERNAME` если он задан с ним.

---

### `backend/core/serializers/telegram.py`

**Назначение:** DRF-сериализаторы для всех Telegram endpoints.

#### `TelegramInitDataSerializer`
Базовый сериализатор. Принимает поле `init_data`, валидирует через `validate_telegram_init_data()`, кладёт результат в `validated_data["telegram_payload"]`.

#### `TelegramAuthSerializer`
Для эндпоинта `POST /telegram/auth`. Метод `get_or_create_client()`:
- Ищет существующего клиента по `telegram_id`
- Если нашёл — синхронизирует `name`/`last_name` из Telegram и возвращает
- Если не нашёл — создаёт гостевого клиента (`is_guest=True`) с `telegram_id`
- **Защита от UNIQUE constraint:** если Telegram `username` уже занят как `login` у другого клиента — создаёт гостя с `login=None` (через `except IntegrityError`)

#### `TelegramAutoLinkSerializer`
Для эндпоинта `POST /telegram/auto-link`. Привязывает текущего залогиненного пользователя.

`validate()`:
- Требует аутентификацию
- Блокирует привязку если `telegram_id` уже занят у **другого реального** (не гостевого) пользователя
- Гостевые аккаунты с тем же `telegram_id` не считаются конфликтом (они временные, создаются авто-авторизацией)

`save()`:
- Перед сохранением отвязывает `telegram_id` от любых **гостевых** аккаунтов (WebApp автоматически создаёт гостей, их надо заменить реальным аккаунтом)
- Устанавливает `user.telegram_id = tg_user["id"]` (перезаписывает предыдущее значение — поддержка смены аккаунта)
- Копирует `username`/`first_name`/`last_name` из Telegram в профиль если поля пустые

---

### `backend/core/views/telegram.py`

**Назначение:** API views для четырёх Telegram endpoints.

#### `TelegramAuthView` — `POST /api/v2/telegram/auth`
- `AllowAny` — без аутентификации (вход через Telegram)
- Валидирует `initData`, создаёт/находит клиента, выдаёт JWT токены
- Гостям выдаёт `GuestRefreshToken`, реальным — обычный `RefreshToken`

#### `TelegramLinkView` — `GET /api/v2/telegram/link`
- `IsAuthenticated` — только залогиненные
- Генерирует одноразовый код через `generate_telegram_link_code_for_user()`
- Возвращает ссылку на бота: `{code, expires_in, link, url}`

#### `TelegramAutoLinkView` — `POST /api/v2/telegram/auto-link`
- `IsAuthenticated` — только залогиненные
- Делегирует валидацию и сохранение в `TelegramAutoLinkSerializer`
- Возвращает обновлённый профиль пользователя

#### `TelegramLinkConsumeView` — `POST /api/v2/telegram/link/consume/`
- Вызывается **Telegram ботом** (аутентификация по `X-Api-Key`)
- Принимает `code` (бот передаёт `link_<code>`, префикс обрезается через `.removeprefix()`)
- Ищет `user_id` в Redis по коду
- Отвязывает `telegram_id` от любых других аккаунтов перед сохранением
- Копирует профильные поля из Telegram если пустые
- **Защита от UNIQUE на `login`:** `try/except IntegrityError` — если `username` занят, сохраняет без `login`

---

## Backend — изменённые файлы

### `backend/config/settings.py`
Добавлена конфигурация Redis-кэша (используется для хранения одноразовых кодов привязки):

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://redis:6379/2"),
    }
}
```

Использует Redis DB №2 — отдельно от Celery (DB 0 и 1).

### `backend/core/urls.py`
Добавлены четыре новых маршрута под префиксом `api/v2/`:

```
POST   telegram/auth              — авто-авторизация через WebApp
GET    telegram/link              — получение ссылки для привязки через бота
POST   telegram/link/consume/     — активация кода ботом
POST   telegram/auto-link         — привязка initData к залогиненному юзеру
```

### `backend/core/views/bot_visitors.py`
Переопределён метод `create()` — используется `get_or_create` вместо стандартного `create`:
- **Проблема:** бот повторно вызывал `POST /api/v2/bot-visitors/` при каждом старте → 400 Bad Request из-за `unique=True` на `telegram_id`
- **Решение:** `BotVisitor.objects.get_or_create(telegram_id=telegram_id)` — возвращает 201 для нового, 200 для существующего

### `backend/core/serializers/__init__.py` и `backend/core/views/__init__.py`
Добавлены импорты новых классов для доступа через `from core.serializers import ...` и `from core.views import ...`.

---

## Bot — изменённые файлы

### `bot/config.py`
Добавлен алиас `BACKEND_API_BASE` для переменной `BASE_URL`. Решает проблему именования переменной окружения на разных серверах.

### `bot/api.py`
Добавлена функция `link_account_via_code(code, telegram_id, telegram_user)`:
- Отправляет `POST /api/v2/telegram/link/consume/` с кодом из команды `/start`
- Передаёт профильные данные Telegram пользователя (`username`, `first_name`, `last_name`)
- Возвращает `(success: bool, message: str)` — сообщение для отправки пользователю в боте
- Обрабатывает ошибки сети и некорректный JSON через `content_type=None`

**Исправление URL:** был `api/telegram/link/consume/` → стало `api/v2/telegram/link/consume/` (все Core URLs монтируются под префиксом `api/v2/`).

### `bot/main.py`
Изменён обработчик команды `/start`:

**Было:** просто добавлял visitor и показывал приветствие.

**Стало:**
1. Извлекает `payload` из аргументов команды (`message.get_args()`)
2. Если `payload` не пустой — вызывает `link_account_via_code(payload, telegram_id, telegram_user)`
3. Отправляет пользователю результат привязки (успех или ошибку)
4. Если привязка не произошла (обычный `/start`) — регистрирует visitor

---

## Frontend — изменённые файлы

### `src/hooks/use-auth-check.js`

**Назначение:** Проверяет аутентификацию при загрузке любой страницы.

**Что изменено:** Раньше при наличии **любого** токена в localStorage сразу устанавливал `authChecked=true` и выходил. Это означало, что гостевая Telegram-сессия блокировала попытку найти реальный аккаунт по `telegram_id`.

**Теперь:**
- Если токен **реального пользователя** (`isGuest=false`) → восстанавливает сессию и завершает
- Если токен **гостевой** (`isGuest=true`) → восстанавливает гостевую сессию, но продолжает выполнять Telegram-проверку
- Telegram-проверка: если `hasInitData=true` → вызывает `telegramAuth`, который может вернуть реальный аккаунт (если Telegram уже привязан) и апгрейднуть сессию

**Зачем:** Без этого пользователь с привязанным Telegram, у которого в localStorage лежит старый гостевой токен, никогда не был бы автоматически залогинен под своим реальным аккаунтом.

---

### `src/redux/features/auth/authApi.js`

#### Мутация `login`
В `onQueryStarted` при успешном входе добавлены явные `isGuest: false, guestId: null` в:
- `setAuth({...})` — localStorage
- `dispatch(userLoggedIn({...}))` — Redux
- `Cookies.set('userInfo', ...)` — cookie

**Проблема которую решает:** `setAuth` делает MERGE с существующими данными. Если в localStorage была гостевая сессия (`isGuest: true`), флаг не перезаписывался → `LoginArea` видела `isGuest=true` и не редиректила после входа.

#### Query `getUser`
Исправлен расчёт `mergedIsGuest`:

**Было:** `mergedUser?.is_guest ?? existing?.isGuest ?? false`
— наследовал `isGuest: true` от предыдущей гостевой сессии если API не вернул поле `is_guest`.

**Стало:** `mergedUser?.is_guest === true`
— только явный `is_guest: true` из API считается гостем. Реальный пользователь без поля `is_guest` получает `false`.

#### Мутации `telegramAutoLink` и `telegramAuth`
Добавлены в экспорты: `useLazyTelegramLinkQuery`, `useTelegramAutoLinkMutation`, `useTelegramAuthMutation`.

---

### `src/components/forms/login-form.jsx`

**Что убрано:** Прямой вызов `telegramAutoLink` сразу после входа.

**Почему убрали:** Вызов происходил без проверки `user.telegram_id` — приводил к тому, что если Telegram был привязан к другому гостевому аккаунту, этот аккаунт терял привязку. Также вызывался для аккаунтов у которых Telegram уже был привязан.

**Логика перенесена в:** `login-area.jsx` (с безопасными проверками).

---

### `src/components/login-register/login-area.jsx`

Добавлены два `useEffect`:

#### 1. Безопасный авто-линк после входа
```
Условия для вызова telegramAutoLink:
  ✓ пользователь залогинен (accessToken есть, isGuest=false)
  ✓ профиль загружен (user !== null)
  ✓ у пользователя нет telegram_id (user.telegram_id falsy)
  ✓ есть initData из Telegram WebApp (hasInitData=true)
  ✓ не вызывали раньше (ref-флаг)
```

**Зачем:** Привязка происходит только если точно известно что у текущего пользователя Telegram не привязан. Предотвращает нежелательную перепривязку.

#### 2. Редирект после входа
Редиректит на главную (или сохранённый URL) когда `accessToken` появляется и `isGuest=false`. Гостей не редиректит — они остаются на странице логина.

---

### `src/components/profile/user-profile-area.jsx`

#### Авто-привязка при открытии профиля через Telegram WebApp
Новый `useEffect` при загрузке профиля:
```
Если:
  - открыто в Telegram WebApp (hasInitData=true)
  - профиль загружен
  - telegram_id из WebApp ОТЛИЧАЕТСЯ от telegram_id в профиле (или профиль не привязан)
→ автоматически вызывает telegramAutoLink
→ показывает тост "Telegram привязан" или "Telegram заменён"
```

**Зачем:** Реализует требование «пользователь может автоматически привязать/сменить Telegram, просто зайдя в профиль через WebApp».

#### UI кнопки — разделение статуса и действия
**Было:** Одна кнопка, менялся цвет и текст.

**Стало:**
- Когда **не привязан** → кнопка `btn-outline-primary` "Привязать Telegram"
- Когда **привязан** → 
  - Статусный бейдж `btn-success` "Telegram привязан" (не кликабельный, `pointer-events: none`)
  - Отдельная кнопка `btn-outline-secondary` "Сменить аккаунт"

---

### `src/hooks/use-order-checkout.js`

После создания гостевого аккаунта при оформлении заказа добавлен вызов `telegramAutoLink` если открыто в Telegram WebApp. Это связывает гостевой аккаунт с Telegram без дополнительных действий пользователя.

---

### `src/data/menu-data.js`

В `account_pages` (мобильное меню) добавлена ссылка на профиль:
```js
{ titleKey: 'menu.myProfile', link: '/profile', showForAuth: true }
```
**Проблема:** Ссылка на профиль отсутствовала в мобильном меню — авторизованные пользователи не могли перейти в профиль через бургер-меню.

---

### `messages/ru.json`, `messages/en.json`, `messages/uk.json`

Добавлены переводы:

| Ключ | ru | en | uk |
|------|----|----|-----|
| `menu.myProfile` | Мой профиль | My Profile | Мій профіль |
| `ProfileExtra.telegramChangeCTA` | Сменить аккаунт | Change account | Змінити акаунт |
| `ProfileExtra.telegramChangedSuccess` | Telegram-аккаунт успешно заменён | Telegram account changed successfully | Telegram-акаунт успішно замінено |

---

## Флоу авторизации

### Флоу 1: Первое открытие сайта через Telegram WebApp (новый пользователь)
```
Telegram WebApp → сайт загружается
useAuthCheck:
  localStorage пуст → requiresTelegramCheck=true
  hasInitData=true → telegramAuth(initData)
Backend:
  validate_telegram_init_data → OK
  Client.filter(telegram_id=X) → не найден
  Client.objects.create_guest(telegram_id=X, is_guest=True)
  выдаёт GuestRefreshToken
Frontend:
  dispatch(userLoggedIn({isGuest: true}))
  пользователь залогинен как гость
```

### Флоу 2: Открытие сайта (Telegram уже привязан к реальному аккаунту)
```
Telegram WebApp → useAuthCheck
  localStorage: гостевой токен → dispatch (guest), requiresTelegramCheck=true
  hasInitData=true → telegramAuth(initData)
Backend:
  Client.filter(telegram_id=X) → нашёл реального пользователя
  выдаёт обычный RefreshToken
Frontend:
  dispatch(userLoggedIn({isGuest: false}))
  гостевая сессия заменена реальной
```

### Флоу 3: Вход по email/паролю в Telegram WebApp
```
Пользователь заполняет форму → login mutation
Backend: выдаёт токен с isGuest=false
authApi.onQueryStarted:
  setAuth({isGuest: false, guestId: null}) — явно очищает гостевой флаг
  dispatch(userLoggedIn({isGuest: false}))

login-area.jsx useEffect:
  accessToken изменился, isGuest=false
  user загружен, user.telegram_id=null
  hasInitData=true
  → telegramAutoLink(initData)
Backend:
  проверяет: есть ли реальный (не гостевой) конфликт? → нет
  отвязывает гостя с этим telegram_id
  сохраняет telegram_id на реальном аккаунте
```

### Флоу 4: Ручная привязка через бота (обычный браузер)
```
Профиль → кнопка "Привязать Telegram"
  window.open('', '_blank')  ← ДО await (иначе браузер блокирует popup)
  GET /api/v2/telegram/link
  → {code: "abc123", link: "https://t.me/bot?start=link_abc123"}
  win.location.href = link

Пользователь в Telegram нажимает кнопку Start
Bot: /start link_abc123
  api.link_account_via_code("link_abc123", telegram_id, user)
  POST /api/v2/telegram/link/consume/ {code: "link_abc123", telegram_id: X}
Backend TelegramLinkConsumeView:
  code.removeprefix("link_") → "abc123"
  cache.get("telegram_link:abc123") → user_id
  Client.objects.exclude(id=user_id).filter(telegram_id=X).update(telegram_id=None)
  user.telegram_id = X
  user.save()
  cache.delete(key)
  → 200 "✅ Аккаунти успішно пов'язані!"
Bot: отправляет сообщение об успехе
```

---

## Переменные окружения

### Backend (`backend/.env`)
| Переменная | Описание | Пример |
|------------|----------|--------|
| `TELEGRAM_BOT_TOKEN` | Токен бота (для валидации HMAC) | `123456:ABCdef...` |
| `TELEGRAM_BOT_USERNAME` | Username бота без `@` | `airbagshop_bot` |
| `TELEGRAM_AUTH_MAX_AGE_SECONDS` | Максимальный возраст initData (по умолчанию 86400) | `86400` |
| `REDIS_URL` | URL Redis для кэша кодов (по умолчанию `redis://redis:6379/2`) | `redis://redis:6379/2` |

### Bot (`bot/.env`)
| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен бота |
| `BASE_URL` или `BACKEND_API_BASE` | URL бэкенда с `/` в конце |
| `BACKEND_API_KEY` | API ключ для запросов к бэкенду |

---

## Защитные механизмы

### HMAC валидация (бэкенд)
Каждый `initData` проверяется криптографически:
```python
secret_key = HMAC-SHA256("WebAppData", bot_token)
expected = HMAC-SHA256(secret_key, data_check_string)
assert expected == received_hash
```
Подделать `initData` без знания `bot_token` невозможно.

### Защита от перепривязки (бэкенд)
`TelegramAutoLinkSerializer.validate()` блокирует привязку если `telegram_id` уже принадлежит другому **реальному** пользователю. Гостевые аккаунты не защищены — они автоматически создаются WebApp и считаются временными.

### Нельзя угнать Telegram другого реального пользователя
Даже если злоумышленник залогинится под другим аккаунтом в том же Telegram WebApp, привязка будет заблокирована с ошибкой "This Telegram account is already linked" — потому что проверяется `is_guest=False` конфликт.

### Безопасный авто-линк после входа (фронтенд)
`login-area.jsx` вызывает `telegramAutoLink` только если одновременно:
1. Пользователь — реальный (не гость)
2. Профиль загружен (`user !== null`)
3. `user.telegram_id` пустой (нет уже привязанного Telegram)
4. Есть `initData` из WebApp

### Уникальность login при создании гостя
Если Telegram `username` уже занят как `login` другого клиента → `IntegrityError` → гость создаётся с `login=None`. Аналогичная защита при consume-коде бота.

### Авто-линк только один раз (фронтенд)
Ref-флаги (`autoLinkRef`, `autoLinkAttempted`) предотвращают дублирование вызовов `telegramAutoLink` при перерендерах компонентов.
