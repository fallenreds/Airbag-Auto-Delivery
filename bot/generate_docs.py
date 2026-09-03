"""
Generate bot_functions.docx — полная документация функций Telegram-бота AirbagAD.
Запуск: python generate_docs.py  (из папки bot/)
Результат: ../docs/bot_functions.docx
"""

import os
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# ─── helpers ───────────────────────────────────────────────────────────────────

def set_heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    h.alignment = WD_ALIGN_PARAGRAPH.LEFT
    return h


def add_paragraph(doc, text, bold=False, italic=False):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    return p


def add_table(doc, headers, rows):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.LEFT

    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        for run in hdr_cells[i].paragraphs[0].runs:
            run.bold = True
        # shade header
        tc = hdr_cells[i]._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), "D9E1F2")
        tcPr.append(shd)

    for row_data in rows:
        row_cells = table.add_row().cells
        for i, cell_text in enumerate(row_data):
            row_cells[i].text = str(cell_text)

    return table


def add_spacer(doc):
    doc.add_paragraph("")


# ─── document ──────────────────────────────────────────────────────────────────

def build_document():
    doc = Document()

    # Margins
    section = doc.sections[0]
    section.left_margin = Cm(2)
    section.right_margin = Cm(2)

    # ── Title ──────────────────────────────────────────────────────────────────
    title = doc.add_heading("Документація: Telegram-бот AirbagAD", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_paragraph(doc, "Версія бота: aiogram 2.25.2  |  Дата: 2025", italic=True)
    add_spacer(doc)

    # ══════════════════════════════════════════════════════════════════════════
    # ЧАСТИНА 1 — ДЛЯ КОРИСТУВАЧІВ
    # ══════════════════════════════════════════════════════════════════════════
    set_heading(doc, "ЧАСТИНА 1. Функції для користувачів (клієнтів)", 1)
    add_paragraph(doc,
        "У цьому розділі описані всі дії, доступні звичайному клієнту в Telegram-боті.",
        italic=True)
    add_spacer(doc)

    # ── 1.1 Команди ────────────────────────────────────────────────────────────
    set_heading(doc, "1.1 Команди", 2)
    add_table(doc,
        ["Команда", "Що робить", "Деталі"],
        [
            ["/start",
             "Вхід до бота",
             "Якщо викликати як /start <code>, де <code> — одноразовий код із особистого кабінету, "
             "бот прив'язує Telegram-акаунт до акаунту клієнта на сайті. "
             "Без коду — реєструє нового гостя (bot-visitor) і показує меню."],
            ["/stop",
             "Скасувати поточну дію",
             "Перериває будь-який багатокроковий процес (FSM) і повертає в головне меню."],
        ]
    )
    add_spacer(doc)

    # ── 1.2 Текстове меню ──────────────────────────────────────────────────────
    set_heading(doc, "1.2 Текстові кнопки головного меню", 2)
    add_table(doc,
        ["Кнопка", "Дія", "Хто бачить"],
        [
            ["статус",
             "Показує список активних замовлень клієнта. Для кожного замовлення відображаються: "
             "номер, ім'я, адреса, ТТН (якщо є), тип платежу, сума до сплати, статус оплати.",
             "Тільки авторизований клієнт (прив'язаний акаунт)"],
            ["Зв'язок",
             "Показує контактну інформацію магазину: "
             "телефон менеджера та посилання на профіль Telegram.",
             "Усі користувачі"],
            ["знижки",
             "Відображає поточний розмір персональної знижки клієнта, "
             "скільки витрачено за поточний місяць, "
             "та таблицю порогів знижок (поріг суми → % знижки).",
             "Тільки авторизований клієнт"],
        ]
    )
    add_spacer(doc)

    # ── 1.3 Інлайн-кнопки у картці замовлення ─────────────────────────────────
    set_heading(doc, "1.3 Інлайн-кнопки у картці замовлення", 2)
    add_table(doc,
        ["Кнопка", "Дія"],
        [
            ["Відстежити замовлення 🔍",
             "Перевіряє статус посилки через API Нової Пошти за ТТН замовлення. "
             "Виводить: статус, вага, отримувач, відправник, адреси, дати доставки, вартість."],
            ["Видалити замовлення ❌",
             "Дозволяє клієнту самостійно видалити своє замовлення "
             "(тільки якщо воно на передоплаті та ще не сплачено)."],
            ["Переглянути реквізити",
             "Показує реквізити магазину для переказу оплати (картка, ПІБ тощо)."],
            ["Статус замовлень 📦",
             "Ярлик для виклику статусу замовлень (аналог кнопки 'статус')."],
            ["Зв'язок з нами 📞",
             "Ярлик для показу контактів."],
        ]
    )
    add_spacer(doc)

    # ── 1.4 Автоматичні повідомлення клієнту ──────────────────────────────────
    set_heading(doc, "1.4 Автоматичні повідомлення клієнту", 2)
    add_paragraph(doc,
        "Бот автоматично надсилає клієнту такі повідомлення (без його дій):", italic=True)
    add_table(doc,
        ["Подія", "Повідомлення клієнту"],
        [
            ["Нове замовлення створено",
             "Картка нового замовлення з деталями (товари, адреса, тип платежу, сума)."],
            ["Замовлення відправлено (ТТН оновлено)",
             "Повідомлення «Ваше замовлення відправлено» + ТТН + кнопка відстеження."],
            ["Посилка прибула у відділення",
             "Повідомлення «Ваше замовлення прибуло у відділення» + кнопка відстеження."],
            ["Замовлення завершено",
             "Повідомлення «Дякуємо за замовлення! До нових зустрічей»."],
            ["Замовлення видалено адміністратором",
             "Повідомлення «Ваше замовлення видалено» + причина (якщо вказана) + кнопка зв'язку."],
            ["Замовлення об'єднано",
             "Повідомлення про об'єднання з номером нового замовлення."],
            ["Тип платежу змінено на НП",
             "Повідомлення «Тип замовлення змінено на накладений платіж»."],
            ["Нарахована знижка",
             "Повідомлення «Вам нарахована нова знижка» + кнопка «Знижки»."],
            ["Замовлення не оплачене (нагадування)",
             "Нагадування про несплачене замовлення (надсилається 1–2 рази з інтервалом ~1 год)."],
        ]
    )
    add_spacer(doc)

    # ══════════════════════════════════════════════════════════════════════════
    # ЧАСТИНА 2 — ДЛЯ АДМІНІСТРАТОРІВ
    # ══════════════════════════════════════════════════════════════════════════
    set_heading(doc, "ЧАСТИНА 2. Функції для адміністраторів", 1)
    add_paragraph(doc,
        "Адміністратори мають доступ до панелі управління через команду /admin.",
        italic=True)
    add_spacer(doc)

    # ── 2.1 Вхід в адмін-панель ────────────────────────────────────────────────
    set_heading(doc, "2.1 Вхід до адмін-панелі (/admin)", 2)
    add_paragraph(doc,
        "Команда /admin доступна лише для Telegram ID, зареєстрованих у списку адміністраторів "
        "(задано в коді). "
        "Відкриває меню з кнопками керування.")
    add_spacer(doc)

    # ── 2.2 Меню адмін-панелі ─────────────────────────────────────────────────
    set_heading(doc, "2.2 Кнопки адмін-панелі", 2)
    add_table(doc,
        ["Кнопка", "Дія"],
        [
            ["Активні замовлення 📃",
             "Виводить список усіх незавершених замовлень з деталями. "
             "Для кожного — кнопки: перегляд, позначити сплаченим, видалити, "
             "об'єднати, змінити на НП, перевірити ТТН."],
            ["Переглянути усіх клієнтів 👨🏻",
             "Виводить список усіх клієнтів (ID, ім'я, телефон, email, сума за місяць). "
             "Для кожного є кнопка «Додати знижку»."],
            ["Знижки 💎",
             "Показує таблицю порогів знижок (поріг → %). "
             "Кнопка «Редагувати знижки» дозволяє видалити або додати рівень."],
            ["Встановити реквізити 💳",
             "Відкриває форму редагування реквізитів магазину (ПІБ, номер картки). "
             "Зберігається у props.json."],
            ["Переглянути реквізити",
             "Виводить поточні реквізити магазину."],
            ["Створити оголошення 🖼",
             "Запускає процес масового розсилання. "
             "Вибір формату: з фото чи без. "
             "Адмін надсилає повідомлення, бот розсилає їх усім зареєстрованим користувачам."],
        ]
    )
    add_spacer(doc)

    # ── 2.3 Управління конкретним замовленням ─────────────────────────────────
    set_heading(doc, "2.3 Управління замовленнями", 2)
    add_table(doc,
        ["Дія", "Опис"],
        [
            ["Переглянути замовлення",
             "Показує повну картку замовлення: клієнт (з Remonline), адреса, товари, "
             "знижка, сума, ТТН, тип та статус платежу."],
            ["Зробити сплаченим 💸",
             "Позначає замовлення як оплачене в системі."],
            ["Видалити замовлення ❌",
             "Видаляє замовлення. Клієнту надсилається повідомлення."],
            ["Закрити замовлення ✅",
             "Завершує замовлення (is_completed = true). "
             "Клієнту надсилається повідомлення «Дякуємо»."],
            ["Змінити на накладений платіж 📥",
             "Змінює тип оплати з передплати на накладений платіж. "
             "Клієнту надсилається повідомлення."],
            ["Відстежити замовлення 🔍",
             "Перевіряє статус посилки за ТТН через API Нової Пошти."],
            ["Об'єднати з іншим замовленням 🔀",
             "Об'єднує поточне замовлення з іншим (inline query для вибору цільового замовлення). "
             "Клієнту надсилається повідомлення про об'єднання."],
        ]
    )
    add_spacer(doc)

    # ── 2.4 Управління TTN ────────────────────────────────────────────────────
    set_heading(doc, "2.4 Додавання ТТН до замовлення", 2)
    add_paragraph(doc,
        "Адмін може додати або оновити ТТН (номер відправлення Нової Пошти) до замовлення:")
    steps_ttn = [
        ("1", "Натиснути кнопку «Додати ТТН» (доступна в картці замовлення або через команду)."),
        ("2", "Ввести ID замовлення."),
        ("3", "Ввести номер ТТН."),
        ("4", "Бот оновлює ТТН у системі та сповіщає клієнта про відправлення."),
    ]
    for num, text in steps_ttn:
        add_paragraph(doc, f"  {num}. {text}")
    add_spacer(doc)

    # ── 2.5 Управління знижками ────────────────────────────────────────────────
    set_heading(doc, "2.5 Управління знижками", 2)
    add_paragraph(doc, "Два типи операцій зі знижками:")
    add_table(doc,
        ["Тип", "Опис", "Формат вводу"],
        [
            ["Додати рівень знижки",
             "Додає новий поріг у таблицю знижок (місячна сума → %).",
             "Повідомлення у форматі: сума@відсоток\nПриклад: 5000@10"],
            ["Видалити рівень",
             "Видаляє вибраний рівень знижки за ID.",
             "Кнопка «Видалити» поруч із рівнем"],
            ["Додати бонусну знижку клієнту",
             "Вручну нараховує знижку конкретному клієнту.",
             "Крок 1: ввести ID клієнта; Крок 2: ввести кількість (%)"],
        ]
    )
    add_spacer(doc)

    # ── 2.6 Шаблони розсилок ──────────────────────────────────────────────────
    set_heading(doc, "2.6 Шаблони розсилок", 2)
    add_table(doc,
        ["Дія", "Опис"],
        [
            ["Переглянути шаблони",
             "Показує список збережених шаблонів з кнопками відправки та видалення."],
            ["Надіслати шаблон",
             "Розсилає текст шаблону всім зареєстрованим користувачам бота."],
            ["Створити шаблон",
             "Крок 1: ввести назву; Крок 2: ввести текст. "
             "Шаблон зберігається через backend API."],
            ["Видалити шаблон",
             "Видаляє шаблон за ID."],
        ]
    )
    add_spacer(doc)

    # ── 2.7 Автоматичні повідомлення адміністратору ────────────────────────────
    set_heading(doc, "2.7 Автоматичні повідомлення адміністратору", 2)
    add_table(doc,
        ["Подія", "Повідомлення адміністратору"],
        [
            ["Новий клієнт зареєструвався",
             "Повідомлення з ID, ім'ям, прізвищем та телефоном нового клієнта."],
            ["Нове замовлення",
             "«Нове замовлення в remonline успішно створено!»"],
            ["Нове замовлення з передоплатою",
             "Повна картка замовлення + кнопки керування."],
            ["Нове замовлення з НП",
             "«Нове замовлення з накладеним платежом!» + ID замовлення."],
            ["Замовлення видалено",
             "Підтвердження видалення."],
            ["Помилка Remonline timeout",
             "Повідомлення про помилку синхронізації з Remonline CRM "
             "та ID замовлення для перевірки."],
            ["Несплачені замовлення (щогодинно)",
             "Кількість несплачених замовлень."],
        ]
    )
    add_spacer(doc)

    # ══════════════════════════════════════════════════════════════════════════
    # ЧАСТИНА 3 — ВНУТРІШНІ ФУНКЦІЇ (ДЛЯ РОЗРОБНИКІВ)
    # ══════════════════════════════════════════════════════════════════════════
    set_heading(doc, "ЧАСТИНА 3. Внутрішні (підкапотні) функції", 1)
    add_paragraph(doc,
        "Цей розділ призначений для розробників. "
        "Описані модулі, класи та функції, що забезпечують роботу бота.",
        italic=True)
    add_spacer(doc)

    # ── 3.1 FSM-стани ─────────────────────────────────────────────────────────
    set_heading(doc, "3.1 FSM-стани (bot/States.py)", 2)
    add_paragraph(doc,
        "Для багатокрокових діалогів використовується aiogram FSM (Finite State Machine). "
        "Стани зберігаються у пам'яті (MemoryStorage).")
    add_table(doc,
        ["Клас стану", "Кроки", "Призначення"],
        [
            ["NewTTN", "order_id → ttn_state", "Додавання ТТН до замовлення"],
            ["NewPost", "set → messages", "Створення масової розсилки"],
            ["NewTextPost", "text", "Текстова розсилка без фото"],
            ["NewClientDiscount", "client_id → count", "Ручне нарахування знижки клієнту"],
            ["NewProps", "set → full_name → card", "Редагування реквізитів магазину"],
            ["NewTemplate", "name → text", "Створення шаблону розсилки"],
            ["MergeOrderState", "source_order_id → target_order_id", "Об'єднання замовлень"],
        ]
    )
    add_spacer(doc)

    # ── 3.2 Фонові задачі ─────────────────────────────────────────────────────
    set_heading(doc, "3.2 Фонові задачі (bot/updates.py)", 2)
    add_paragraph(doc,
        "Три асинхронні задачі запускаються при старті бота через asyncio та виконуються нескінченно.")
    add_table(doc,
        ["Функція", "Інтервал", "Що робить"],
        [
            ["order_updates(bot, admin_list)",
             "кожні 10 секунд",
             "Опитує endpoint /api/v2/order-events/ на наявність нових подій замовлень. "
             "Маршрутизація — словник updates.ORDER_EVENT_HANDLERS, ключі якого збігаються "
             "з OrderEventType в backend/core/models.py (стежить tests/test_event_contract.py). "
             "Невідомий код пишеться в лог, а не зникає мовчки. "
             "Після обробки видаляє запис події."],
            ["client_updates(bot, admin_list)",
             "кожні 10 секунд",
             "Опитує /api/v2/client-events/ на нових клієнтів. "
             "При події CREATED — надсилає адміністратору дані нового клієнта. "
             "Після обробки видаляє запис події."],
        ]
    )
    add_spacer(doc)

    # ── 3.3 API-клієнт ────────────────────────────────────────────────────────
    set_heading(doc, "3.3 API-клієнт (bot/api.py)", 2)
    add_paragraph(doc,
        "Всі HTTP-запити до Django-бекенду виконуються через aiohttp. "
        "Аутентифікація — заголовок x-api-key. "
        "Базовий URL задається через змінну середовища BACKEND_API_BASE.")
    add_spacer(doc)

    set_heading(doc, "3.3.1 Пагінація", 3)
    add_table(doc,
        ["Функція", "Опис"],
        [
            ["_fetch_paginated(endpoint, limit)",
             "Універсальна функція для отримання всіх записів з пагінованих ендпоінтів. "
             "Крок пагінації: 100 записів. Зупиняється коли next=null або досягнуто limit."],
        ]
    )
    add_spacer(doc)

    set_heading(doc, "3.3.2 Замовлення", 3)
    add_table(doc,
        ["Функція", "HTTP-метод + URL", "Опис", "Статус"],
        [
            ["get_orders_by_tg_id(telegram_id)", "GET /api/v2/orders?telegram_id=...",
             "Всі замовлення користувача за Telegram ID", "✅ Працює"],
            ["get_order_by_id(order_id)", "GET /api/v2/orders/{id}",
             "Замовлення за ID", "✅ Працює"],
            ["get_active_orders(limit)", "GET /api/v2/orders?is_completed=0",
             "Всі активні замовлення", "✅ Працює"],
            ["get_active_orders_by_telegram_id(telegram_id)",
             "GET /api/v2/orders?is_completed=0&telegram_id=...",
             "Активні замовлення конкретного користувача", "✅ Працює"],
            ["delete_order(order_id)", "DELETE /api/v2/orders/{id}/",
             "Видалення замовлення", "✅ Виправлено (була опечатка /order/)"],
            ["make_pay_order(order_id)", "PATCH /api/v2/orders/{id}/ {\"is_paid\": true}",
             "Позначити замовлення як сплачене", "✅ Виправлено"],
            ["merge_order(source_id, target_id)", "—",
             "Об'єднання двох замовлень", "⚠️ Потребує реалізації на бекенді"],
            ["update_ttn(order_id, ttn)", "PATCH /api/v2/orders/{id}/ {\"ttn\": ...}",
             "Оновлення ТТН замовлення", "✅ Виправлено"],
            ["finish_order(order_id)", "PATCH /api/v2/orders/{id}/ {\"is_completed\": true}",
             "Завершення (деактивація) замовлення", "✅ Виправлено"],
            ["change_to_not_prepayment(order_id)",
             "PATCH /api/v2/orders/{id}/ {\"prepayment\": false}",
             "Зміна типу оплати на накладений платіж", "✅ Виправлено"],
            ["get_order_by_ttn(ttn)", "GET /api/v2/orders?ttn=...",
             "Пошук замовлення за ТТН", "✅ Виправлено (була опечатка /order)"],
            ["update_branch_remember_count(order_id)",
             "PATCH /api/v2/orders/{id}/ {\"branch_remember_count\": n+1}",
             "Оновлення лічильника нагадувань про посилку у відділенні",
             "✅ Виправлено (GET + PATCH)"],
        ]
    )
    add_spacer(doc)

    set_heading(doc, "3.3.3 Клієнти", 3)
    add_table(doc,
        ["Функція", "HTTP-метод + URL", "Опис", "Статус"],
        [
            ["get_all_clients(limit)", "GET /api/v2/clients/",
             "Всі клієнти", "✅ Працює"],
            ["get_client_by_id(client_id)", "GET /api/v2/clients/{id}",
             "Клієнт за ID", "✅ Працює"],
            ["get_client_by_tg_id(telegram_id)", "GET /api/v2/clients?telegram_id=...",
             "Клієнт за Telegram ID", "✅ Працює"],
            ["check_auth(telegram_id)", "GET /api/v2/clients?telegram_id={id}",
             "Перевірка авторизації (чи прив'язаний акаунт)", "✅ Виправлено"],
            ["get_discount(client_id)", "GET /api/v2/clients/{id}/discount-info/",
             "Інформація про знижку клієнта", "✅ Працює"],
            ["get_discount_percentage(client_id)", "GET /api/v2/clients/{id}/discount-info/",
             "Відсоток знижки клієнта", "✅ Працює"],
            ["get_money_spend_cur_month(client_id)",
             "GET /api/v2/clients/{id}/current-month-spending/",
             "Сума витрат клієнта за поточний місяць", "✅ Працює"],
            ["add_bonus_client_discount(client_id, count)",
             "—",
             "Нарахування бонусної знижки клієнту", "⚠️ Потребує реалізації на бекенді"],
        ]
    )
    add_spacer(doc)

    set_heading(doc, "3.3.4 Відвідувачі бота", 3)
    add_table(doc,
        ["Функція", "HTTP-метод + URL", "Опис", "Статус"],
        [
            ["add_new_visitor(telegram_id)", "POST /api/v2/bot-visitors/",
             "Реєстрація нового відвідувача", "✅ Працює"],
            ["get_visitors(limit)", "GET /api/v2/bot-visitors/",
             "Список відвідувачів (для розсилок)", "✅ Працює"],
            ["delete_visitor(id)", "DELETE /api/v2/bot-visitors/{id}/",
             "Видалення відвідувача", "✅ Працює"],
            ["link_account_via_code(code, telegram_id, telegram_user)",
             "POST /api/v2/telegram/link/consume/",
             "Прив'язка Telegram до акаунту через одноразовий код", "✅ Працює"],
        ]
    )
    add_spacer(doc)

    set_heading(doc, "3.3.5 Знижки та товари", 3)
    add_table(doc,
        ["Функція", "HTTP-метод + URL", "Опис", "Статус"],
        [
            ["get_all_goods(limit)", "GET /api/v2/goods/",
             "Всі товари", "✅ Працює"],
            ["get_discounts_info(limit)", "GET /api/v2/discounts/",
             "Таблиця рівнів знижок", "✅ Працює"],
            ["delete_discount(discount_id)", "DELETE /api/v2/discounts/{id}/",
             "Видалення рівня знижки", "✅ Працює"],
            ["post_discount(procent, month_payment)", "POST /api/v2/discount/",
             "Створення рівня знижки", "❌ Не працює (URL: /discount/ замість /discounts/)"],
        ]
    )
    add_spacer(doc)

    set_heading(doc, "3.3.6 Шаблони", 3)
    add_table(doc,
        ["Функція", "HTTP-метод + URL", "Опис", "Статус"],
        [
            ["get_templates(limit)", "GET /api/v2/templates/",
             "Список шаблонів", "✅ Працює"],
            ["get_template(template_id)", "GET /api/v2/templates/{id}/",
             "Шаблон за ID", "✅ Працює"],
            ["create_template(name, text)", "POST /api/v2/templates/",
             "Створення шаблону", "✅ Працює"],
            ["delete_template(template_id)", "DELETE /api/v2/templates/{id}/",
             "Видалення шаблону", "✅ Працює"],
        ]
    )
    add_spacer(doc)

    set_heading(doc, "3.3.7 Події (order-events, client-events)", 3)
    add_table(doc,
        ["Функція", "HTTP-метод + URL", "Опис", "Статус"],
        [
            ["get_order_updates(limit)", "GET /api/v2/order-events/",
             "Список нових подій замовлень", "✅ Працює"],
            ["delete_order_updates(id)", "DELETE /api/v2/order-events/{id}/",
             "Видалення обробленої події замовлення", "✅ Працює"],
            ["get_clients_updates(limit)", "GET /api/v2/client-events/",
             "Список нових подій клієнтів", "✅ Працює"],
            ["delete_client_update(id)", "DELETE /api/v2/client-events/{id}/",
             "Видалення обробленої події клієнта", "✅ Працює"],
        ]
    )
    add_spacer(doc)

    set_heading(doc, "3.3.8 Нова Пошта", 3)
    add_table(doc,
        ["Функція", "Опис", "Статус"],
        [
            ["ttn_tracking(ttn, recipient_phone)",
             "Відстеження посилки через API Нової Пошти (TrackingDocument.getStatusDocuments). "
             "Повертає статус, вагу, адреси, дати.",
             "✅ Працює (зовнішній API)"],
        ]
    )
    add_spacer(doc)

    # ── 3.4 Утиліти engine.py ─────────────────────────────────────────────────
    set_heading(doc, "3.4 Утиліти (bot/engine.py)", 2)
    add_table(doc,
        ["Функція", "Опис"],
        [
            ["find_good(goods, good_id)",
             "Знаходить товар у списку за ID. Повертає dict або None."],
            ["make_order(bot, telegram_id, order_items, goods, order, client)",
             "Формує та надсилає картку замовлення клієнту. "
             "Розраховує суму зі знижкою, додає кнопки (ТТН, оплата, реквізити). "
             "Примітка: є TODO щодо коректності quantity."],
            ["base_client_info_builder(client)",
             "Форматує рядок з базовими даними клієнта (ПІБ + телефон)."],
            ["build_order_suma(order)",
             "Обчислює загальну суму замовлення з позицій (original_price_minor × quantity)."],
            ["manager_notes_builder(order, goods)",
             "Формує повний текст адмін-картки замовлення: "
             "клієнт, адреса, товари, знижка, сума, ТТН. "
             "Використовується при виведенні замовлення адміністратору."],
            ["show_order_goods(order)",
             "Повертає рядок зі списком товарів замовлення (назва + кількість)."],
            ["id_spliter(callback_data)",
             "Парсить ID з рядка callback_data формату 'action/ID'. "
             "Приклад: 'delete_order/45' → 45."],
            ["ttn_info_builder(response, order)",
             "Форматує відповідь API Нової Пошти у читабельний текст для Telegram."],
            ["send_messages_to_admins(bot, admin_ids, text, reply_markup)",
             "Надсилає повідомлення всім адміністраторам. Пропускає помилки ChatNotFound/BotBlocked."],
            ["send_error_log(bot, admin_id, error)",
             "Надсилає повідомлення про помилку конкретному адміністратору."],
        ]
    )
    add_spacer(doc)

    # ── 3.5 Утиліти utils/ ────────────────────────────────────────────────────
    set_heading(doc, "3.5 Утиліти (bot/utils/)", 2)
    add_table(doc,
        ["Файл", "Функція", "Опис"],
        [
            ["utils/utils.py", "to_major(value)",
             "Конвертує суму з мінорних одиниць у основні (divide by 100). "
             "Приклад: 10000 → 100.00 грн"],
            ["utils/utils.py", "to_minor(value)",
             "Конвертує суму з основних одиниць у мінорні (multiply by 100). "
             "Приклад: 100 → 10000"],
            ["utils/inline.py", "inline_paginator(items, page_size=50)",
             "Розбиває список на сторінки по 50 елементів для inline-запитів."],
        ]
    )
    add_spacer(doc)

    # ── 3.6 Сповіщення notifications.py ──────────────────────────────────────
    set_heading(doc, "3.6 Сповіщення (bot/notifications.py)", 2)
    add_table(doc,
        ["Функція", "Призначення", "Нотатки"],
        [
            ["check_status_notification(bot, telegram_id, order)",
             "Показує деталі замовлення клієнту (аналог команди «статус»).",
             "Бере id клієнта з поля order['client'] та позиції з order['items']."],
            ["new_order_notification(bot, order, admin_list)",
             "Сповіщає адмінів про нове замовлення в remonline.",
             "—"],
            ["merge_order_notification(bot, order)",
             "Сповіщає клієнта про об'єднання замовлень.",
             "Баг: відсутній telegram_id для send_message (замість bot.send_message треба order['telegram_id'])"],
            ["ttn_update_notification(bot, order)",
             "Сповіщає клієнта про відправлення посилки (ТТН оновлено).",
             "—"],
            ["order_in_branch_reminder_notifications(bot, order, remember_time)",
             "Затримане нагадування про посилку у відділенні (через asyncio.sleep).",
             "—"],
            ["new_order_client_notification(bot, order)",
             "Показує клієнту картку щойно створеного замовлення.",
             "—"],
            ["no_connection_with_server_notification(bot, message)",
             "Повідомляє користувача про недоступність сервера.",
             "—"],
            ["order_in_branch_notifications(bot, order)",
             "Сповіщає клієнта що посилка прибула у відділення.",
             "—"],
            ["deactivated_notifications(bot, order, admin_list)",
             "Сповіщає клієнта та адміна про завершення замовлення.",
             "—"],
            ["deleted_notifications(bot, order, reason, admin_list)",
             "Сповіщає клієнта та адміна про видалення замовлення.",
             "Також викликає delete_order() — подвійне видалення якщо вже видалено."],
            ["client_added_bonus_notifications(bot, client_id)",
             "Сповіщає клієнта про нарахування бонусної знижки.",
             "—"],
            ["unknown_error_notifications(bot, telegram_id)",
             "Загальне повідомлення про помилку.",
             "—"],
            ["change_to_not_prepayment_notifications(bot, order_id, telegram_id)",
             "Сповіщає клієнта про зміну типу оплати.",
             "—"],
        ]
    )
    add_spacer(doc)

    # ── 3.7 Конфігурація ──────────────────────────────────────────────────────
    set_heading(doc, "3.7 Конфігурація (bot/config.py)", 2)
    add_table(doc,
        ["Змінна", "Env var", "Призначення"],
        [
            ["BOT_TOKEN", "BOT_TOKEN", "Токен Telegram-бота"],
            ["BASE_URL / BACKEND_API_BASE", "BACKEND_API_BASE або BASE_URL",
             "Базовий URL Django-бекенду"],
            ["BACKEND_API_KEY", "BACKEND_API_KEY", "Ключ для x-api-key заголовку"],
            ["NOVA_POST_API_KEY", "NOVA_POST_API_KEY", "API-ключ Нової Пошти"],
            ["WEB_URL", "WEB_APP_URL", "URL Telegram WebApp"],
            ["PRICE_ID_PROD", "PRICE_ID_PROD", "ID ціни для Telegram Payments"],
            ["REMONLINE_API_KEY_PROD", "API_KEY_PROD", "API-ключ Remonline CRM"],
            ["DEFAULT_BRANCH_PROD", "BRANCH_PROD", "ID відділення Remonline за замовчуванням"],
            ["LOCAL_PROXY_URL", "LOCAL_PROXY_URL", "Локальний проксі (для розробки)"],
        ]
    )
    add_spacer(doc)

    # ── 3.8 Логування ─────────────────────────────────────────────────────────
    set_heading(doc, "3.8 Логування (bot/logger.py)", 2)
    add_paragraph(doc,
        "Використовується structlog + Rich. Логи виводяться в консоль та записуються у файл. "
        "Функція setup_logging() ініціалізується при старті бота. "
        "Глобальний logger доступний через import logger із будь-якого модуля.")
    add_spacer(doc)

    # ══════════════════════════════════════════════════════════════════════════
    # ЧАСТИНА 4 — ВІДОМІ ПРОБЛЕМИ
    # ══════════════════════════════════════════════════════════════════════════
    set_heading(doc, "ЧАСТИНА 4. Проблеми та залишкові задачі", 1)
    add_paragraph(doc,
        "9 з 11 несумісностей з новим бекендом виправлено в bot/api.py. "
        "Залишилися дві функції, що вимагають реалізації на бекенді.",
        italic=True)
    add_spacer(doc)

    add_paragraph(doc, "4.1 Виправлені функції bot/api.py", bold=True)
    add_table(doc,
        ["Функція", "Старий URL", "Новий URL"],
        [
            ["make_pay_order()", "POST /api/v2/payorder/{id}",
             "PATCH /api/v2/orders/{id}/ {\"is_paid\": true}"],
            ["check_auth()", "GET /api/v2/isauthendicated/{id}",
             "GET /api/v2/clients?telegram_id={id} → {\"success\": bool}"],
            ["update_ttn()", "PATCH /api/v2/updatettn/",
             "PATCH /api/v2/orders/{id}/ {\"ttn\": ttn}"],
            ["update_branch_remember_count()", "PATCH /api/v2/branch_remember_count/{id}",
             "GET order + PATCH /api/v2/orders/{id}/ {\"branch_remember_count\": n+1}"],
            ["finish_order()", "PATCH /api/v2/disactiveorder/{id}",
             "PATCH /api/v2/orders/{id}/ {\"is_completed\": true}"],
            ["delete_order()", "DELETE /api/v2/order/{id}/",
             "DELETE /api/v2/orders/{id}/ (виправлена опечатка)"],
            ["post_discount()", "POST /api/v2/discount/ {procent:...}",
             "POST /api/v2/discounts/ {percentage:...} (виправлені URL і поле)"],
            ["get_order_by_ttn()", "GET /api/v2/order?ttn=",
             "GET /api/v2/orders?ttn= (виправлена опечатка)"],
            ["change_to_not_prepayment()", "PATCH /api/v2/orders/tonotprepayment/{id}",
             "PATCH /api/v2/orders/{id}/ {\"prepayment\": false}"],
        ]
    )
    add_spacer(doc)

    add_paragraph(doc, "4.2 Потребують реалізації на бекенді", bold=True)
    add_table(doc,
        ["Функція", "Опис", "Рекомендація"],
        [
            ["merge_order(source_id, target_id)",
             "Об'єднання двох замовлень в одне",
             "Додати POST /api/v2/orders/merge/ на бекенді"],
            ["add_bonus_client_discount(client_id, count)",
             "Ручне нарахування бонусної знижки клієнту",
             "Додати POST /api/v2/clients/{id}/add-bonus/ на бекенді"],
        ]
    )
    add_spacer(doc)
    add_spacer(doc)

    add_paragraph(doc, "4.3 Баги в notifications.py (не виправлені — окрема задача):", bold=True)
    add_table(doc,
        ["Функція", "Проблема"],
        [
            ["merge_order_notification()",
             "Відсутній перший аргумент у bot.send_message() — не переданий telegram_id клієнта. "
             "Повідомлення ніколи не надсилається."],
            ["deleted_notifications()",
             "Викликає delete_order() повторно після того як бекенд вже видалив замовлення — "
             "призведе до 404 (тепер delete_order повертає True/None замість dict)."],
        ]
    )

    return doc


# ─── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "bot_functions.docx")

    doc = build_document()
    doc.save(out_path)
    print(f"Документ збережено: {os.path.abspath(out_path)}")
