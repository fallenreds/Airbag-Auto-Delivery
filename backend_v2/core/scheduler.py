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

    from core.goods_sync import sync_goods
    from core.order_event_handler import order_event_handler

    logger.info("Starting APScheduler background scheduler")

    # Configure job defaults for the entire scheduler
    job_defaults = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 60}

    _scheduler = BackgroundScheduler(job_defaults=job_defaults)

    # Run sync_goods every minute
    _scheduler.add_job(
        sync_goods, "cron", minute="*", name="sync_goods", max_instances=1
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
