import logging
from decimal import ROUND_HALF_UP, Decimal

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import CATEGORIES_IGNORE_IDS, PRICE_ID_PROD, REMONLINE_API_KEY
from core.services.remonline.api import RemonlineInterface

logger = logging.getLogger(__name__)


def sync_goods():
    from django.db import transaction

    from core.models import Good, GoodCategory

    remonline = RemonlineInterface(REMONLINE_API_KEY)
    goods_data = remonline.get_goods(remonline.get_main_warehouse_id())
    # --- Категории ---
    categories_data = {}
    for item in goods_data:
        cat = item.get("category")
        if cat and "id" in cat:
            categories_data[cat["id"]] = cat
    category_ids = list(categories_data.keys())

    existing_categories = {
        c.id_remonline: c
        for c in GoodCategory.objects.filter(id_remonline__in=category_ids)
    }
    categories_to_update = []
    categories_to_create = []
    for cat_id, cat in categories_data.items():
        obj = existing_categories.get(cat_id)
        defaults = {
            "title": cat.get("title", ""),
            "parent_id": cat.get("parent_id"),
        }
        if obj:
            changed = False
            for k, v in defaults.items():
                if getattr(obj, k) != v:
                    setattr(obj, k, v)
                    changed = True
            if changed:
                categories_to_update.append(obj)
        else:
            new_cat = GoodCategory(id_remonline=cat_id, **defaults)
            existing_categories[cat_id] = new_cat
            categories_to_create.append(new_cat)

    with transaction.atomic():
        if categories_to_create:
            GoodCategory.objects.bulk_create(categories_to_create)
        if categories_to_update:
            GoodCategory.objects.bulk_update(
                categories_to_update, ["title", "parent_id"]
            )

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
            cat_obj = existing_categories.get(cat["id"])
        if cat.get("id") in CATEGORIES_IGNORE_IDS:
            continue

        # Подготавливаем данные для товара
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
                ],
            )

    logger.info(
        f"Goods sync complete: created {len(goods_to_create)}, updated {len(goods_to_update)}"
    )


def to_minor(v):
    return int(
        (Decimal(str(v)) * Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def start_scheduler():
    logger.info("Scheduler started!")

    scheduler = BackgroundScheduler()
    scheduler.add_job(sync_goods, CronTrigger(minute="*"))
    scheduler.start()
    return scheduler
