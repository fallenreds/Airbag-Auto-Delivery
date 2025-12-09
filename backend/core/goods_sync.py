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


def to_minor(v):
    return int(
        (Decimal(str(v)) * Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )

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



def sync_goods_and_categories():
    remonline = RemonlineInterface(REMONLINE_API_KEY)
    goods_data = remonline.get_goods(remonline.get_main_warehouse_id())
    # --- Категории ---
    categories = sync_categories()
    
    
    # --- Товары ---
    remonline_ids = [item["id"] for item in goods_data]
    logger.info(f"Remonline goods count: {len(goods_data)}")

    # Получаем существующие товары по remonline_id
    existing_goods = {
        g.id_remonline: g for g in Good.objects.filter(id_remonline__in=remonline_ids)
    }

    goods_to_create = []
    goods_to_update = []

    for item in goods_data:
        cat_obj = None
        cat = item.get("category")
        if cat and "id" in cat:
            cat_obj = categories.get(cat["id"])

        if cat.get("id") in CATEGORIES_IGNORE_IDS:
            continue

        # Подготавливаем данные для товара
        goods_data_dict = {
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "images": item.get("image", []),
            # цена в минимальных единицах и +100
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
        remonline_id = item["id"]
        existing_good = existing_goods.get(remonline_id)

        if existing_good:
            # Обновляем существующий товар
            changed = False
            for field, value in goods_data_dict.items():
                if getattr(existing_good, field) != value:
                    setattr(existing_good, field, value)
                    changed = True

            if changed:
                goods_to_update.append(existing_good)
        else:
            # Создаем новый товар
            new_good = Good(id_remonline=remonline_id, **goods_data_dict)
            goods_to_create.append(new_good)

    with transaction.atomic():
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
        f"Goods sync complete: created {len(goods_to_create)}, updated {len(goods_to_update)}"
    )
