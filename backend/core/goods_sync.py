"""
Файл синхронизации това
"""

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from config.settings import (
    CATEGORIES_IGNORE_IDS,
    PRICE_ID_PROD,
    REMONLINE_API_KEY,
    REMONLINE_TOGETHERBUY_CUSTOM_FIELD_ID,
)
from core.models import Good, GoodCategory
from core.services.remonline.api import RemonlineInterface

logger = logging.getLogger(__name__)

def sync_goods_and_categories() -> None:
    """
    Обёртка: сначала синхронизирует категории, затем товары.
    """
    categories = sync_categories()
    sync_goods(categories)

def sync_categories()->list[GoodCategory]:
    """
    Синхронизирует категории с Remonline
    Возвращает текущий список категорий
    Игорирует ненужные категории (включая дочерние)
    Удаляет категории которые уже не существуют в ремонлайн
    Удаляет категории которые игнорируются
    Обновляет категории которые изменились
    Добавляет категории которые есть в ремонлайн и нет в БД
    """
    remonline = RemonlineInterface(REMONLINE_API_KEY)
    remonline_categories_data = remonline.get_categories()
    # Корневые игнорируемые категории (указываешь ты)
    ignore_root_ids = set(CATEGORIES_IGNORE_IDS)

    # Полный список ID, которые нужно игнорировать (включая потомков)
    ignored_ids = get_ignored_category_ids(remonline_categories_data, ignore_root_ids)

    # Категории из БД
    db_categories = GoodCategory.objects.all()
    current_map = {c.id_remonline: c for c in db_categories}

    categories_to_create = []   # новые категории
    categories_to_update = []   # категории для обновления

    # Обрабатываем категории из Remonline
    for category in remonline_categories_data:
        cat_id = category["id"]

        # Пропускаем игнорируемые
        if cat_id in ignored_ids:
            continue

        existing = current_map.get(cat_id)

        if existing is None:
            # Новая категория
            categories_to_create.append(
                GoodCategory(
                    id=cat_id,
                    id_remonline=cat_id,
                    title=category["title"],
                    parent_id=category.get("parent_id"),
                )
            )
        else:
            # Изменились название или parent
            if existing.title != category["title"] or existing.parent_id != category.get("parent_id"):
                existing.title = category["title"]
                existing.parent_id = category.get("parent_id")
                categories_to_update.append(existing)

    # ID категорий, которые реально должны быть в БД по данным Remonline (без игнорируемых)
    remonline_ids = {
        c["id"]
        for c in remonline_categories_data
        if c["id"] not in ignored_ids
    }

    db_ids = {c.id_remonline for c in db_categories}

    # Удаляем:
    # 1) всё, что попало в игнор
    # 2) всё, чего больше нет в Remonline среди неигнорируемых
    ids_to_delete = (db_ids & ignored_ids) | (db_ids - remonline_ids)

    with transaction.atomic():
        if ids_to_delete:
            GoodCategory.objects.filter(id_remonline__in=ids_to_delete).delete()

        if categories_to_create:
            GoodCategory.objects.bulk_create(categories_to_create)

        if categories_to_update:
            GoodCategory.objects.bulk_update(categories_to_update, ["title", "parent_id"])

        # Текущий список категорий после синка
        current_categories = list(GoodCategory.objects.all())

    logger.info(f"Synced categories: {len(current_categories)}")
    return current_categories

def get_ignored_category_ids(remonline_categories_data:list[dict], ignore_root_ids:set[int]):
    """
    remonline_categories_data: список dict-ов с полями "id", "parent_id"
    ignore_root_ids: set/id категорий, от которых игнорируем всё поддерево
    """
    # parent_id -> [child_id, ...]
    children_map = {}
    for cat in remonline_categories_data:
        pid = cat.get("parent_id") #Ремонлайн отправляет без ключа если нет перента
        cid = cat["id"]
        children_map.setdefault(pid, []).append(cid)

    ignored_ids = set(ignore_root_ids)
    stack = list(ignore_root_ids)

    # DFS/BFS по дереву от корневых игнорируемых категорий
    while stack:
        current_id = stack.pop()

        for child_id in children_map.get(current_id, []):
            if child_id not in ignored_ids:
                ignored_ids.add(child_id)
                stack.append(child_id)

    return ignored_ids

