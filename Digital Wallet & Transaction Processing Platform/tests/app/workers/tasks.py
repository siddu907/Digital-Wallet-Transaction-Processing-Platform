from app.database import SessionLocal
from app.workers.celery_app import celery
from app.jobs.tasks import (
    cleanup_pending_transactions,
    create_daily_wallet_summary,
    daily_transaction_report,
    process_approved_refunds,
    reset_daily_limits,
    retry_failed_transactions,
    scan_suspicious_transactions,
)


def _run(function):
    with SessionLocal() as db:
        return function(db)


@celery.task(name="app.workers.tasks.cleanup_pending")
def cleanup_pending():
    return _run(cleanup_pending_transactions)


@celery.task(name="app.workers.tasks.wallet_summary")
def wallet_summary():
    return _run(create_daily_wallet_summary)


@celery.task(name="app.workers.tasks.daily_report")
def daily_report():
    return _run(daily_transaction_report)


@celery.task(name="app.workers.tasks.process_approved_refunds")
def process_refunds():
    return _run(process_approved_refunds)


@celery.task(name="app.workers.tasks.retry_failed")
def retry_failed():
    return _run(retry_failed_transactions)


@celery.task(name="app.workers.tasks.scan_suspicious")
def scan_suspicious():
    return _run(scan_suspicious_transactions)


@celery.task(name="app.workers.tasks.daily_limit_reset")
def daily_limit_reset():
    return _run(reset_daily_limits)
