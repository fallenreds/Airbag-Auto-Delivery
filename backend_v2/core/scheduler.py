import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Module-level singleton to prevent multiple schedulers per process
_scheduler: Optional[BackgroundScheduler] = None


def start_scheduler() -> BackgroundScheduler:
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("Scheduler already running; skipping startup")
        return _scheduler

    from core.goods_sync import sync_goods
    from core.order_event_handler import order_event_handler

    logger.info("Starting APScheduler background scheduler")

    _scheduler = BackgroundScheduler()
    # Run sync_goods every minute
    _scheduler.add_job(sync_goods, CronTrigger(minute="*"))
    # Run order_event_handler every minute
    _scheduler.add_job(order_event_handler, CronTrigger(minute="*"))

    _scheduler.start()
    logger.info("Scheduler started with jobs: %s", [job.id for job in _scheduler.get_jobs()])
    return _scheduler
