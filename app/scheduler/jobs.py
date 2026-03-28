from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import Settings
from app.services.alerts import AlertService


def build_scheduler(settings: Settings, alert_service: AlertService) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(
        timezone="UTC",
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    )
    scheduler.add_job(alert_service.run_due_subscriptions, "interval", seconds=settings.scheduler_tick_seconds, id="run_due_subscriptions")
    scheduler.add_job(alert_service.retry_pending_notifications, "interval", seconds=30, id="retry_pending_notifications")
    return scheduler
