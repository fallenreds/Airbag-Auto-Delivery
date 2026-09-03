import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

# Module-level singleton to prevent multiple schedulers per process
_scheduler: Optional[BackgroundScheduler] = None


def start_scheduler() -> BackgroundScheduler:
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("Scheduler already running; skipping startup")
        return _scheduler

    from core.goods_sync import sync_goods_and_categories
    from core.order_event_handler import order_event_handler
    from core.services.order_sync import retry_failed_syncs

    logger.info("Starting APScheduler background scheduler")

    # Configure job defaults for the entire scheduler
    job_defaults = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 60}

    _scheduler = BackgroundScheduler(job_defaults=job_defaults)

    def sync_goods_quietly():
        """
        Синхронизация каталога, не сыплющая трейсбеками.

        Задача крутится каждую минуту, и при недоступности RemOnline в лог
        каждую минуту падал полный стек. Данные при этом не портятся —
        исключение прилетает из `get_goods()` до записи в базу, — так что
        достаточно одной строки, а на следующей минуте попытка повторится.
        """
        try:
            sync_goods_and_categories()
        except Exception as exc:
            logger.warning("sync_goods skipped: %s", exc)

    # Run sync_goods every minute
    _scheduler.add_job(
        sync_goods_quietly, "cron", minute="*", name="sync_goods", max_instances=1
    )

    # Дотягиваем заказы, не уехавшие в CRM из-за сбоя. Раз в пять минут:
    # чаще незачем, а временный сбой так чинится сам, без ручного прогона.
    _scheduler.add_job(
        retry_failed_syncs,
        "interval",
        minutes=5,
        name="retry_failed_syncs",
        max_instances=1,
    )

    # Run order_event_handler every minute with sequential execution
    _scheduler.add_job(
        order_event_handler,
        "interval",
        minutes=1,
        name="order_event_handler",
        max_instances=1,
        next_run_time=datetime.now()
        + timedelta(seconds=1),  # Start with 1 second delay
    )

    _scheduler.start()
    logger.info(
        "Scheduler started with jobs: %s", [job.id for job in _scheduler.get_jobs()]
    )
    return _scheduler