def sync_goods(categories: list[GoodCategory]) -> None:
    """
    Синхронизирует товары с Remonline.

    Функция:
    - получает список категорий, актуальных после sync_categories()
    - удаляет товары, которые:
        * исчезли из Remonline
        * принадлежат категориям, которых больше нет (в т.ч. игнорируемым)
    - обновляет товары, данные которых изменились в Remonline
    - добавляет товары, которых нет в БД, но они есть в Remonline
    """
    remonline = RemonlineInterface(REMONLINE_API_KEY)

    # Категории для привязки товаров: id_remonline → объект
    categories_by_remote_id = {c.id_remonline: c for c in categories}
    # Актуальные pk категорий: используются для проверки валидности существующих товаров
    valid_category_ids_db = {c.id for c in categories}

    # --- Товары из Remonline ---
    goods_data = remonline.get_goods(remonline.get_main_warehouse_id())
    remonline_good_ids = {item["id"] for item in goods_data}
    logger.info(f"Remonline goods count: {len(remonline_good_ids)}")

    # --- Текущие товары из БД ---
    existing_goods_qs = Good.objects.all()
    existing_goods = {g.id_remonline: g for g in existing_goods_qs}

    # Определяем товары, которые нужно удалить
    ids_to_delete = get_goods_ids_to_delete(
        existing_goods_qs=existing_goods_qs,
        remonline_good_ids=remonline_good_ids,
        valid_category_ids_db=valid_category_ids_db,
    )

    goods_to_create = []
    goods_to_update = []

    # --- Обработка товаров Remonline ---
    for item in goods_data:
        rem_id = item["id"]

        # Категория товара в формате Remonline
        cat = item.get("category") or {}
        remote_cat_id = cat.get("id")

        # Пропускаем товары без категории или с категорией, которую не нужно синхронизировать
        if not remote_cat_id or remote_cat_id not in categories_by_remote_id:
            continue

        cat_obj = categories_by_remote_id[remote_cat_id]
        goods_fields = build_good_fields(item, cat_obj)

        existing_good = existing_goods.get(rem_id)

        if existing_good:
            changed = False
            # Обновляем только изменённые поля
            for field, value in goods_fields.items():
                if getattr(existing_good, field) != value:
                    setattr(existing_good, field, value)
                    changed = True

            if changed:
                goods_to_update.append(existing_good)
        else:
            # Создаём новый товар
            goods_to_create.append(Good(id_remonline=rem_id, **goods_fields))

    # --- Применяем изменения ---
    with transaction.atomic():
        if ids_to_delete:
            Good.objects.filter(id_remonline__in=ids_to_delete).delete()

        if goods_to_create:
            Good.objects.bulk_create(goods_to_create)

        if goods_to_update:
            Good.objects.bulk_update(
                goods_to_update,
                [
                    "title",
                    "description",
                    "images",
                    "price_minor",
                    "residue",
                    "code",
                    "category",
                    "together_buy",
                ],
            )

    logger.info(
        f"Goods sync: created {len(goods_to_create)}, "
        f"updated {len(goods_to_update)}, "
        f"deleted {len(ids_to_delete)}"
    )


def build_good_fields(item: dict, cat_obj: GoodCategory) -> dict:
    """Собирает данные товара из ответа Remonline."""
    return {
        "title": item.get("title", ""),
        "description": item.get("description", ""),
        "images": item.get("image", []),
        "price_minor": to_minor(item.get("price", {}).get(PRICE_ID_PROD, 0)),
        "residue": int(item.get("residue", 0)),
        "code": item.get("code", ""),
        "category": cat_obj,
        "together_buy": Good.parse_ids_string(
            item.get("custom_fields", dict()).get(
                REMONLINE_TOGETHERBUY_CUSTOM_FIELD_ID, ""
            )
        ),
    }

def get_goods_ids_to_delete(
    existing_goods_qs,
    remonline_good_ids: set[int],
    valid_category_ids_db: set[int],
) -> set[int]:
    """
    Возвращает id_remonline товаров, которые нужно удалить:
    - товара нет в Remonline
    - или категория товара больше не валидна
    """
    ids_to_delete: set[int] = set()

    for g in existing_goods_qs:
        if g.id_remonline not in remonline_good_ids:
            ids_to_delete.add(g.id_remonline)
            continue

        if g.category_id and g.category_id not in valid_category_ids_db:
            ids_to_delete.add(g.id_remonline)

    return ids_to_delete

def to_minor(v):
    return int(
        (Decimal(str(v)) * Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )

