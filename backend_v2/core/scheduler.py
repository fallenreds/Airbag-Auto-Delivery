from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

from config.settings import REMONLINE_API_KEY, PRICE_ID_PROD, BONUS_ID
from core.services.remonline.api import RemonlineInterface

logger = logging.getLogger(__name__)


def sync_goods():
    from core.models import Good, GoodCategory
    from django.db import transaction
    from config.settings import BONUS_ID

    remonline = RemonlineInterface(REMONLINE_API_KEY)
    goods_data = remonline.get_goods(remonline.get_main_warehouse_id())
    goods_data = [item for item in goods_data if item['id'] != BONUS_ID]

    # --- Категории ---
    categories_data = {}
    for item in goods_data:
        cat = item.get('category')
        if cat and 'id' in cat:
            categories_data[cat['id']] = cat
    category_ids = list(categories_data.keys())

    existing_categories = {c.id_remonline: c for c in GoodCategory.objects.filter(id_remonline__in=category_ids)}
    categories_to_update = []
    categories_to_create = []
    for cat_id, cat in categories_data.items():
        obj = existing_categories.get(cat_id)
        defaults = {
            'title': cat.get('title', ''),
            'parent_id': cat.get('parent_id'),
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
            GoodCategory.objects.bulk_update(categories_to_update, ['title', 'parent_id'])

    # --- Товары ---
    remonline_ids = [item['id'] for item in goods_data]
    logger.info(f"Remonline goods count: {len(goods_data)}")
    logger.info(f"Remonline IDs: {remonline_ids}")
    # Полностью очищаем таблицу Good
    Good.objects.all().delete()
    goods_to_create = []
    for item in goods_data:
        cat_obj = None
        cat = item.get('category')
        if cat and 'id' in cat:
            cat_obj = existing_categories.get(cat['id'])
        goods_to_create.append(Good(
            id_remonline=item['id'],
            title=item.get('title', ''),
            description=item.get('description', ''),
            images=item.get('image', []),
            price=int(item.get('price', {})[PRICE_ID_PROD]),
            residue=int(item.get('residue', 0)),
            code=item.get('code', ''),
            category=cat_obj,
        ))
    with transaction.atomic():
        if goods_to_create:
            Good.objects.bulk_create(goods_to_create)
    logger.info(f"Goods sync complete: created {len(goods_to_create)}")


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(sync_goods, CronTrigger(minute='*'))
    scheduler.start()
    logger.info("Scheduler started!")
    return scheduler
