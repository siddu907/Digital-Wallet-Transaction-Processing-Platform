from celery import Celery

from app.config import settings


def create_celery_app() -> Celery:
    celery = Celery(
        "digital_wallet",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )
    celery.conf.imports = ("app.workers.tasks",)
    celery.conf.beat_schedule = {
        "daily-limit-reset": {"task": "app.workers.tasks.daily_limit_reset", "schedule": 86400},
        "pending-transaction-cleanup": {"task": "app.workers.tasks.cleanup_pending", "schedule": 3600},
        "suspicious-transaction-scan": {"task": "app.workers.tasks.scan_suspicious", "schedule": 300},
        "daily-wallet-summary": {"task": "app.workers.tasks.wallet_summary", "schedule": 86400},
        "failed-transaction-retry": {"task": "app.workers.tasks.retry_failed", "schedule": 600},
        "approved-refund-processing": {"task": "app.workers.tasks.process_approved_refunds", "schedule": 60},
        "daily-transaction-report": {"task": "app.workers.tasks.daily_report", "schedule": 86400},
    }
    return celery


celery = create_celery_app()
